"""The KerstDiner model: Party, Guest Count, Dish, Tableware Item, and the
report queue and config state beside it.

Adds the entities of docs/design.md's Data model: Party with its Guest Counts
(assertions 1, 2, 11), Dish with the Guest Categories it is made for (7, 12,
13) and the Party that makes it (5, 6), and Tableware Item with the Party that
brings it along (9, 10). The four Guest Categories are a checked string, fixed
in code.

Revision ID: 0001
Revises:
Create Date: 2026-11-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUEST_CATEGORIES = ("vegan", "vegetarisch", "normaal", "kind")
_PARTY_ANSWERS = ("unanswered", "coming", "not_coming")


def _guest_category() -> sa.Enum:
    return sa.Enum(
        *_GUEST_CATEGORIES,
        name="guest_category",
        native_enum=False,
        create_constraint=True,
        length=16,
    )


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "parties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "answer",
            sa.Enum(
                *_PARTY_ANSWERS,
                name="party_answer",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("link_token", sa.String(64), nullable=False, unique=True),
    )
    op.create_table(
        "guest_counts",
        sa.Column(
            "party_id",
            sa.Integer(),
            sa.ForeignKey("parties.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("category", _guest_category(), primary_key=True),
        sa.Column("people", sa.Integer(), nullable=False),
        sa.CheckConstraint("people >= 0", name="ck_guest_counts_people"),
    )
    op.create_table(
        "dishes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("image", sa.String(200), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "made_by_id",
            sa.Integer(),
            sa.ForeignKey("parties.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_dishes_made_by_id", "dishes", ["made_by_id"])
    op.create_table(
        "dish_guest_categories",
        sa.Column(
            "dish_id",
            sa.Integer(),
            sa.ForeignKey("dishes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("category", _guest_category(), primary_key=True),
    )
    op.create_table(
        "tableware_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("text", sa.String(200), nullable=False),
        sa.Column("image", sa.String(200), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "brought_by_id",
            sa.Integer(),
            sa.ForeignKey("parties.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tableware_items_brought_by_id", "tableware_items", ["brought_by_id"]
    )
    op.create_table(
        "change_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "config_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reset_applied", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_config_state_single_row"),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_table("config_state")
    op.drop_table("change_reports")
    op.drop_index("ix_tableware_items_brought_by_id", table_name="tableware_items")
    op.drop_table("tableware_items")
    op.drop_table("dish_guest_categories")
    op.drop_index("ix_dishes_made_by_id", table_name="dishes")
    op.drop_table("dishes")
    op.drop_table("guest_counts")
    op.drop_table("parties")
