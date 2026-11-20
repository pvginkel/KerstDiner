"""KerstDiner's client of the notification bridge (pvginkel/Notifications).

The bridge sends a submit to the Telegram chat of the registration whose bearer
token it carries, here ``kerstdiner``'s. Its ``url`` becomes the message's
*Open* button. A ``200`` says the body was valid and every channel was tried,
not that anything was delivered: the per-channel result says that, and a
channel's error in it is a failed send.
"""

import logging
from typing import Any

import requests

from app.core_exceptions import ExternalServiceException
from app.services.health_service import CheckResult, CheckStatus, HealthService

logger = logging.getLogger(__name__)

# Above the bridge's slowest answer: it gives a Telegram call up after a 10 s
# stall and makes up to four per chat.
_CONNECT_TIMEOUT_SECONDS = 10
_READ_TIMEOUT_SECONDS = 120
_READINESS_TIMEOUT_SECONDS = 2

_SUBMIT_OPERATION = "send a change report to the notification bridge"


class NotificationBridgeClient:
    """Submits messages under one registration's bearer token."""

    def __init__(
        self, base_url: str, token: str, health_service: HealthService
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        if self.is_configured:
            # Not critical: households can answer and take dishes without it,
            # and their reports wait in the queue.
            health_service.register_check(
                "notification_bridge", self.check_readiness, critical=False
            )

    @property
    def is_configured(self) -> bool:
        """Whether the deploy gave the bridge's URL and token."""
        return bool(self._base_url and self._token)

    def check_readiness(self) -> CheckResult:
        """Readiness check: the bridge answers its ``/healthz``, which takes no token."""
        response = requests.get(
            f"{self._base_url}/healthz", timeout=_READINESS_TIMEOUT_SECONDS
        )
        if response.status_code != 200:
            return CheckResult(
                CheckStatus.ERROR, f"the bridge answered {response.status_code}"
            )
        return CheckResult(CheckStatus.OK)

    def submit(self, message: str, url: str | None = None) -> None:
        """Send ``message`` (Markdown) to the registration's Telegram chat.

        Raises:
            ExternalServiceException: The bridge did not answer, refused the
                submit, or Telegram did not take the message.
        """
        body: dict[str, Any] = {"message": message}
        if url is not None:
            body["url"] = url
        try:
            response = requests.post(
                f"{self._base_url}/v1/submit",
                json=body,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS),
            )
        except requests.RequestException as error:
            raise ExternalServiceException(
                _SUBMIT_OPERATION, f"the bridge did not answer: {error}"
            ) from error

        if response.status_code != 200:
            raise ExternalServiceException(
                _SUBMIT_OPERATION,
                f"the bridge answered {response.status_code}: {_error_of(response)}",
            )
        try:
            result = response.json()
        except ValueError as error:
            raise ExternalServiceException(
                _SUBMIT_OPERATION, "the bridge's answer is not JSON"
            ) from error
        telegram = result.get("telegram") if isinstance(result, dict) else None
        if telegram != "ok":
            raise ExternalServiceException(
                _SUBMIT_OPERATION,
                f"Telegram did not take it: {telegram or 'the registration has no Telegram channel'}",
            )


def _error_of(response: requests.Response) -> str:
    """The bridge's own ``error`` from a refusal, or the start of the body."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return str(body["error"])
    return response.text[:200]
