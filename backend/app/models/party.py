"""Party: one household invited to the dinner, and its Guest Counts."""

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.guest_category import GuestCategory, guest_category_type


class PartyAnswer(StrEnum):
    """A Party's answer: nog geen antwoord, komt or komt niet."""

    UNANSWERED = "unanswered"
    COMING = "coming"
    NOT_COMING = "not_coming"


class Party(db.Model):  # type: ignore[name-defined]
    """One household invited to the dinner (the config's and the UI's huishouden).

    ``key`` is the config's key, which never changes; ``position`` is its place
    in the config, which orders /admin. ``link_token`` is the secret of the
    household's link, ``/p/<link_token>``.
    """

    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(sa.String(64), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    position: Mapped[int] = mapped_column()
    answer: Mapped[PartyAnswer] = mapped_column(
        sa.Enum(
            PartyAnswer,
            name="party_answer",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda members: [member.value for member in members],
            validate_strings=True,
        ),
        default=PartyAnswer.UNANSWERED,
    )
    answered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    link_token: Mapped[str] = mapped_column(sa.String(64), unique=True)

    guest_counts: Mapped[list["GuestCount"]] = relationship(
        back_populates="party",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GuestCount.category",
    )

    def people(self, category: GuestCategory) -> int:
        """The number of people of ``category`` the Party brings."""
        for count in self.guest_counts:
            if count.category == category:
                return count.people
        return 0

    def set_people(self, category: GuestCategory, people: int) -> None:
        """Set the number of people of ``category`` the Party brings."""
        for count in self.guest_counts:
            if count.category == category:
                count.people = people
                return
        self.guest_counts.append(GuestCount(category=category, people=people))


class GuestCount(db.Model):  # type: ignore[name-defined]
    """The number of people of one Guest Category that one Party brings."""

    __tablename__ = "guest_counts"
    __table_args__ = (sa.CheckConstraint("people >= 0", name="ck_guest_counts_people"),)

    party_id: Mapped[int] = mapped_column(
        sa.ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[GuestCategory] = mapped_column(
        guest_category_type(), primary_key=True
    )
    people: Mapped[int] = mapped_column()

    party: Mapped[Party] = relationship(back_populates="guest_counts")
