"""The Playwright specs' reset: ``POST /api/testing/reset``. Testing mode only."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request
from spectree import Response as SpectreeResponse

from app.schemas.common import ApiErrorResponseSchema
from app.schemas.config_file import KerstDinerConfig
from app.schemas.testing_reset_schema import (
    ResetItemResponse,
    ResetPartyResponse,
    TestingResetResponse,
)
from app.services.config_sync_service import ConfigSyncService
from app.services.container import ServiceContainer
from app.utils.auth import public
from app.utils.spectree_config import api

testing_reset_bp = Blueprint("testing_reset", __name__, url_prefix="/testing")


@testing_reset_bp.before_request
def check_testing_mode() -> Any:
    """Reject requests when the server is not running in testing mode."""
    from app.api.testing_guard import reject_if_not_testing

    return reject_if_not_testing()


@testing_reset_bp.route("/reset", methods=["POST"])
@public
@api.validate(
    json=KerstDinerConfig,
    resp=SpectreeResponse(
        HTTP_200=TestingResetResponse, HTTP_400=ApiErrorResponseSchema
    ),
)
@inject
def reset(
    config_sync_service: ConfigSyncService = Provide[
        ServiceContainer.config_sync_service
    ],
) -> Any:
    """Wipe every household, dish, servies item and report, and apply the config given.

    The body has the config file's shape, as JSON. Every household gets a new
    link token, which the answer carries.
    """
    config = KerstDinerConfig.model_validate(request.get_json())
    applied = config_sync_service.replace_all(config)
    return TestingResetResponse(
        parties=[
            ResetPartyResponse(id=p.id, key=p.key, name=p.name, link_token=p.link_token)
            for p in applied.parties
        ],
        dishes=[ResetItemResponse(id=d.id, key=d.key) for d in applied.dishes],
        servies=[ResetItemResponse(id=t.id, key=t.key) for t in applied.servies],
    ).model_dump(mode="json")
