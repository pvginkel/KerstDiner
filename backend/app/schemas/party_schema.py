"""Schemas of a household's own endpoints (``/api/party``) and the admin's."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer

PartyAnswerValue = Literal["unanswered", "coming", "not_coming"]
"""nog geen antwoord, komt, komt niet."""

LINK_TOKEN_HEADER = "X-Link-Token"
"""The header a household's requests carry its link token in."""

People = Annotated[int, Field(ge=0, le=99)]


class LinkTokenHeaders(BaseModel):
    """The household's link token, from its link ``/p/<token>``.

    Optional in the OpenAPI document, so that the generated client's hooks,
    which pass no headers, type-check: the frontend adds it to every request
    of the household page. A request without it answers 401, as one with an
    unknown token does.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    link_token: str | None = Field(
        default=None,
        alias="X-Link-Token",
        max_length=64,
        description="The household's link token, from its link /p/<token>",
    )


class GuestCountsSchema(BaseModel):
    """How many people of each Guest Category a household brings."""

    model_config = ConfigDict(extra="forbid")

    vegan: People = Field(description="Vegan")
    vegetarisch: People = Field(description="Vegetarisch")
    normaal: People = Field(description="Eet alles")
    kind: People = Field(description="Kindermenu <6jr: children under 6")

    @classmethod
    def of(cls, counts: dict[GuestCategory, int]) -> "GuestCountsSchema":
        """The schema of a count per Guest Category."""
        return cls(
            **{category.value: counts.get(category, 0) for category in GuestCategory}
        )

    @classmethod
    def of_party(cls, party: Party) -> "GuestCountsSchema":
        """The Party's Guest Counts."""
        return cls.of({category: party.people(category) for category in GuestCategory})

    def as_counts(self) -> dict[GuestCategory, int]:
        """A count per Guest Category."""
        return {
            category: int(getattr(self, category.value)) for category in GuestCategory
        }

    @property
    def people(self) -> int:
        """Everyone, the young children included."""
        return self.vegan + self.vegetarisch + self.normaal + self.kind


class PartyResponse(BaseModel):
    """A household as it sees itself."""

    id: int = Field(description="The household's id")
    name: str = Field(description="Its name, such as Familie Jansen")
    answer: PartyAnswerValue = Field(description="Its answer, or unanswered")
    counts: GuestCountsSchema = Field(
        description="Who it brings: the operator's guess until it answers"
    )
    people: int = Field(description="Everyone it brings, the young children included")
    answered_at: datetime | None = Field(description="When it last changed its answer")

    @classmethod
    def of(cls, party: Party) -> "PartyResponse":
        """The response for ``party``."""
        counts = GuestCountsSchema.of_party(party)
        return cls(
            id=party.id,
            name=party.name,
            answer=party.answer.value,
            counts=counts,
            people=counts.people,
            answered_at=party.answered_at,
        )


class PartyAnswerRequest(BaseModel):
    """A household's answer: coming with who it brings, or not coming."""

    model_config = ConfigDict(extra="forbid")

    answer: Literal["coming", "not_coming"] = Field(description="komt or komt niet")
    counts: GuestCountsSchema | None = Field(
        default=None,
        description="Who it brings; required when coming, ignored when not",
    )

    @model_validator(mode="after")
    def _counts_when_coming(self) -> Self:
        if self.answer == "coming":
            if self.counts is None:
                raise ValueError("counts are required when coming")
            if self.counts.people == 0:
                raise ValueError("a household that comes brings at least one person")
        return self

    @property
    def party_answer(self) -> PartyAnswer:
        """The answer as the model's value."""
        return PartyAnswer(self.answer)


class AdminPartyResponse(PartyResponse):
    """A household as /admin sees it, with its link."""

    link_token: str = Field(description="Its link token: the link is /p/<link_token>")

    @classmethod
    def of(cls, party: Party) -> "AdminPartyResponse":
        """The response for ``party``."""
        return cls(**PartyResponse.of(party).model_dump(), link_token=party.link_token)


class AdminPartiesResponse(BaseModel):
    """Every household in config order, and the totals the dish tiles use."""

    parties: list[AdminPartyResponse] = Field(
        description="Every household, in config order"
    )
    totals: GuestCountsSchema = Field(
        description="Who every household brings, the guesses of those yet to answer included"
    )
    people: int = Field(description="Everyone who comes, the young children included")
