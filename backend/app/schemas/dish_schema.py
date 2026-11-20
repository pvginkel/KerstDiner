"""Schemas of the dish and servies tiles (``/api/dishes``, ``/api/tableware``)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.dish_service import DishView
from app.services.tableware_service import TablewareView

ClaimStatusValue = Literal["free", "yours", "taken"]
"""A tile's state for the household that looks: nog vrij, its own, or another's."""


class DishResponse(BaseModel):
    """A dish tile."""

    id: int = Field(description="The dish's id")
    name: str = Field(description="Its name, such as Pompoensoep")
    image: str | None = Field(
        description="Its photo's file name under /gerechten/, or null for the placeholder"
    )
    people: int = Field(
        description="How many it is for: vegan, vegetarisch and eet alles as it is made for them"
    )
    status: ClaimStatusValue = Field(
        description="free, yours, or taken by another household"
    )
    made_by: str | None = Field(description="The name of the household that makes it")

    @classmethod
    def of(cls, view: DishView) -> "DishResponse":
        """The tile of ``view``."""
        return cls(
            id=view.dish.id,
            name=view.dish.name,
            image=view.dish.image,
            people=view.people,
            status=view.status,
            made_by=view.made_by_name,
        )


class DishListResponse(BaseModel):
    """Every dish, in config order."""

    dishes: list[DishResponse] = Field(description="Every dish, in config order")


class TablewareResponse(BaseModel):
    """A servies tile."""

    id: int = Field(description="The item's id")
    text: str = Field(description='What it is, such as "20 borden"')
    image: str | None = Field(
        description="Its photo's file name under /servies/, or null for the placeholder"
    )
    status: ClaimStatusValue = Field(
        description="free, yours, or taken by another household"
    )
    brought_by: str | None = Field(
        description="The name of the household that brings it"
    )

    @classmethod
    def of(cls, view: TablewareView) -> "TablewareResponse":
        """The tile of ``view``."""
        return cls(
            id=view.item.id,
            text=view.item.text,
            image=view.item.image,
            status=view.status,
            brought_by=view.brought_by_name,
        )


class TablewareListResponse(BaseModel):
    """Every servies item, in config order."""

    items: list[TablewareResponse] = Field(
        description="Every servies item, in config order"
    )
