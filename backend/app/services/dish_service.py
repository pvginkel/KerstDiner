"""Dishes: the tiles of "Wat nemen jullie mee?", and taking or giving one back."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    ClaimTakenException,
    InvalidOperationException,
    RecordNotFoundException,
)
from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer
from app.services.party_service import category_totals
from app.services.report_service import ReportQueue
from app.services.report_texts import dish_released_report, dish_taken_report

ClaimStatus = Literal["free", "yours", "taken"]
"""A tile's state for the household that looks: nog vrij, yours, or another's."""


def claim_status(maker_id: int | None, party: Party) -> ClaimStatus:
    """The tile's state for ``party`` when ``maker_id`` makes or brings it."""
    if maker_id is None:
        return "free"
    return "yours" if maker_id == party.id else "taken"


@dataclass(frozen=True)
class DishView:
    """A Dish as one household sees it."""

    dish: Dish
    people: int
    status: ClaimStatus
    made_by_name: str | None


class DishService:
    """The dish tiles, and a household's claims on them."""

    def __init__(self, db_session: Session, report_queue: ReportQueue) -> None:
        self.db_session = db_session
        self._report_queue = report_queue

    def list_dishes(self, party: Party) -> list[DishView]:
        """Every Dish in config order, as ``party`` sees it."""
        totals = category_totals(self.db_session)
        dishes = self.db_session.scalars(select(Dish).order_by(Dish.position))
        return [self._view(dish, party, totals) for dish in dishes]

    def claim(self, party: Party, dish_id: int) -> DishView:
        """``party`` takes the dish; no change when it has it already.

        Raises:
            RecordNotFoundException: No Dish has ``dish_id``.
            InvalidOperationException: The Party has not said it is coming.
            ClaimTakenException: Another Party makes it.
        """
        dish = self._lock(dish_id)
        if dish.made_by_id != party.id:
            if party.answer != PartyAnswer.COMING:
                raise InvalidOperationException(
                    f"take dish {dish.name}", f"{party.name} has not said it is coming"
                )
            if dish.made_by_id is not None:
                raise ClaimTakenException(
                    f"Dit gerecht is net door {self._maker_name(dish)} gekozen"
                )
            dish.made_by_id = party.id
            self.db_session.flush()
            self._report_queue.queue(dish_taken_report(party, dish))
        return self._view(dish, party, category_totals(self.db_session))

    def release(self, party: Party, dish_id: int) -> DishView:
        """``party`` gives the dish back; no change when nobody makes it.

        Raises:
            RecordNotFoundException: No Dish has ``dish_id``.
            ClaimTakenException: Another Party makes it.
        """
        dish = self._lock(dish_id)
        if dish.made_by_id is not None:
            if dish.made_by_id != party.id:
                raise ClaimTakenException(
                    f"Dit gerecht is door {self._maker_name(dish)} gekozen"
                )
            dish.made_by_id = None
            self.db_session.flush()
            self._report_queue.queue(dish_released_report(party, dish))
        return self._view(dish, party, category_totals(self.db_session))

    def _lock(self, dish_id: int) -> Dish:
        """The Dish, its row locked until the transaction ends: two claims take turns."""
        dish = self.db_session.scalars(
            select(Dish)
            .where(Dish.id == dish_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if dish is None:
            raise RecordNotFoundException("Dish", dish_id)
        return dish

    def _maker_name(self, dish: Dish) -> str | None:
        if dish.made_by_id is None:
            return None
        maker = self.db_session.get(Party, dish.made_by_id)
        return maker.name if maker is not None else None

    def _view(
        self, dish: Dish, party: Party, totals: dict[GuestCategory, int]
    ) -> DishView:
        return DishView(
            dish=dish,
            people=sum(totals[c] for c in dish.categories),
            status=claim_status(dish.made_by_id, party),
            made_by_name=self._maker_name(dish),
        )
