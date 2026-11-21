"""Servies: its tiles, and taking or giving an item back, as a household does a dish."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    ClaimTakenException,
    InvalidOperationException,
    RecordNotFoundException,
)
from app.models.party import Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.services.dish_service import ClaimStatus, claim_status
from app.services.report_service import ReportQueue
from app.services.report_texts import (
    tableware_released_report,
    tableware_taken_report,
)


@dataclass(frozen=True)
class TablewareView:
    """A Tableware Item as one household sees it."""

    item: TablewareItem
    status: ClaimStatus
    brought_by_name: str | None


class TablewareService:
    """The servies tiles, and a household's claims on them."""

    def __init__(self, db_session: Session, report_queue: ReportQueue) -> None:
        self.db_session = db_session
        self._report_queue = report_queue

    def list_items(self, party: Party) -> list[TablewareView]:
        """Every Tableware Item in config order, as ``party`` sees it."""
        items = self.db_session.scalars(
            select(TablewareItem).order_by(TablewareItem.position)
        )
        return [self._view(item, party) for item in items]

    def claim(self, party: Party, item_id: int) -> TablewareView:
        """``party`` takes the item; no change when it has it already.

        Raises:
            RecordNotFoundException: No Tableware Item has ``item_id``.
            InvalidOperationException: The Party has not said it is coming.
            ClaimTakenException: Another Party brings it.
        """
        item = self._lock(item_id)
        if item.brought_by_id != party.id:
            if party.answer != PartyAnswer.COMING:
                raise InvalidOperationException(
                    f"take servies {item.text}",
                    f"{party.name} has not said it is coming",
                )
            if item.brought_by_id is not None:
                raise ClaimTakenException(
                    f"Dit servies is net door {self._bringer_name(item)} gekozen"
                )
            item.brought_by_id = party.id
            self.db_session.flush()
            self._report_queue.queue(party, tableware_taken_report(item))
        return self._view(item, party)

    def release(self, party: Party, item_id: int) -> TablewareView:
        """``party`` gives the item back; no change when nobody brings it.

        Raises:
            RecordNotFoundException: No Tableware Item has ``item_id``.
            ClaimTakenException: Another Party brings it.
        """
        item = self._lock(item_id)
        if item.brought_by_id is not None:
            if item.brought_by_id != party.id:
                raise ClaimTakenException(
                    f"Dit servies is door {self._bringer_name(item)} gekozen"
                )
            item.brought_by_id = None
            self.db_session.flush()
            self._report_queue.queue(party, tableware_released_report(item))
        return self._view(item, party)

    def _lock(self, item_id: int) -> TablewareItem:
        """The item, its row locked until the transaction ends: two claims take turns."""
        item = self.db_session.scalars(
            select(TablewareItem)
            .where(TablewareItem.id == item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if item is None:
            raise RecordNotFoundException("Tableware Item", item_id)
        return item

    def _bringer_name(self, item: TablewareItem) -> str | None:
        if item.brought_by_id is None:
            return None
        bringer = self.db_session.get(Party, item.brought_by_id)
        return bringer.name if bringer is not None else None

    def _view(self, item: TablewareItem, party: Party) -> TablewareView:
        return TablewareView(
            item=item,
            status=claim_status(item.brought_by_id, party),
            brought_by_name=self._bringer_name(item),
        )
