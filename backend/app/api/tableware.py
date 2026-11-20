"""The servies tiles: ``/api/tableware``, called with the household's link token."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint
from spectree import Response as SpectreeResponse

from app.api.link_token import current_party
from app.schemas.common import ApiErrorResponseSchema
from app.schemas.dish_schema import TablewareListResponse, TablewareResponse
from app.schemas.party_schema import LinkTokenHeaders
from app.services.container import ServiceContainer
from app.services.party_service import PartyService
from app.services.tableware_service import TablewareService
from app.utils.auth import public
from app.utils.spectree_config import api

tableware_bp = Blueprint("tableware", __name__, url_prefix="/tableware")

_CLAIM_RESPONSES = SpectreeResponse(
    HTTP_200=TablewareResponse,
    HTTP_400=ApiErrorResponseSchema,
    HTTP_401=ApiErrorResponseSchema,
    HTTP_404=ApiErrorResponseSchema,
    HTTP_409=ApiErrorResponseSchema,
)


@tableware_bp.route("", methods=["GET"])
@public
@api.validate(
    headers=LinkTokenHeaders,
    resp=SpectreeResponse(
        HTTP_200=TablewareListResponse,
        HTTP_400=ApiErrorResponseSchema,
        HTTP_401=ApiErrorResponseSchema,
    ),
)
@inject
def list_tableware(
    party_service: PartyService = Provide[ServiceContainer.party_service],
    tableware_service: TablewareService = Provide[ServiceContainer.tableware_service],
) -> Any:
    """Every servies item: text, photo, and who brings it."""
    party = current_party(party_service)
    items = [TablewareResponse.of(view) for view in tableware_service.list_items(party)]
    return TablewareListResponse(items=items).model_dump(mode="json")


@tableware_bp.route("/<int:item_id>/claim", methods=["PUT"])
@public
@api.validate(headers=LinkTokenHeaders, resp=_CLAIM_RESPONSES)
@inject
def claim_tableware(
    item_id: int,
    party_service: PartyService = Provide[ServiceContainer.party_service],
    tableware_service: TablewareService = Provide[ServiceContainer.tableware_service],
) -> Any:
    """Take the item: 409 when another household brings it, or this one has not said it comes."""
    party = current_party(party_service)
    view = tableware_service.claim(party, item_id)
    return TablewareResponse.of(view).model_dump(mode="json")


@tableware_bp.route("/<int:item_id>/claim", methods=["DELETE"])
@public
@api.validate(headers=LinkTokenHeaders, resp=_CLAIM_RESPONSES)
@inject
def release_tableware(
    item_id: int,
    party_service: PartyService = Provide[ServiceContainer.party_service],
    tableware_service: TablewareService = Provide[ServiceContainer.tableware_service],
) -> Any:
    """Give the item back: 409 when another household brings it."""
    party = current_party(party_service)
    view = tableware_service.release(party, item_id)
    return TablewareResponse.of(view).model_dump(mode="json")
