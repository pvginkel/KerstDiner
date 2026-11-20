"""What the config sync last applied. Plumbing, not part of the data model."""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ConfigState(db.Model):  # type: ignore[name-defined]
    """One row: the ``reset`` value the config sync last applied."""

    __tablename__ = "config_state"
    __table_args__ = (sa.CheckConstraint("id = 1", name="ck_config_state_single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reset_applied: Mapped[int] = mapped_column()
