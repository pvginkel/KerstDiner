"""The dish tiles: ``/api/dishes``, called with the household's link token."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint
from spectree import Response as SpectreeResponse

from app.api.link_token import current_party
from app.schemas.common import ApiErrorResponseSchema
from app.schemas.dish_schema import DishListResponse, DishResponse
from app.schemas.party_schema import LinkTokenHeaders
from app.services.container import ServiceContainer
from app.services.dish_service import DishService
from app.services.party_service import PartyService
from app.utils.auth import public
from app.utils.spectree_config import api

dishes_bp = Blueprint("dishes", __name__, url_prefix="/dishes")

_CLAIM_RESPONSES = SpectreeResponse(
    HTTP_200=DishResponse,
    HTTP_400=ApiErrorResponseSchema,
    HTTP_401=ApiErrorResponseSchema,
    HTTP_404=ApiErrorResponseSchema,
    HTTP_409=ApiErrorResponseSchema,
)


@dishes_bp.route("", methods=["GET"])
@public
@api.validate(
    headers=LinkTokenHeaders,
    resp=SpectreeResponse(
        HTTP_200=DishListResponse,
        HTTP_400=ApiErrorResponseSchema,
        HTTP_401=ApiErrorResponseSchema,
    ),
)
@inject
def list_dishes(
    party_service: PartyService = Provide[ServiceContainer.party_service],
    dish_service: DishService = Provide[ServiceContainer.dish_service],
) -> Any:
    """Every dish: name, photo, how many it is for, and who makes it."""
    party = current_party(party_service)
    dishes = [DishResponse.of(view) for view in dish_service.list_dishes(party)]
    return DishListResponse(dishes=dishes).model_dump(mode="json")


@dishes_bp.route("/<int:dish_id>/claim", methods=["PUT"])
@public
@api.validate(headers=LinkTokenHeaders, resp=_CLAIM_RESPONSES)
@inject
def claim_dish(
    dish_id: int,
    party_service: PartyService = Provide[ServiceContainer.party_service],
    dish_service: DishService = Provide[ServiceContainer.dish_service],
) -> Any:
    """Take the dish: 409 when another household makes it, or this one has not said it comes."""
    party = current_party(party_service)
    return DishResponse.of(dish_service.claim(party, dish_id)).model_dump(mode="json")


@dishes_bp.route("/<int:dish_id>/claim", methods=["DELETE"])
@public
@api.validate(headers=LinkTokenHeaders, resp=_CLAIM_RESPONSES)
@inject
def release_dish(
    dish_id: int,
    party_service: PartyService = Provide[ServiceContainer.party_service],
    dish_service: DishService = Provide[ServiceContainer.dish_service],
) -> Any:
    """Give the dish back: 409 when another household makes it."""
    party = current_party(party_service)
    return DishResponse.of(dish_service.release(party, dish_id)).model_dump(mode="json")
