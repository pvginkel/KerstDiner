"""Tests of the config sync: the config file's rules, and the testing reset."""

import copy
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.change_report import ChangeReport
from app.models.config_state import ConfigState
from app.models.dish import Dish, DishGuestCategory
from app.models.guest_category import GuestCategory
from app.models.party import GuestCount, Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.schemas.config_file import KerstDinerConfig
from app.services.config_sync_service import (
    AppliedConfig,
    ConfigSyncService,
    SyncSummary,
)
from app.services.container import ServiceContainer
from tests.conftest import SEED_CONFIG


def _config(**changes: Any) -> dict[str, Any]:
    """A copy of ``SEED_CONFIG`` with whole sections replaced."""
    config = copy.deepcopy(SEED_CONFIG)
    config.update(changes)
    return config


def _model(config: dict[str, Any]) -> KerstDinerConfig:
    return KerstDinerConfig.model_validate(config)


def _counts(party: Party) -> dict[GuestCategory, int]:
    return {c: party.people(c) for c in GuestCategory}


def _party(session: Session, key: str) -> Party:
    return session.scalars(select(Party).where(Party.key == key)).one()


def _dish(session: Session, key: str) -> Dish:
    return session.scalars(select(Dish).where(Dish.key == key)).one()


def _item(session: Session, key: str) -> TablewareItem:
    return session.scalars(select(TablewareItem).where(TablewareItem.key == key)).one()


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _state(session: Session) -> ConfigState | None:
    session.expire_all()
    return session.get(ConfigState, 1)


class TestConfigSyncService:
    """``sync``: the config file into the database."""

    @pytest.fixture
    def service(self, container: ServiceContainer) -> ConfigSyncService:
        return container.config_sync_service()

    # -- households ---------------------------------------------------------

    def test_new_household_is_created_with_the_guess_and_a_link(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        config = _config(
            households=[
                *SEED_CONFIG["households"],
                {
                    "key": "wij",
                    "name": "Wij",
                    "guess": {"vegan": 1, "vegetarisch": 2, "normaal": 3, "kind": 4},
                },
            ]
        )

        service.sync(_model(config))

        party = _party(session, "wij")
        assert party.name == "Wij"
        assert party.position == 3
        assert party.answer == PartyAnswer.UNANSWERED
        assert party.answered_at is None
        assert _counts(party) == {
            GuestCategory.VEGAN: 1,
            GuestCategory.VEGETARISCH: 2,
            GuestCategory.NORMAAL: 3,
            GuestCategory.KIND: 4,
        }
        assert party.link_token
        tokens = {p.link_token for p in session.scalars(select(Party))}
        assert len(tokens) == 4

    def test_new_household_has_a_count_row_for_every_category(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        config = _config(
            households=[
                *SEED_CONFIG["households"],
                {"key": "wij", "name": "Wij"},
            ]
        )

        service.sync(_model(config))

        party = _party(session, "wij")
        rows = session.scalars(
            select(GuestCount).where(GuestCount.party_id == party.id)
        ).all()
        assert {row.category for row in rows} == set(GuestCategory)
        assert all(row.people == 0 for row in rows)

    def test_existing_unanswered_household_follows_name_and_counts(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        household = {
            "key": "jansen",
            "name": "Familie Janssen",
            "guess": {"vegan": 3, "normaal": 1},
        }
        config = _config(households=[household, *SEED_CONFIG["households"][1:]])
        before = _party(session, "jansen")
        token, party_id = before.link_token, before.id

        service.sync(_model(config))

        party = _party(session, "jansen")
        assert party.id == party_id
        assert party.link_token == token
        assert party.name == "Familie Janssen"
        assert _counts(party) == {
            GuestCategory.VEGAN: 3,
            GuestCategory.VEGETARISCH: 0,
            GuestCategory.NORMAAL: 1,
            GuestCategory.KIND: 0,
        }
        assert party.answer == PartyAnswer.UNANSWERED

    @pytest.mark.parametrize(
        ("answer", "counts"),
        [
            (PartyAnswer.COMING, {GuestCategory.NORMAAL: 4, GuestCategory.KIND: 1}),
            (PartyAnswer.NOT_COMING, {}),
        ],
    )
    def test_existing_answered_household_follows_only_the_name(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
        answer: PartyAnswer,
        counts: dict[GuestCategory, int],
    ) -> None:
        party = _party(session, "jansen")
        container.party_service().save_answer(party, answer, counts)
        answered = _counts(party)
        token = party.link_token
        household = {
            "key": "jansen",
            "name": "Familie Janssen",
            "guess": {"vegan": 9},
        }
        config = _config(households=[household, *SEED_CONFIG["households"][1:]])

        service.sync(_model(config))

        party = _party(session, "jansen")
        assert party.name == "Familie Janssen"
        assert party.answer == answer
        assert _counts(party) == answered
        assert party.link_token == token

    def test_household_order_follows_the_file(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        households = list(reversed(SEED_CONFIG["households"]))

        service.sync(_model(_config(households=households)))

        ordered = session.scalars(select(Party).order_by(Party.position)).all()
        assert [p.key for p in ordered] == ["tante-els", "de-boer", "jansen"]
        assert [p.position for p in ordered] == [0, 1, 2]

    def test_order_of_an_answered_household_follows_the_file(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        container.party_service().save_answer(
            _party(session, "jansen"), PartyAnswer.COMING, {GuestCategory.NORMAAL: 1}
        )
        households = list(reversed(SEED_CONFIG["households"]))

        service.sync(_model(_config(households=households)))

        assert _party(session, "jansen").position == 2

    def test_a_changed_key_is_a_new_household(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        old_token = _party(session, "jansen").link_token
        household = {**SEED_CONFIG["households"][0], "key": "janssen"}
        config = _config(households=[household, *SEED_CONFIG["households"][1:]])

        service.sync(_model(config))

        assert (
            session.scalars(select(Party).where(Party.key == "jansen")).first() is None
        )
        assert _party(session, "janssen").link_token != old_token

    def test_removed_household_is_gone_with_its_counts(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        removed_id = _party(session, "de-boer").id
        households = [h for h in SEED_CONFIG["households"] if h["key"] != "de-boer"]

        service.sync(_model(_config(households=households)))

        keys = set(session.scalars(select(Party.key)))
        assert keys == {"jansen", "tante-els"}
        left = session.scalar(
            select(func.count())
            .select_from(GuestCount)
            .where(GuestCount.party_id == removed_id)
        )
        assert left == 0

    def test_removed_household_frees_its_dishes_and_servies(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        de_boer = _party(session, "de-boer")
        jansen = _party(session, "jansen")
        _dish(session, "soep").made_by = de_boer
        _dish(session, "rollade").made_by = jansen
        _item(session, "borden").brought_by = de_boer
        _item(session, "glazen").brought_by = jansen
        session.flush()
        households = [h for h in SEED_CONFIG["households"] if h["key"] != "de-boer"]

        service.sync(_model(_config(households=households)))

        assert _dish(session, "soep").made_by_id is None
        assert _dish(session, "rollade").made_by_id == jansen.id
        assert _item(session, "borden").brought_by_id is None
        assert _item(session, "glazen").brought_by_id == jansen.id

    def test_removing_every_household_empties_the_table(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        service.sync(_model(_config(households=[])))

        assert _count(session, Party) == 0
        assert _count(session, GuestCount) == 0
        assert _count(session, Dish) == 3

    # -- dishes -------------------------------------------------------------

    def test_new_dish_is_created(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        dishes = [
            *SEED_CONFIG["dishes"],
            {"key": "taart", "name": "Taart", "for": ["vegan"], "image": "taart.jpg"},
            {"key": "salade", "name": "Salade"},
        ]

        service.sync(_model(_config(dishes=dishes)))

        taart = _dish(session, "taart")
        assert taart.name == "Taart"
        assert taart.image == "taart.jpg"
        assert taart.position == 3
        assert taart.made_by_id is None
        assert taart.categories == {GuestCategory.VEGAN}
        salade = _dish(session, "salade")
        assert salade.image is None
        assert salade.position == 4
        assert salade.categories == {
            GuestCategory.VEGAN,
            GuestCategory.VEGETARISCH,
            GuestCategory.NORMAAL,
        }

    def test_changed_dish_follows_the_file_and_keeps_its_maker(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        rollade = _dish(session, "rollade")
        maker = _party(session, "jansen")
        rollade.made_by = maker
        session.flush()
        dish_id = rollade.id
        dishes = [
            SEED_CONFIG["dishes"][0],
            {
                "key": "rollade",
                "name": "Gevulde rollade",
                "for": ["vegetarisch", "normaal"],
                "image": "rollade.jpg",
            },
            SEED_CONFIG["dishes"][2],
        ]

        service.sync(_model(_config(dishes=dishes)))

        rollade = _dish(session, "rollade")
        assert rollade.id == dish_id
        assert rollade.name == "Gevulde rollade"
        assert rollade.image == "rollade.jpg"
        assert rollade.categories == {GuestCategory.VEGETARISCH, GuestCategory.NORMAAL}
        assert rollade.made_by_id == maker.id
        rows = session.scalars(
            select(DishGuestCategory).where(DishGuestCategory.dish_id == dish_id)
        ).all()
        assert len(rows) == 2

    def test_dish_loses_its_image(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        dishes = [
            {"key": "soep", "name": "Pompoensoep"},
            *SEED_CONFIG["dishes"][1:],
        ]

        service.sync(_model(_config(dishes=dishes)))

        assert _dish(session, "soep").image is None

    def test_dish_without_for_becomes_made_for_all_three(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        dishes = [
            SEED_CONFIG["dishes"][0],
            {"key": "rollade", "name": "Rollade"},
            SEED_CONFIG["dishes"][2],
        ]

        service.sync(_model(_config(dishes=dishes)))

        assert _dish(session, "rollade").categories == {
            GuestCategory.VEGAN,
            GuestCategory.VEGETARISCH,
            GuestCategory.NORMAAL,
        }

    def test_dish_narrowed_to_one_group(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        dishes = [
            {"key": "soep", "name": "Pompoensoep", "for": ["vegan"]},
            *SEED_CONFIG["dishes"][1:],
        ]

        service.sync(_model(_config(dishes=dishes)))

        assert _dish(session, "soep").categories == {GuestCategory.VEGAN}

    def test_dish_order_follows_the_file(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        dishes = list(reversed(SEED_CONFIG["dishes"]))

        service.sync(_model(_config(dishes=dishes)))

        ordered = session.scalars(select(Dish).order_by(Dish.position)).all()
        assert [d.key for d in ordered] == ["wellington", "rollade", "soep"]

    def test_removed_dish_is_gone_with_its_groups(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        removed_id = _dish(session, "rollade").id
        _dish(session, "rollade").made_by = _party(session, "jansen")
        session.flush()
        dishes = [d for d in SEED_CONFIG["dishes"] if d["key"] != "rollade"]

        service.sync(_model(_config(dishes=dishes)))

        assert set(session.scalars(select(Dish.key))) == {"soep", "wellington"}
        left = session.scalar(
            select(func.count())
            .select_from(DishGuestCategory)
            .where(DishGuestCategory.dish_id == removed_id)
        )
        assert left == 0
        assert _party(session, "jansen")

    # -- servies ------------------------------------------------------------

    def test_new_servies_item_is_created(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        servies = [
            *SEED_CONFIG["servies"],
            {"key": "bestek", "text": "20 sets bestek", "image": "bestek.jpg"},
        ]

        service.sync(_model(_config(servies=servies)))

        item = _item(session, "bestek")
        assert item.text == "20 sets bestek"
        assert item.image == "bestek.jpg"
        assert item.position == 2
        assert item.brought_by_id is None

    def test_changed_servies_item_follows_the_file_and_keeps_its_bringer(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        borden = _item(session, "borden")
        bringer = _party(session, "de-boer")
        borden.brought_by = bringer
        session.flush()
        item_id = borden.id
        servies = [
            {"key": "borden", "text": "30 borden"},
            SEED_CONFIG["servies"][1],
        ]

        service.sync(_model(_config(servies=servies)))

        borden = _item(session, "borden")
        assert borden.id == item_id
        assert borden.text == "30 borden"
        assert borden.image is None
        assert borden.brought_by_id == bringer.id

    def test_servies_order_follows_the_file(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        servies = list(reversed(SEED_CONFIG["servies"]))

        service.sync(_model(_config(servies=servies)))

        ordered = session.scalars(
            select(TablewareItem).order_by(TablewareItem.position)
        ).all()
        assert [t.key for t in ordered] == ["glazen", "borden"]

    def test_removed_servies_item_is_gone(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        _item(session, "glazen").brought_by = _party(session, "jansen")
        session.flush()
        servies = [t for t in SEED_CONFIG["servies"] if t["key"] != "glazen"]

        service.sync(_model(_config(servies=servies)))

        assert set(session.scalars(select(TablewareItem.key))) == {"borden"}
        assert _party(session, "jansen")

    # -- whole syncs --------------------------------------------------------

    def test_sync_of_the_same_config_changes_nothing(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        jansen = _party(session, "jansen")
        container.party_service().save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 3}
        )
        _dish(session, "soep").made_by = jansen
        session.flush()
        before = [(p.id, p.key, p.link_token, _counts(p)) for p in seeded.parties]

        summary = service.sync(_model(SEED_CONFIG))

        session.expire_all()
        parties = session.scalars(select(Party).order_by(Party.position)).all()
        assert [(p.id, p.key, p.link_token, _counts(p)) for p in parties] == before
        assert _dish(session, "soep").made_by_id == jansen.id
        assert summary.reset is False

    def test_empty_config_removes_everything(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        summary = service.sync(_model({"reset": 1}))

        assert _count(session, Party) == 0
        assert _count(session, Dish) == 0
        assert _count(session, TablewareItem) == 0
        assert summary == SyncSummary(reset=False, households=0, dishes=0, servies=0)

    def test_summary_counts_what_the_file_holds(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
    ) -> None:
        summary = service.sync(_model(SEED_CONFIG))

        assert summary == SyncSummary(reset=False, households=3, dishes=3, servies=2)

    # -- reset --------------------------------------------------------------

    def test_first_sync_records_reset_and_clears_nothing(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        jansen = _party(session, "jansen")
        container.party_service().save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 3}
        )
        _dish(session, "soep").made_by = jansen
        token = jansen.link_token
        session.execute(delete(ConfigState))
        session.flush()

        summary = service.sync(_model(_config(reset=7)))

        state = _state(session)
        assert state is not None
        assert state.reset_applied == 7
        assert summary.reset is False
        jansen = _party(session, "jansen")
        assert jansen.answer == PartyAnswer.COMING
        assert jansen.people(GuestCategory.NORMAAL) == 3
        assert jansen.link_token == token
        assert _dish(session, "soep").made_by_id == jansen.id

    def test_first_sync_into_an_empty_database_creates_everything(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        session.execute(delete(Dish))
        session.execute(delete(TablewareItem))
        session.execute(delete(Party))
        session.execute(delete(ConfigState))
        session.flush()

        summary = service.sync(_model(SEED_CONFIG))

        assert [
            p.key for p in session.scalars(select(Party).order_by(Party.position))
        ] == [
            "jansen",
            "de-boer",
            "tante-els",
        ]
        assert _count(session, Dish) == 3
        assert _count(session, TablewareItem) == 2
        assert _state(session) is not None
        assert summary.reset is False

    def test_higher_reset_clears_every_answer_claim_and_link(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        jansen = _party(session, "jansen")
        de_boer = _party(session, "de-boer")
        party_service = container.party_service()
        party_service.save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 4}
        )
        party_service.save_answer(de_boer, PartyAnswer.NOT_COMING, {})
        _dish(session, "soep").made_by = jansen
        _item(session, "borden").brought_by = jansen
        session.flush()
        old_ids = {p.key: p.id for p in seeded.parties}
        old_tokens = {p.key: p.link_token for p in seeded.parties}

        summary = service.sync(_model(_config(reset=2)))

        assert summary.reset is True
        parties = session.scalars(select(Party).order_by(Party.position)).all()
        assert [p.key for p in parties] == ["jansen", "de-boer", "tante-els"]
        for party in parties:
            assert party.answer == PartyAnswer.UNANSWERED
            assert party.answered_at is None
            assert party.id != old_ids[party.key]
            assert party.link_token != old_tokens[party.key]
        assert _counts(_party(session, "jansen")) == {
            GuestCategory.VEGAN: 0,
            GuestCategory.VEGETARISCH: 1,
            GuestCategory.NORMAAL: 2,
            GuestCategory.KIND: 2,
        }
        assert _counts(_party(session, "de-boer"))[GuestCategory.NORMAAL] == 2
        assert all(d.made_by_id is None for d in session.scalars(select(Dish)))
        assert all(
            t.brought_by_id is None for t in session.scalars(select(TablewareItem))
        )
        state = _state(session)
        assert state is not None
        assert state.reset_applied == 2

    def test_reset_applies_the_file_afterwards(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        config = _config(
            reset=2,
            households=[{"key": "nieuw", "name": "Nieuw", "guess": {"vegan": 2}}],
            dishes=[{"key": "taart", "name": "Taart"}],
            servies=[{"key": "kopjes", "text": "20 kopjes"}],
        )

        service.sync(_model(config))

        assert set(session.scalars(select(Party.key))) == {"nieuw"}
        assert set(session.scalars(select(Dish.key))) == {"taart"}
        assert set(session.scalars(select(TablewareItem.key))) == {"kopjes"}
        assert _party(session, "nieuw").people(GuestCategory.VEGAN) == 2

    def test_equal_reset_clears_nothing(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        jansen = _party(session, "jansen")
        container.party_service().save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 4}
        )
        _dish(session, "soep").made_by = jansen
        session.flush()
        token = jansen.link_token

        summary = service.sync(_model(_config(reset=1)))

        assert summary.reset is False
        jansen = _party(session, "jansen")
        assert jansen.answer == PartyAnswer.COMING
        assert jansen.link_token == token
        assert _dish(session, "soep").made_by_id == jansen.id

    def test_lower_reset_clears_nothing_and_keeps_the_applied_one(
        self,
        apply_config: Callable[[dict[str, Any]], AppliedConfig],
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        apply_config(_config(reset=5))
        jansen = _party(session, "jansen")
        container.party_service().save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 4}
        )
        _dish(session, "soep").made_by = jansen
        session.flush()
        token = jansen.link_token

        summary = service.sync(_model(_config(reset=3)))

        assert summary.reset is False
        jansen = _party(session, "jansen")
        assert jansen.answer == PartyAnswer.COMING
        assert jansen.link_token == token
        assert _dish(session, "soep").made_by_id == jansen.id
        state = _state(session)
        assert state is not None
        assert state.reset_applied == 5

    def test_a_reset_is_applied_once(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        assert service.sync(_model(_config(reset=2))).reset is True
        jansen = _party(session, "jansen")
        container.party_service().save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 4}
        )

        summary = service.sync(_model(_config(reset=2)))

        assert summary.reset is False
        assert _party(session, "jansen").answer == PartyAnswer.COMING

    def test_reset_to_zero_without_state_starts_at_zero(
        self,
        service: ConfigSyncService,
        apply_config: Callable[[dict[str, Any]], AppliedConfig],
        session: Session,
    ) -> None:
        apply_config(_config(reset=0))
        session.execute(delete(ConfigState))
        session.flush()

        service.sync(_model(_config(reset=0)))

        state = _state(session)
        assert state is not None
        assert state.reset_applied == 0


class TestConfigSyncServiceReplaceAll:
    """``replace_all``: the testing endpoint's reset."""

    @pytest.fixture
    def service(self, container: ServiceContainer) -> ConfigSyncService:
        return container.config_sync_service()

    def test_wipes_what_was_there(
        self,
        seeded: AppliedConfig,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        config = _config(
            households=[{"key": "nieuw", "name": "Nieuw"}],
            dishes=[{"key": "taart", "name": "Taart"}],
            servies=[{"key": "kopjes", "text": "20 kopjes"}],
        )

        service.replace_all(_model(config))

        assert set(session.scalars(select(Party.key))) == {"nieuw"}
        assert set(session.scalars(select(Dish.key))) == {"taart"}
        assert set(session.scalars(select(TablewareItem.key))) == {"kopjes"}

    def test_wipes_the_shipped_data_of_the_run_database(
        self,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        service.replace_all(_model({}))

        assert _count(session, Party) == 0
        assert _count(session, GuestCount) == 0
        assert _count(session, Dish) == 0
        assert _count(session, DishGuestCategory) == 0
        assert _count(session, TablewareItem) == 0

    def test_clears_answers_claims_and_links(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        jansen = _party(session, "jansen")
        container.party_service().save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 4}
        )
        _dish(session, "soep").made_by = jansen
        _item(session, "borden").brought_by = jansen
        session.flush()
        old_tokens = {p.link_token for p in seeded.parties}

        applied = service.replace_all(_model(SEED_CONFIG))

        assert {p.link_token for p in applied.parties}.isdisjoint(old_tokens)
        assert all(p.answer == PartyAnswer.UNANSWERED for p in applied.parties)
        assert all(d.made_by_id is None for d in applied.dishes)
        assert all(t.brought_by_id is None for t in applied.servies)
        assert _counts(applied.parties[0]) == {
            GuestCategory.VEGAN: 0,
            GuestCategory.VEGETARISCH: 1,
            GuestCategory.NORMAAL: 2,
            GuestCategory.KIND: 2,
        }

    def test_clears_the_report_queue(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        container.party_service().save_answer(
            _party(session, "jansen"), PartyAnswer.COMING, {GuestCategory.NORMAAL: 1}
        )
        session.add(ChangeReport(message="al verstuurd", sent_at=func.now()))
        session.flush()
        assert _count(session, ChangeReport) >= 2

        service.replace_all(_model(SEED_CONFIG))

        assert _count(session, ChangeReport) == 0

    def test_returns_what_it_created_in_config_order(
        self,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        config = {
            "households": [
                {"key": "zeger", "name": "Zeger"},
                {"key": "adam", "name": "Adam"},
                {"key": "mies", "name": "Mies"},
            ],
            "dishes": [
                {"key": "z-taart", "name": "Taart"},
                {"key": "a-soep", "name": "Soep"},
            ],
            "servies": [
                {"key": "z-borden", "text": "borden"},
                {"key": "a-glazen", "text": "glazen"},
            ],
        }

        applied = service.replace_all(_model(config))

        assert [p.key for p in applied.parties] == ["zeger", "adam", "mies"]
        assert [d.key for d in applied.dishes] == ["z-taart", "a-soep"]
        assert [t.key for t in applied.servies] == ["z-borden", "a-glazen"]
        assert [p.name for p in applied.parties] == ["Zeger", "Adam", "Mies"]

    def test_returned_rows_are_stored_with_ids_and_unique_tokens(
        self,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        applied = service.replace_all(_model(SEED_CONFIG))

        assert all(isinstance(p.id, int) for p in applied.parties)
        assert all(isinstance(d.id, int) for d in applied.dishes)
        assert all(isinstance(t.id, int) for t in applied.servies)
        tokens = [p.link_token for p in applied.parties]
        assert all(tokens)
        assert len(set(tokens)) == len(tokens)
        assert session.get(Party, applied.parties[0].id) is applied.parties[0]

    def test_applies_images_and_groups(
        self,
        service: ConfigSyncService,
    ) -> None:
        applied = service.replace_all(_model(SEED_CONFIG))

        soep, rollade, wellington = applied.dishes
        assert soep.image == "pompoensoep.jpg"
        assert soep.categories == {
            GuestCategory.VEGAN,
            GuestCategory.VEGETARISCH,
            GuestCategory.NORMAAL,
        }
        assert rollade.categories == {GuestCategory.NORMAAL}
        assert wellington.categories == {GuestCategory.VEGAN, GuestCategory.VEGETARISCH}
        assert [t.image for t in applied.servies] == ["borden.jpg", None]

    def test_sets_the_config_state_when_there_is_one(
        self,
        apply_config: Callable[[dict[str, Any]], AppliedConfig],
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        apply_config(_config(reset=4))

        service.replace_all(_model(_config(reset=2)))

        state = _state(session)
        assert state is not None
        assert state.reset_applied == 2
        assert _count(session, ConfigState) == 1

    def test_creates_the_config_state_when_there_is_none(
        self,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        session.execute(delete(ConfigState))
        session.flush()

        service.replace_all(_model(_config(reset=6)))

        state = _state(session)
        assert state is not None
        assert state.reset_applied == 6

    def test_a_later_sync_of_the_same_reset_clears_nothing(
        self,
        seeded: AppliedConfig,
        container: ServiceContainer,
        service: ConfigSyncService,
        session: Session,
    ) -> None:
        container.party_service().save_answer(
            _party(session, "jansen"), PartyAnswer.COMING, {GuestCategory.NORMAAL: 1}
        )

        service.sync(_model(SEED_CONFIG))

        assert _party(session, "jansen").answer == PartyAnswer.COMING
