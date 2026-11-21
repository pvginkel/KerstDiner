"""The report queue names the household of each change.

A household's changes go out together, in one message headed by its name
(docs/design.md, Change reports), so each queued change carries its Party.
The reports already sent are dropped: they are plumbing that has done its job.
A report still waiting is a full sentence that starts with its household's
name, and gets that household; one that matches none stops the upgrade, rather
than be lost.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.execute("DELETE FROM change_reports WHERE sent_at IS NOT NULL")
    op.add_column(
        "change_reports",
        sa.Column(
            "party_id",
            sa.Integer(),
            sa.ForeignKey("parties.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    # The longest name that starts the message, so that "Familie Jansen" never
    # takes a report of "Familie Jansen-de Vries".
    op.execute(
        """
        UPDATE change_reports AS r
        SET party_id = (
            SELECT p.id FROM parties AS p
            WHERE starts_with(r.message, p.name || ' ')
            ORDER BY length(p.name) DESC
            LIMIT 1
        )
        """
    )
    op.alter_column("change_reports", "party_id", nullable=False)
    op.create_index("ix_change_reports_party_id", "change_reports", ["party_id"])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("ix_change_reports_party_id", table_name="change_reports")
    op.drop_column("change_reports", "party_id")
