"""The config sync: the config file's households, dishes and servies into the database.

The deploy's migration step runs it (``post_migration_hook``), and
docs/design.md, "The config file", has its rules:

- a new household is created with the guess as its counts and a fresh link;
- an existing one that hasn't answered follows the file's name and guess; one
  that has answered follows only its name;
- a new or changed dish or servies item follows the file, and whoever makes or
  brings it keeps it;
- a household, dish or servies item the file no longer has disappears, and its
  claims go with it;
- a ``reset`` higher than the one last applied first clears every answer,
  claim and link, then applies the file as if for the first time.
"""

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.change_report import ChangeReport
from app.models.config_state import ConfigState
from app.models.dish import Dish, DishGuestCategory
from app.models.guest_category import GuestCategory
from app.models.party import GuestCount, Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.schemas.config_file import (
    DishConfig,
    HouseholdConfig,
    KerstDinerConfig,
    TablewareConfig,
)
from app.services.party_service import new_link_token

_STATE_ID = 1


@dataclass(frozen=True)
class AppliedConfig:
    """What a config created, in config order."""

    parties: list[Party]
    dishes: list[Dish]
    servies: list[TablewareItem]


@dataclass(frozen=True)
class SyncSummary:
    """What a sync did, for the migration step's log."""

    reset: bool
    households: int
    dishes: int
    servies: int


class ConfigSyncService:
    """Applies a config to the database, in the caller's transaction."""

    def __init__(self, db_session: Session) -> None:
        self.db_session = db_session

    def sync(self, config: KerstDinerConfig) -> SyncSummary:
        """Apply ``config``, first clearing everything when its ``reset`` is raised."""
        state = self.db_session.get(ConfigState, _STATE_ID)
        reset = False
        if state is None:
            # The first sync: an empty database, nothing to clear.
            self.db_session.add(ConfigState(id=_STATE_ID, reset_applied=config.reset))
        elif config.reset > state.reset_applied:
            self._clear()
            state.reset_applied = config.reset
            reset = True
        self._apply(config)
        return SyncSummary(
            reset=reset,
            households=len(config.households),
            dishes=len(config.dishes),
            servies=len(config.servies),
        )

    def replace_all(self, config: KerstDinerConfig) -> AppliedConfig:
        """Clear everything, the report queue too, and apply ``config`` as if for the first time.

        The testing endpoint's reset; the deploy never runs it.
        """
        self._clear()
        self.db_session.execute(delete(ChangeReport))
        state = self.db_session.get(ConfigState, _STATE_ID)
        if state is None:
            self.db_session.add(ConfigState(id=_STATE_ID, reset_applied=config.reset))
        else:
            state.reset_applied = config.reset
        self._apply(config)
        return AppliedConfig(
            parties=list(
                self.db_session.scalars(select(Party).order_by(Party.position))
            ),
            dishes=list(self.db_session.scalars(select(Dish).order_by(Dish.position))),
            servies=list(
                self.db_session.scalars(
                    select(TablewareItem).order_by(TablewareItem.position)
                )
            ),
        )

    def _clear(self) -> None:
        """Delete every Party, Dish and Tableware Item: every answer, claim and link."""
        self.db_session.execute(delete(Dish))
        self.db_session.execute(delete(TablewareItem))
        self.db_session.execute(delete(Party))
        # The database cascaded to the Guest Counts and the dishes' groups.
        self.db_session.expire_all()

    def _apply(self, config: KerstDinerConfig) -> None:
        self._remove_missing(config)
        self._apply_households(config.households)
        self._apply_dishes(config.dishes)
        self._apply_tableware(config.servies)
        self.db_session.flush()

    def _remove_missing(self, config: KerstDinerConfig) -> None:
        """Delete what the file no longer names; the database releases its claims."""
        self.db_session.execute(
            delete(Party).where(Party.key.not_in([h.key for h in config.households]))
        )
        self.db_session.execute(
            delete(Dish).where(Dish.key.not_in([d.key for d in config.dishes]))
        )
        self.db_session.execute(
            delete(TablewareItem).where(
                TablewareItem.key.not_in([t.key for t in config.servies])
            )
        )
        self.db_session.expire_all()

    def _apply_households(self, households: list[HouseholdConfig]) -> None:
        existing = {p.key: p for p in self.db_session.scalars(select(Party))}
        for position, household in enumerate(households):
            party = existing.get(household.key)
            if party is None:
                self.db_session.add(
                    Party(
                        key=household.key,
                        name=household.name,
                        position=position,
                        answer=PartyAnswer.UNANSWERED,
                        link_token=new_link_token(),
                        guest_counts=[
                            GuestCount(category=c, people=household.guess.people(c))
                            for c in GuestCategory
                        ],
                    )
                )
                continue
            party.name = household.name
            party.position = position
            if party.answer == PartyAnswer.UNANSWERED:
                for category in GuestCategory:
                    party.set_people(category, household.guess.people(category))

    def _apply_dishes(self, dishes: list[DishConfig]) -> None:
        existing = {d.key: d for d in self.db_session.scalars(select(Dish))}
        for position, config in enumerate(dishes):
            dish = existing.get(config.key)
            if dish is None:
                dish = Dish(key=config.key)
                self.db_session.add(dish)
            dish.name = config.name
            dish.image = config.image
            dish.position = position
            wanted = set(config.categories)
            for row in list(dish.made_for):
                if row.category not in wanted:
                    dish.made_for.remove(row)
            for category in config.categories:
                if category not in dish.categories:
                    dish.made_for.append(DishGuestCategory(category=category))

    def _apply_tableware(self, servies: list[TablewareConfig]) -> None:
        existing = {t.key: t for t in self.db_session.scalars(select(TablewareItem))}
        for position, config in enumerate(servies):
            item = existing.get(config.key)
            if item is None:
                item = TablewareItem(key=config.key)
                self.db_session.add(item)
            item.text = config.text
            item.image = config.image
            item.position = position
