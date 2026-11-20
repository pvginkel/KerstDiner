"""Dish: one dish on the Christmas menu, and who it is made for."""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.guest_category import GuestCategory, guest_category_type
from app.models.party import Party


class Dish(db.Model):  # type: ignore[name-defined]
    """One dish on the menu, made by one Party, or by nobody yet.

    ``image`` is the photo's file name under ``frontend/public/gerechten/``,
    or None for the placeholder.
    """

    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(sa.String(64), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    image: Mapped[str | None] = mapped_column(sa.String(200))
    position: Mapped[int] = mapped_column()
    made_by_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("parties.id", ondelete="SET NULL"), index=True
    )

    made_by: Mapped[Party | None] = relationship()
    made_for: Mapped[list["DishGuestCategory"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DishGuestCategory.category",
    )

    @property
    def categories(self) -> set[GuestCategory]:
        """The Guest Categories the Dish is made for."""
        return {row.category for row in self.made_for}


class DishGuestCategory(db.Model):  # type: ignore[name-defined]
    """A Guest Category a Dish is made for."""

    __tablename__ = "dish_guest_categories"

    dish_id: Mapped[int] = mapped_column(
        sa.ForeignKey("dishes.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[GuestCategory] = mapped_column(
        guest_category_type(), primary_key=True
    )
