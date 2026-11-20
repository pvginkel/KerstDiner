"""The household endpoints' caller: the Party whose link token the request carries."""

from flask import request

from app.models.party import Party
from app.schemas.party_schema import LINK_TOKEN_HEADER
from app.services.party_service import PartyService


def current_party(party_service: PartyService) -> Party:
    """The Party whose link token the request's ``X-Link-Token`` header carries.

    Raises:
        AuthenticationException: The header is missing, or its token is
            unknown or has been replaced.
    """
    return party_service.get_by_link_token(request.headers.get(LINK_TOKEN_HEADER, ""))
