"""Parties: a household's answer, who it brings, and its link."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.exceptions import (
    AuthenticationException,
    InvalidOperationException,
    RecordNotFoundException,
)
from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import GuestCount, Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.services.report_service import ReportQueue
from app.services.report_texts import attendance_report

UNKNOWN_LINK_MESSAGE = "Gebruik de persoonlijke link uit je e-mail"


def new_link_token() -> str:
    """A link token: 128 random bits, URL-safe."""
    return secrets.token_urlsafe(16)


def category_totals(db_session: Session) -> dict[GuestCategory, int]:
    """Every Party's Guest Counts summed per Guest Category, guesses included."""
    totals = dict.fromkeys(GuestCategory, 0)
    rows = db_session.execute(
        select(GuestCount.category, func.sum(GuestCount.people)).group_by(
            GuestCount.category
        )
    )
    for category, people in rows:
        totals[category] = int(people or 0)
    return totals


@dataclass(frozen=True)
class PartyTotals:
    """The people every Party brings, per Guest Category and in all."""

    counts: dict[GuestCategory, int]

    @property
    def people(self) -> int:
        """Everyone who comes, the young children included."""
        return sum(self.counts.values())


class PartyService:
    """A household's own answer, and the admin's view of every household."""

    def __init__(self, db_session: Session, report_queue: ReportQueue) -> None:
        self.db_session = db_session
        self._report_queue = report_queue

    def get_by_link_token(self, link_token: str) -> Party:
        """The Party whose link carries ``link_token``.

        Raises:
            AuthenticationException: The token is empty, or no Party has it:
                it is unknown or has been replaced.
        """
        party = (
            self.db_session.scalars(
                select(Party).where(Party.link_token == link_token)
            ).first()
            if link_token
            else None
        )
        if party is None:
            raise AuthenticationException(UNKNOWN_LINK_MESSAGE)
        return party

    def save_answer(
        self,
        party: Party,
        answer: PartyAnswer,
        counts: dict[GuestCategory, int],
    ) -> Party:
        """Save the Party's answer and, when it comes, who it brings.

        Declining sets every Guest Count to zero and releases the Party's
        dishes and servies. A save that changes nothing changes nothing, and
        is not reported; any other is reported.

        Raises:
            InvalidOperationException: ``answer`` is ``unanswered``, which a
                Party cannot give.
        """
        if answer == PartyAnswer.UNANSWERED:
            raise InvalidOperationException(
                f"save the answer of {party.name}", "'unanswered' is no answer"
            )
        if answer == PartyAnswer.NOT_COMING:
            new_counts = dict.fromkeys(GuestCategory, 0)
            self._release_everything(party)
        else:
            new_counts = {c: counts.get(c, 0) for c in GuestCategory}

        unchanged = party.answer == answer and all(
            party.people(c) == new_counts[c] for c in GuestCategory
        )
        if unchanged:
            return party

        party.answer = answer
        for category, people in new_counts.items():
            party.set_people(category, people)
        party.answered_at = datetime.now(UTC)
        self.db_session.flush()
        self._report_queue.queue(attendance_report(party))
        return party

    def list_parties(self) -> list[Party]:
        """Every Party, in config order."""
        return list(self.db_session.scalars(select(Party).order_by(Party.position)))

    def totals(self) -> PartyTotals:
        """The people every Party brings, guesses included, as the dish tiles count them."""
        return PartyTotals(counts=category_totals(self.db_session))

    def replace_link(self, party_id: int) -> Party:
        """Give the Party a new link; the old one stops working.

        Raises:
            RecordNotFoundException: No Party has ``party_id``.
        """
        party = self.db_session.get(Party, party_id)
        if party is None:
            raise RecordNotFoundException("Party", party_id)
        party.link_token = new_link_token()
        self.db_session.flush()
        return party

    def _release_everything(self, party: Party) -> None:
        self.db_session.execute(
            update(Dish).where(Dish.made_by_id == party.id).values(made_by_id=None)
        )
        self.db_session.execute(
            update(TablewareItem)
            .where(TablewareItem.brought_by_id == party.id)
            .values(brought_by_id=None)
        )
