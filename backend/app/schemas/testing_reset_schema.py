"""Schemas of the testing endpoint that resets the state (``POST /api/testing/reset``)."""

from pydantic import BaseModel, Field


class ResetPartyResponse(BaseModel):
    """A household the reset created, with its link token."""

    id: int
    key: str
    name: str
    link_token: str


class ResetItemResponse(BaseModel):
    """A dish or servies item the reset created."""

    id: int
    key: str


class TestingResetResponse(BaseModel):
    """What the reset created, in config order."""

    parties: list[ResetPartyResponse] = Field(description="Every household")
    dishes: list[ResetItemResponse] = Field(description="Every dish")
    servies: list[ResetItemResponse] = Field(description="Every servies item")
