"""Tableware Item: one lot of tableware the dinner needs (the UI's servies)."""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.party import Party


class TablewareItem(db.Model):  # type: ignore[name-defined]
    """One lot of tableware, such as "20 borden", brought by one Party or nobody yet.

    ``image`` is the photo's file name under ``frontend/public/servies/``, or
    None for the placeholder.
    """

    __tablename__ = "tableware_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(sa.String(64), unique=True)
    text: Mapped[str] = mapped_column(sa.String(200))
    image: Mapped[str | None] = mapped_column(sa.String(200))
    position: Mapped[int] = mapped_column()
    brought_by_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("parties.id", ondelete="SET NULL"), index=True
    )

    brought_by: Mapped[Party | None] = relationship()
