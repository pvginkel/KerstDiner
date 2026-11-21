"""The report queue: a household's changes, waiting for its next Telegram message.

Plumbing, not part of the data model (docs/design.md, Change reports).
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.party import Party


class ChangeReport(db.Model):  # type: ignore[name-defined]
    """One change of ``party``, a line of its next message; ``sent_at`` is None until it went out.

    ``message`` is the line as Markdown, without the household's name, which
    heads the message it goes out in.
    """

    __tablename__ = "change_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int] = mapped_column(
        sa.ForeignKey("parties.id", ondelete="CASCADE"), index=True
    )
    message: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    party: Mapped[Party] = relationship()
