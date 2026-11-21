"""TablewareService: the servies tiles and a household's claims on them."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    ClaimTakenException,
    InvalidOperationException,
    RecordNotFoundException,
)
from app.models.change_report import ChangeReport
from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.services.config_sync_service import AppliedConfig
from app.services.container import ServiceContainer
from app.services.party_service import PartyService
from app.services.tableware_service import TablewareService

NORMAAL = GuestCategory.NORMAAL


def _reports(session: Session) -> list[str]:
    return [
        f"{report.party.name}: {report.message}"
        for report in session.scalars(select(ChangeReport).order_by(ChangeReport.id))
    ]


@pytest.fixture
def party_service(container: ServiceContainer, seeded: AppliedConfig) -> PartyService:
    return container.party_service()


@pytest.fixture
def tableware_service(
    container: ServiceContainer, seeded: AppliedConfig
) -> TablewareService:
    return container.tableware_service()


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
def borden(seeded: AppliedConfig) -> TablewareItem:
    return seeded.servies[0]


class TestTablewareService:
    # -- list_items --------------------------------------------------------

    def test_list_items_in_config_order(
        self, tableware_service: TablewareService, jansen: Party
    ):
        views = tableware_service.list_items(jansen)

        assert [v.item.text for v in views] == ["20 borden", "20 wijnglazen"]
        assert [v.item.image for v in views] == ["borden.jpg", None]

    def test_list_items_all_free_at_first(
        self, tableware_service: TablewareService, jansen: Party
    ):
        views = tableware_service.list_items(jansen)

        assert [v.status for v in views] == ["free", "free"]
        assert [v.brought_by_name for v in views] == [None, None]

    def test_list_items_shows_the_claimant_to_everyone(
        self,
        tableware_service: TablewareService,
        jansen: Party,
        de_boer: Party,
        seeded: AppliedConfig,
    ):
        borden, glazen = seeded.servies
        tableware_service.claim(jansen, borden.id)
        tableware_service.claim(de_boer, glazen.id)

        mine = tableware_service.list_items(jansen)
        theirs = tableware_service.list_items(de_boer)

        assert [(v.status, v.brought_by_name) for v in mine] == [
            ("yours", "Familie Jansen"),
            ("taken", "Familie de Boer"),
        ]
        assert [(v.status, v.brought_by_name) for v in theirs] == [
            ("taken", "Familie Jansen"),
            ("yours", "Familie de Boer"),
        ]

    def test_list_items_without_items(self, apply_config, container: ServiceContainer):
        applied = apply_config(
            {"households": [{"key": "jansen", "name": "Familie Jansen"}]}
        )

        assert container.tableware_service().list_items(applied.parties[0]) == []

    # -- claim -------------------------------------------------------------

    def test_claim_takes_the_item(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        borden: TablewareItem,
    ):
        view = tableware_service.claim(jansen, borden.id)

        assert view.status == "yours"
        assert view.brought_by_name == "Familie Jansen"
        assert view.item.id == borden.id
        session.expire_all()
        saved = session.get(TablewareItem, borden.id)
        assert saved is not None
        assert saved.brought_by_id == jansen.id

    def test_claim_queues_one_report(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        borden: TablewareItem,
    ):
        tableware_service.claim(jansen, borden.id)

        assert _reports(session)[-1] == "Familie Jansen: Neemt 20 borden mee."
        assert len(_reports(session)) == 2  # The answer's report and this one.

    def test_claim_of_an_item_you_have_changes_nothing(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        borden: TablewareItem,
    ):
        tableware_service.claim(jansen, borden.id)
        reports = _reports(session)

        view = tableware_service.claim(jansen, borden.id)

        assert view.status == "yours"
        assert _reports(session) == reports

    def test_claim_of_an_item_another_household_brings(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        de_boer: Party,
        borden: TablewareItem,
    ):
        tableware_service.claim(jansen, borden.id)
        reports = _reports(session)

        with pytest.raises(ClaimTakenException) as raised:
            tableware_service.claim(de_boer, borden.id)

        assert raised.value.error_code == "CLAIMED_BY_OTHER"
        assert raised.value.message == "Dit servies is net door Familie Jansen gekozen"
        assert _reports(session) == reports
        session.expire_all()
        saved = session.get(TablewareItem, borden.id)
        assert saved is not None
        assert saved.brought_by_id == jansen.id

    def test_claim_by_a_household_that_has_not_answered(
        self,
        tableware_service: TablewareService,
        session: Session,
        els: Party,
        borden: TablewareItem,
    ):
        with pytest.raises(InvalidOperationException) as raised:
            tableware_service.claim(els, borden.id)

        assert raised.value.error_code == "INVALID_OPERATION"
        assert _reports(session) == []

    def test_claim_by_a_household_that_declined(
        self,
        tableware_service: TablewareService,
        party_service: PartyService,
        els: Party,
        borden: TablewareItem,
    ):
        party_service.save_answer(els, PartyAnswer.NOT_COMING, {})

        with pytest.raises(InvalidOperationException):
            tableware_service.claim(els, borden.id)

    def test_claim_unknown_item(
        self, tableware_service: TablewareService, jansen: Party
    ):
        with pytest.raises(RecordNotFoundException) as raised:
            tableware_service.claim(jansen, 999_999_999)

        assert raised.value.error_code == "RECORD_NOT_FOUND"

    def test_claim_after_the_decline_released_it(
        self,
        tableware_service: TablewareService,
        party_service: PartyService,
        jansen: Party,
        de_boer: Party,
        borden: TablewareItem,
    ):
        tableware_service.claim(jansen, borden.id)
        party_service.save_answer(jansen, PartyAnswer.NOT_COMING, {})

        view = tableware_service.claim(de_boer, borden.id)

        assert view.brought_by_name == "Familie de Boer"

    # -- release -----------------------------------------------------------

    def test_release_gives_the_item_back(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        borden: TablewareItem,
    ):
        tableware_service.claim(jansen, borden.id)

        view = tableware_service.release(jansen, borden.id)

        assert view.status == "free"
        assert view.brought_by_name is None
        session.expire_all()
        saved = session.get(TablewareItem, borden.id)
        assert saved is not None
        assert saved.brought_by_id is None

    def test_release_queues_one_report(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        borden: TablewareItem,
    ):
        tableware_service.claim(jansen, borden.id)

        tableware_service.release(jansen, borden.id)

        assert _reports(session)[-2:] == [
            "Familie Jansen: Neemt 20 borden mee.",
            "Familie Jansen: Neemt 20 borden toch niet mee.",
        ]

    def test_release_of_an_item_nobody_brings_changes_nothing(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        borden: TablewareItem,
    ):
        reports = _reports(session)

        view = tableware_service.release(jansen, borden.id)

        assert view.status == "free"
        assert _reports(session) == reports

    def test_release_of_an_item_another_household_brings(
        self,
        tableware_service: TablewareService,
        session: Session,
        jansen: Party,
        de_boer: Party,
        borden: TablewareItem,
    ):
        tableware_service.claim(jansen, borden.id)
        reports = _reports(session)

        with pytest.raises(ClaimTakenException) as raised:
            tableware_service.release(de_boer, borden.id)

        assert raised.value.error_code == "CLAIMED_BY_OTHER"
        assert "Familie Jansen" in raised.value.message
        assert _reports(session) == reports
        session.expire_all()
        saved = session.get(TablewareItem, borden.id)
        assert saved is not None
        assert saved.brought_by_id == jansen.id

    def test_release_unknown_item(
        self, tableware_service: TablewareService, jansen: Party
    ):
        with pytest.raises(RecordNotFoundException):
            tableware_service.release(jansen, 999_999_999)
