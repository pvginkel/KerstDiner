"""PartyService: a household's answer, the totals and the admin's link replacement."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    AuthenticationException,
    InvalidOperationException,
    RecordNotFoundException,
)
from app.models.change_report import ChangeReport
from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.services.config_sync_service import AppliedConfig
from app.services.container import ServiceContainer
from app.services.party_service import (
    PartyService,
    category_totals,
    new_link_token,
)

VEGAN = GuestCategory.VEGAN
VEGETARISCH = GuestCategory.VEGETARISCH
NORMAAL = GuestCategory.NORMAAL
KIND = GuestCategory.KIND


def _reports(session: Session) -> list[str]:
    return [
        report.message
        for report in session.scalars(select(ChangeReport).order_by(ChangeReport.id))
    ]


def _counts(party: Party) -> dict[GuestCategory, int]:
    return {category: party.people(category) for category in GuestCategory}


@pytest.fixture
def party_service(container: ServiceContainer, seeded: AppliedConfig) -> PartyService:
    return container.party_service()


@pytest.fixture
def jansen(seeded: AppliedConfig) -> Party:
    return seeded.parties[0]


@pytest.fixture
def de_boer(seeded: AppliedConfig) -> Party:
    return seeded.parties[1]


@pytest.fixture
def els(seeded: AppliedConfig) -> Party:
    return seeded.parties[2]


class TestPartyService:
    # -- get_by_link_token -------------------------------------------------

    def test_get_by_link_token_finds_the_party(
        self, party_service: PartyService, jansen: Party, de_boer: Party
    ):
        assert party_service.get_by_link_token(jansen.link_token).id == jansen.id
        assert party_service.get_by_link_token(de_boer.link_token).id == de_boer.id

    def test_get_by_link_token_unknown_token(self, party_service: PartyService):
        with pytest.raises(AuthenticationException) as raised:
            party_service.get_by_link_token("no-such-token")

        assert raised.value.message == "Gebruik de persoonlijke link uit je e-mail"

    def test_get_by_link_token_empty_token(self, party_service: PartyService):
        with pytest.raises(AuthenticationException):
            party_service.get_by_link_token("")

    def test_get_by_link_token_replaced_token(
        self, party_service: PartyService, jansen: Party
    ):
        old_token = jansen.link_token

        party_service.replace_link(jansen.id)

        with pytest.raises(AuthenticationException):
            party_service.get_by_link_token(old_token)

    # -- save_answer -------------------------------------------------------

    def test_a_new_party_has_not_answered_and_holds_the_guess(self, jansen: Party):
        assert jansen.answer == PartyAnswer.UNANSWERED
        assert jansen.answered_at is None
        assert _counts(jansen) == {VEGAN: 0, VEGETARISCH: 1, NORMAAL: 2, KIND: 2}

    def test_save_answer_coming_saves_the_counts(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        result = party_service.save_answer(
            jansen, PartyAnswer.COMING, {VEGETARISCH: 1, NORMAAL: 2, KIND: 2}
        )

        assert result.answer == PartyAnswer.COMING
        assert _counts(result) == {VEGAN: 0, VEGETARISCH: 1, NORMAAL: 2, KIND: 2}
        assert result.answered_at is not None

    def test_save_answer_coming_replaces_the_guess(
        self, party_service: PartyService, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {VEGAN: 3, NORMAAL: 1})

        assert _counts(jansen) == {VEGAN: 3, VEGETARISCH: 0, NORMAAL: 1, KIND: 0}

    def test_save_answer_coming_queues_exactly_one_report(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.save_answer(
            jansen, PartyAnswer.COMING, {VEGETARISCH: 1, NORMAAL: 2, KIND: 2}
        )

        assert _reports(session) == [
            "Familie Jansen komt met 5: 1 vegetarisch, 2 eet alles, 2 kindermenu's."
        ]

    def test_save_answer_with_the_guess_is_still_a_change_from_unanswered(
        self, party_service: PartyService, session: Session, de_boer: Party
    ):
        party_service.save_answer(de_boer, PartyAnswer.COMING, {NORMAAL: 2})

        assert de_boer.answer == PartyAnswer.COMING
        assert de_boer.answered_at is not None
        assert _reports(session) == ["Familie de Boer komt met 2: 2 eet alles."]

    def test_save_answer_persists(
        self, party_service: PartyService, session: Session, els: Party
    ):
        party_service.save_answer(els, PartyAnswer.COMING, {VEGAN: 2})
        session.expire_all()

        saved = session.get(Party, els.id)
        assert saved is not None
        assert saved.answer == PartyAnswer.COMING
        assert saved.people(VEGAN) == 2

    def test_save_answer_unchanged_changes_nothing_and_queues_nothing(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        counts = {VEGETARISCH: 1, NORMAAL: 2, KIND: 2}
        party_service.save_answer(jansen, PartyAnswer.COMING, counts)
        answered_at = jansen.answered_at

        party_service.save_answer(jansen, PartyAnswer.COMING, counts)

        assert jansen.answered_at == answered_at
        assert len(_reports(session)) == 1

    def test_save_answer_unchanged_treats_a_missing_count_as_zero(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 2})

        party_service.save_answer(
            jansen, PartyAnswer.COMING, {NORMAAL: 2, VEGAN: 0, KIND: 0}
        )

        assert len(_reports(session)) == 1

    def test_save_answer_changed_counts_queue_a_new_report_and_move_answered_at(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 2})
        first = jansen.answered_at
        assert first is not None

        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 3, KIND: 1})

        assert jansen.answered_at is not None
        assert jansen.answered_at >= first
        assert _reports(session) == [
            "Familie Jansen komt met 2: 2 eet alles.",
            "Familie Jansen komt met 4: 3 eet alles, 1 kindermenu.",
        ]

    def test_save_answer_not_coming_zeroes_every_count(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {NORMAAL: 5})

        assert jansen.answer == PartyAnswer.NOT_COMING
        assert _counts(jansen) == {VEGAN: 0, VEGETARISCH: 0, NORMAAL: 0, KIND: 0}
        assert jansen.answered_at is not None
        assert _reports(session) == ["Familie Jansen komt niet."]

    def test_save_answer_not_coming_twice_changes_nothing(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})
        answered_at = jansen.answered_at

        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})

        assert jansen.answered_at == answered_at
        assert _reports(session) == ["Familie Jansen komt niet."]

    def test_save_answer_not_coming_after_coming_queues_one_more_report(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 2})
        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})

        assert _reports(session) == [
            "Familie Jansen komt met 2: 2 eet alles.",
            "Familie Jansen komt niet.",
        ]

    def test_save_answer_coming_after_not_coming(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})

        party_service.save_answer(jansen, PartyAnswer.COMING, {VEGAN: 1})

        assert jansen.answer == PartyAnswer.COMING
        assert _counts(jansen) == {VEGAN: 1, VEGETARISCH: 0, NORMAAL: 0, KIND: 0}
        assert _reports(session)[-1] == "Familie Jansen komt met 1: 1 vegan."

    def test_save_answer_not_coming_releases_dishes_and_servies(
        self,
        party_service: PartyService,
        session: Session,
        seeded: AppliedConfig,
        jansen: Party,
        de_boer: Party,
    ):
        soep, rollade, wellington = seeded.dishes
        borden, glazen = seeded.servies
        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 2})
        party_service.save_answer(de_boer, PartyAnswer.COMING, {NORMAAL: 2})
        soep.made_by_id = jansen.id
        wellington.made_by_id = jansen.id
        rollade.made_by_id = de_boer.id
        borden.brought_by_id = jansen.id
        glazen.brought_by_id = de_boer.id
        session.flush()

        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})
        session.expire_all()

        dishes = {d.key: d.made_by_id for d in session.scalars(select(Dish))}
        servies = {
            t.key: t.brought_by_id for t in session.scalars(select(TablewareItem))
        }
        assert dishes == {
            "soep": None,
            "rollade": de_boer.id,
            "wellington": None,
        }
        assert servies == {"borden": None, "glazen": de_boer.id}

    def test_save_answer_not_coming_reports_the_decline_only(
        self,
        party_service: PartyService,
        session: Session,
        seeded: AppliedConfig,
        jansen: Party,
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 2})
        seeded.dishes[0].made_by_id = jansen.id
        seeded.servies[0].brought_by_id = jansen.id
        session.flush()

        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})

        assert _reports(session) == [
            "Familie Jansen komt met 2: 2 eet alles.",
            "Familie Jansen komt niet.",
        ]

    def test_save_answer_coming_keeps_the_claims(
        self,
        party_service: PartyService,
        session: Session,
        seeded: AppliedConfig,
        jansen: Party,
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 2})
        seeded.dishes[0].made_by_id = jansen.id
        session.flush()

        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 4})
        session.expire_all()

        dish = session.get(Dish, seeded.dishes[0].id)
        assert dish is not None
        assert dish.made_by_id == jansen.id

    def test_save_answer_unanswered_is_refused(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        with pytest.raises(InvalidOperationException) as raised:
            party_service.save_answer(jansen, PartyAnswer.UNANSWERED, {})

        assert raised.value.error_code == "INVALID_OPERATION"
        assert jansen.answer == PartyAnswer.UNANSWERED
        assert _reports(session) == []

    # -- list_parties ------------------------------------------------------

    def test_list_parties_in_config_order(self, party_service: PartyService):
        parties = party_service.list_parties()

        assert [p.name for p in parties] == [
            "Familie Jansen",
            "Familie de Boer",
            "Tante Els",
        ]

    def test_list_parties_follows_the_config_not_the_alphabet(
        self, apply_config, container: ServiceContainer
    ):
        apply_config(
            {
                "households": [
                    {"key": "zeeman", "name": "Zeeman"},
                    {"key": "aarts", "name": "Aarts"},
                    {"key": "mulder", "name": "Mulder"},
                ]
            }
        )

        names = [p.name for p in container.party_service().list_parties()]

        assert names == ["Zeeman", "Aarts", "Mulder"]

    def test_list_parties_empty(self, apply_config, container: ServiceContainer):
        apply_config({"households": []})

        assert container.party_service().list_parties() == []

    # -- totals ------------------------------------------------------------

    def test_totals_count_the_guesses_of_the_unanswered(
        self, party_service: PartyService
    ):
        totals = party_service.totals()

        assert totals.counts == {VEGAN: 1, VEGETARISCH: 1, NORMAAL: 4, KIND: 2}

    def test_totals_people_sum_all_four_categories(self, party_service: PartyService):
        assert party_service.totals().people == 8

    def test_totals_follow_the_answers_and_count_decliners_at_zero(
        self,
        party_service: PartyService,
        jansen: Party,
        de_boer: Party,
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {VEGAN: 2, KIND: 1})
        party_service.save_answer(de_boer, PartyAnswer.NOT_COMING, {})

        totals = party_service.totals()

        # Tante Els has not answered: her guess of 1 vegan still counts.
        assert totals.counts == {VEGAN: 3, VEGETARISCH: 0, NORMAAL: 0, KIND: 1}
        assert totals.people == 4

    def test_totals_without_parties_are_zero(
        self, apply_config, container: ServiceContainer
    ):
        apply_config({"households": []})

        totals = container.party_service().totals()

        assert totals.counts == dict.fromkeys(GuestCategory, 0)
        assert totals.people == 0

    def test_category_totals_has_every_category(
        self, session: Session, seeded: AppliedConfig
    ):
        assert category_totals(session) == {
            VEGAN: 1,
            VEGETARISCH: 1,
            NORMAAL: 4,
            KIND: 2,
        }

    # -- replace_link ------------------------------------------------------

    def test_replace_link_gives_a_new_token(
        self, party_service: PartyService, jansen: Party
    ):
        old_token = jansen.link_token

        result = party_service.replace_link(jansen.id)

        assert result.id == jansen.id
        assert result.link_token != old_token
        assert party_service.get_by_link_token(result.link_token).id == jansen.id

    def test_replace_link_leaves_the_other_parties_alone(
        self, party_service: PartyService, jansen: Party, de_boer: Party
    ):
        other_token = de_boer.link_token

        party_service.replace_link(jansen.id)

        assert party_service.get_by_link_token(other_token).id == de_boer.id

    def test_replace_link_keeps_the_answer(
        self, party_service: PartyService, jansen: Party
    ):
        party_service.save_answer(jansen, PartyAnswer.COMING, {NORMAAL: 2})

        party_service.replace_link(jansen.id)

        assert jansen.answer == PartyAnswer.COMING
        assert jansen.people(NORMAAL) == 2

    def test_replace_link_queues_no_report(
        self, party_service: PartyService, session: Session, jansen: Party
    ):
        party_service.replace_link(jansen.id)

        assert _reports(session) == []

    def test_replace_link_unknown_party(self, party_service: PartyService):
        with pytest.raises(RecordNotFoundException) as raised:
            party_service.replace_link(999_999_999)

        assert raised.value.error_code == "RECORD_NOT_FOUND"

    # -- new_link_token ----------------------------------------------------

    def test_new_link_token_is_url_safe_and_hard_to_guess(self):
        token = new_link_token()

        assert len(token) >= 22
        assert token.replace("-", "").replace("_", "").isalnum()

    def test_new_link_token_differs_every_time(self):
        assert len({new_link_token() for _ in range(50)}) == 50
