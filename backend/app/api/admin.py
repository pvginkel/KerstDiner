"""/admin's endpoints: every household, and replacing a link. Admin role only."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint
from spectree import Response as SpectreeResponse

from app.schemas.common import ApiErrorResponseSchema
from app.schemas.party_schema import (
    AdminPartiesResponse,
    AdminPartyResponse,
    GuestCountsSchema,
)
from app.services.container import ServiceContainer
from app.services.party_service import PartyService
from app.utils.auth import allow_roles
from app.utils.spectree_config import api

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/parties", methods=["GET"])
@allow_roles("admin")
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=AdminPartiesResponse,
        HTTP_401=ApiErrorResponseSchema,
        HTTP_403=ApiErrorResponseSchema,
    )
)
@inject
def list_parties(
    party_service: PartyService = Provide[ServiceContainer.party_service],
) -> Any:
    """Every household with its answer, counts, time answered and link, plus the totals."""
    totals = party_service.totals()
    return AdminPartiesResponse(
        parties=[AdminPartyResponse.of(p) for p in party_service.list_parties()],
        totals=GuestCountsSchema.of(totals.counts),
        people=totals.people,
    ).model_dump(mode="json")


@admin_bp.route("/parties/<int:party_id>/link", methods=["POST"])
@allow_roles("admin")
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=AdminPartyResponse,
        HTTP_401=ApiErrorResponseSchema,
        HTTP_403=ApiErrorResponseSchema,
        HTTP_404=ApiErrorResponseSchema,
    )
)
@inject
def replace_link(
    party_id: int,
    party_service: PartyService = Provide[ServiceContainer.party_service],
) -> Any:
    """Replace the household's link; the old one stops working."""
    party = party_service.replace_link(party_id)
    return AdminPartyResponse.of(party).model_dump(mode="json")
