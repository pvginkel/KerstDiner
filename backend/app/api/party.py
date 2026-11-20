"""A household's own answer: ``/api/party``, called with its link token."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request
from spectree import Response as SpectreeResponse

from app.api.link_token import current_party
from app.schemas.common import ApiErrorResponseSchema
from app.schemas.party_schema import LinkTokenHeaders, PartyAnswerRequest, PartyResponse
from app.services.container import ServiceContainer
from app.services.party_service import PartyService
from app.utils.auth import public
from app.utils.spectree_config import api

party_bp = Blueprint("party", __name__, url_prefix="/party")


@party_bp.route("", methods=["GET"])
@public
@api.validate(
    headers=LinkTokenHeaders,
    resp=SpectreeResponse(
        HTTP_200=PartyResponse,
        HTTP_400=ApiErrorResponseSchema,
        HTTP_401=ApiErrorResponseSchema,
    ),
)
@inject
def get_party(
    party_service: PartyService = Provide[ServiceContainer.party_service],
) -> Any:
    """The household, its answer and who it brings."""
    party = current_party(party_service)
    return PartyResponse.of(party).model_dump(mode="json")


@party_bp.route("/answer", methods=["PUT"])
@public
@api.validate(
    headers=LinkTokenHeaders,
    json=PartyAnswerRequest,
    resp=SpectreeResponse(
        HTTP_200=PartyResponse,
        HTTP_400=ApiErrorResponseSchema,
        HTTP_401=ApiErrorResponseSchema,
    ),
)
@inject
def save_answer(
    party_service: PartyService = Provide[ServiceContainer.party_service],
) -> Any:
    """Save komt with who comes, or komt niet; declining releases the household's dishes and servies."""
    party = current_party(party_service)
    data = PartyAnswerRequest.model_validate(request.get_json())
    counts = data.counts.as_counts() if data.counts is not None else {}
    party = party_service.save_answer(party, data.party_answer, counts)
    return PartyResponse.of(party).model_dump(mode="json")
