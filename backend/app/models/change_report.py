"""The report queue: one Telegram message per change a household saves.

Plumbing, not part of the data model (docs/design.md, Change reports).
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ChangeReport(db.Model):  # type: ignore[name-defined]
    """A queued message, sent in ``id`` order; ``sent_at`` is None until it went out."""

    __tablename__ = "change_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
