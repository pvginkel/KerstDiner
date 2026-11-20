"""DishService: the tiles, a household's claims on them, and the claim race."""

import threading
import time

import pytest
from flask import Flask
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.exceptions import (
    ClaimTakenException,
    InvalidOperationException,
    RecordNotFoundException,
)
from app.models.change_report import ChangeReport
from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer
from app.schemas.config_file import KerstDinerConfig
from app.services.config_sync_service import AppliedConfig, ConfigSyncService
from app.services.container import ServiceContainer
from app.services.dish_service import DishService, DishView, claim_status
from app.services.party_service import PartyService
from app.services.report_service import ReportQueue
from tests.conftest import SEED_CONFIG

NORMAAL = GuestCategory.NORMAAL
VEGAN = GuestCategory.VEGAN
KIND = GuestCategory.KIND


def _reports(session: Session) -> list[str]:
    return [
        report.message
        for report in session.scalars(select(ChangeReport).order_by(ChangeReport.id))
    ]


@pytest.fixture
def party_service(container: ServiceContainer, seeded: AppliedConfig) -> PartyService:
    return container.party_service()


@pytest.fixture
def dish_service(container: ServiceContainer, seeded: AppliedConfig) -> DishService:
    return container.dish_service()


@pytest.fixture
def jansen(party_service: PartyService, seeded: AppliedConfig) -> Party:
    """Familie Jansen, coming."""
    party = seeded.parties[0]
    party_service.save_answer(party, PartyAnswer.COMING, {NORMAAL: 2})
    return party


@pytest.fixture
def de_boer(party_service: PartyService, seeded: AppliedConfig) -> Party:
    """Familie de Boer, coming."""
    party = seeded.parties[1]
    party_service.save_answer(party, PartyAnswer.COMING, {NORMAAL: 2})
    return party


@pytest.fixture
def els(seeded: AppliedConfig) -> Party:
    """Tante Els, who has not answered."""
    return seeded.parties[2]


@pytest.fixture
def soep(seeded: AppliedConfig) -> Dish:
    return seeded.dishes[0]


@pytest.fixture
def rollade(seeded: AppliedConfig) -> Dish:
    return seeded.dishes[1]


def _by_key(views: list[DishView]) -> dict[str, DishView]:
    return {view.dish.key: view for view in views}


class TestDishService:
    # -- claim_status ------------------------------------------------------

    def test_claim_status_free_yours_and_taken(self, seeded: AppliedConfig):
        jansen, de_boer, _ = seeded.parties

        assert claim_status(None, jansen) == "free"
        assert claim_status(jansen.id, jansen) == "yours"
        assert claim_status(de_boer.id, jansen) == "taken"

    # -- list_dishes -------------------------------------------------------

    def test_list_dishes_in_config_order(
        self, dish_service: DishService, jansen: Party
    ):
        views = dish_service.list_dishes(jansen)

        assert [v.dish.name for v in views] == [
            "Pompoensoep",
            "Rollade",
            "Linzen-wellington",
        ]

    def test_list_dishes_all_free_at_first(
        self, dish_service: DishService, jansen: Party
    ):
        views = dish_service.list_dishes(jansen)

        assert [v.status for v in views] == ["free", "free", "free"]
        assert [v.made_by_name for v in views] == [None, None, None]

    def test_list_dishes_people_count_the_groups_it_is_made_for(
        self, dish_service: DishService, els: Party
    ):
        # Guesses: vegan 1 (Els), vegetarisch 1, normaal 2 + 2, kind 2 (Jansen).
        views = _by_key(dish_service.list_dishes(els))

        assert views["soep"].people == 1 + 1 + 4
        assert views["rollade"].people == 4
        assert views["wellington"].people == 1 + 1

    def test_list_dishes_people_never_count_young_children(
        self, dish_service: DishService, els: Party, session: Session
    ):
        before = _by_key(dish_service.list_dishes(els))

        for party in session.scalars(select(Party)):
            party.set_people(KIND, 50)
        session.flush()
        after = _by_key(dish_service.list_dishes(els))

        assert {k: v.people for k, v in after.items()} == {
            k: v.people for k, v in before.items()
        }

    def test_list_dishes_people_follow_the_answers(
        self,
        dish_service: DishService,
        party_service: PartyService,
        jansen: Party,
        de_boer: Party,
        els: Party,
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {VEGAN: 3, NORMAAL: 1})
        party_service.save_answer(de_boer, PartyAnswer.NOT_COMING, {})

        views = _by_key(dish_service.list_dishes(els))

        # Jansen: 3 vegan + 1 normaal; de Boer: nobody; Els (unanswered): guess 1 vegan.
        assert views["soep"].people == 4 + 1 + 0
        assert views["rollade"].people == 1
        assert views["wellington"].people == 3 + 1

    def test_list_dishes_shows_the_claimant_to_everyone(
        self,
        dish_service: DishService,
        jansen: Party,
        de_boer: Party,
        soep: Dish,
        rollade: Dish,
    ):
        dish_service.claim(jansen, soep.id)
        dish_service.claim(de_boer, rollade.id)

        mine = _by_key(dish_service.list_dishes(jansen))
        theirs = _by_key(dish_service.list_dishes(de_boer))

        assert (mine["soep"].status, mine["soep"].made_by_name) == (
            "yours",
            "Familie Jansen",
        )
        assert (mine["rollade"].status, mine["rollade"].made_by_name) == (
            "taken",
            "Familie de Boer",
        )
        assert (theirs["soep"].status, theirs["soep"].made_by_name) == (
            "taken",
            "Familie Jansen",
        )
        assert theirs["rollade"].status == "yours"
        assert mine["wellington"].status == "free"

    def test_list_dishes_without_dishes(
        self, apply_config, container: ServiceContainer
    ):
        applied = apply_config(
            {"households": [{"key": "jansen", "name": "Familie Jansen"}]}
        )

        assert container.dish_service().list_dishes(applied.parties[0]) == []

    # -- claim -------------------------------------------------------------

    def test_claim_takes_the_dish(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        soep: Dish,
    ):
        view = dish_service.claim(jansen, soep.id)

        assert view.status == "yours"
        assert view.made_by_name == "Familie Jansen"
        assert view.dish.id == soep.id
        session.expire_all()
        assert session.get(Dish, soep.id).made_by_id == jansen.id  # type: ignore[union-attr]

    def test_claim_queues_one_report(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)

        assert _reports(session)[-1] == "Familie Jansen maakt Pompoensoep."
        assert len(_reports(session)) == 2  # The answer's report and this one.

    def test_claim_of_a_dish_you_have_changes_nothing(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)
        reports = _reports(session)

        view = dish_service.claim(jansen, soep.id)

        assert view.status == "yours"
        assert _reports(session) == reports

    def test_claim_view_carries_the_people(
        self, dish_service: DishService, jansen: Party, rollade: Dish
    ):
        view = dish_service.claim(jansen, rollade.id)

        # Jansen's 2 and de Boer's guess of 2, all normaal.
        assert view.people == 4

    def test_claim_of_a_dish_another_household_makes(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        de_boer: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)
        reports = _reports(session)

        with pytest.raises(ClaimTakenException) as raised:
            dish_service.claim(de_boer, soep.id)

        assert raised.value.error_code == "CLAIMED_BY_OTHER"
        assert raised.value.message == "Dit gerecht is net door Familie Jansen gekozen"
        assert _reports(session) == reports
        session.expire_all()
        assert session.get(Dish, soep.id).made_by_id == jansen.id  # type: ignore[union-attr]

    def test_claim_by_a_household_that_has_not_answered(
        self,
        dish_service: DishService,
        session: Session,
        els: Party,
        soep: Dish,
    ):
        with pytest.raises(InvalidOperationException) as raised:
            dish_service.claim(els, soep.id)

        assert raised.value.error_code == "INVALID_OPERATION"
        assert _reports(session) == []
        session.expire_all()
        assert session.get(Dish, soep.id).made_by_id is None  # type: ignore[union-attr]

    def test_claim_by_a_household_that_declined(
        self,
        dish_service: DishService,
        party_service: PartyService,
        els: Party,
        soep: Dish,
    ):
        party_service.save_answer(els, PartyAnswer.NOT_COMING, {})

        with pytest.raises(InvalidOperationException):
            dish_service.claim(els, soep.id)

    def test_claim_unknown_dish(self, dish_service: DishService, jansen: Party):
        with pytest.raises(RecordNotFoundException) as raised:
            dish_service.claim(jansen, 999_999_999)

        assert raised.value.error_code == "RECORD_NOT_FOUND"

    def test_claim_after_the_decline_released_it(
        self,
        dish_service: DishService,
        party_service: PartyService,
        jansen: Party,
        de_boer: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)
        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})

        view = dish_service.claim(de_boer, soep.id)

        assert view.status == "yours"
        assert view.made_by_name == "Familie de Boer"

    # -- release -----------------------------------------------------------

    def test_release_gives_the_dish_back(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)

        view = dish_service.release(jansen, soep.id)

        assert view.status == "free"
        assert view.made_by_name is None
        session.expire_all()
        assert session.get(Dish, soep.id).made_by_id is None  # type: ignore[union-attr]

    def test_release_queues_one_report(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)

        dish_service.release(jansen, soep.id)

        assert _reports(session)[-2:] == [
            "Familie Jansen maakt Pompoensoep.",
            "Familie Jansen maakt Pompoensoep toch niet.",
        ]

    def test_release_of_a_dish_nobody_makes_changes_nothing(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        soep: Dish,
    ):
        reports = _reports(session)

        view = dish_service.release(jansen, soep.id)

        assert view.status == "free"
        assert _reports(session) == reports

    def test_release_of_a_dish_another_household_makes(
        self,
        dish_service: DishService,
        session: Session,
        jansen: Party,
        de_boer: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)
        reports = _reports(session)

        with pytest.raises(ClaimTakenException) as raised:
            dish_service.release(de_boer, soep.id)

        assert raised.value.error_code == "CLAIMED_BY_OTHER"
        assert "Familie Jansen" in raised.value.message
        assert _reports(session) == reports
        session.expire_all()
        assert session.get(Dish, soep.id).made_by_id == jansen.id  # type: ignore[union-attr]

    def test_release_unknown_dish(self, dish_service: DishService, jansen: Party):
        with pytest.raises(RecordNotFoundException):
            dish_service.release(jansen, 999_999_999)

    def test_release_then_claim_by_another(
        self,
        dish_service: DishService,
        jansen: Party,
        de_boer: Party,
        soep: Dish,
    ):
        dish_service.claim(jansen, soep.id)
        dish_service.release(jansen, soep.id)

        view = dish_service.claim(de_boer, soep.id)

        assert view.made_by_name == "Familie de Boer"


class TestDishServiceRace:
    """Two households claim the same dish at once: the second gets the 409."""

    @staticmethod
    def _wait_for_a_blocked_backend(observer: Session) -> None:
        """Poll until a backend of this database waits for a row lock."""
        deadline = time.perf_counter() + 15
        while time.perf_counter() < deadline:
            waiting = observer.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() "
                    "AND wait_event_type = 'Lock'"
                )
            ).scalar_one()
            observer.rollback()
            if waiting:
                return
            time.sleep(0.02)
        pytest.fail("No backend waits for the dish's row lock")

    def test_the_second_claim_waits_for_the_first_and_is_refused(
        self, committed_app: Flask
    ):
        session_maker = committed_app.container.session_maker()  # type: ignore[attr-defined]
        sender = committed_app.container.report_sender()  # type: ignore[attr-defined]

        setup = session_maker()
        with setup.begin():
            applied = ConfigSyncService(setup).replace_all(
                KerstDinerConfig.model_validate(SEED_CONFIG)
            )
            queue = ReportQueue(setup, sender)
            parties = PartyService(db_session=setup, report_queue=queue)
            parties.save_answer(applied.parties[0], PartyAnswer.COMING, {NORMAAL: 2})
            parties.save_answer(applied.parties[1], PartyAnswer.COMING, {NORMAAL: 2})
            household_a, household_b = applied.parties[0].id, applied.parties[1].id
            dish_id = applied.dishes[0].id
        setup.close()

        session_a = session_maker()
        session_b = session_maker()
        observer = session_maker()
        outcome: dict[str, object] = {}

        def household_b_claims() -> None:
            try:
                service = DishService(
                    db_session=session_b, report_queue=ReportQueue(session_b, sender)
                )
                party = session_b.get(Party, household_b)
                assert party is not None
                outcome["view"] = service.claim(party, dish_id)
                session_b.commit()
            except BaseException as error:  # handed to the test thread
                outcome["error"] = error
                session_b.rollback()

        try:
            # Household A takes the dish and holds its transaction open.
            service_a = DishService(
                db_session=session_a, report_queue=ReportQueue(session_a, sender)
            )
            party_a = session_a.get(Party, household_a)
            assert party_a is not None
            view_a = service_a.claim(party_a, dish_id)
            assert view_a.status == "yours"

            thread = threading.Thread(target=household_b_claims, daemon=True)
            thread.start()

            # B reaches the row lock A holds and waits there.
            self._wait_for_a_blocked_backend(observer)
            assert thread.is_alive()
            assert outcome == {}

            session_a.commit()
            thread.join(timeout=15)
            assert not thread.is_alive()
        finally:
            session_a.close()
            session_b.close()

        error = outcome.get("error")
        assert isinstance(error, ClaimTakenException)
        assert error.error_code == "CLAIMED_BY_OTHER"
        assert error.message == "Dit gerecht is net door Familie Jansen gekozen"
        assert "view" not in outcome

        # The dish is A's, and only A's claim was reported.
        observer.rollback()
        dish = observer.get(Dish, dish_id)
        assert dish is not None
        assert dish.made_by_id == household_a
        messages = [
            r.message
            for r in observer.scalars(select(ChangeReport).order_by(ChangeReport.id))
        ]
        assert messages.count("Familie Jansen maakt Pompoensoep.") == 1
        assert not any("de Boer maakt" in m for m in messages)
        observer.close()
