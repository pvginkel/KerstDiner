"""The four Guest Categories, fixed in code (docs/design.md, Data model)."""

from enum import StrEnum

import sqlalchemy as sa


class GuestCategory(StrEnum):
    """A kind of guest the dinner caters for.

    ``kind`` is a child under 6, who gets a kindermenu that the family arranges
    apart: no Dish is made for it. An older child counts as vegan,
    vegetarisch or normaal, as an adult does.
    """

    VEGAN = "vegan"
    VEGETARISCH = "vegetarisch"
    NORMAAL = "normaal"
    KIND = "kind"


DISH_CATEGORIES: tuple[GuestCategory, ...] = (
    GuestCategory.VEGAN,
    GuestCategory.VEGETARISCH,
    GuestCategory.NORMAAL,
)
"""The Guest Categories a Dish can be made for, in display order: all but kind."""


def guest_category_type() -> sa.Enum:
    """The column type of a Guest Category: a string the database checks."""
    return sa.Enum(
        GuestCategory,
        name="guest_category",
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
