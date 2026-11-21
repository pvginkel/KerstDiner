"""Tests of the notification bridge client, against the served stand-in."""

import socket
from collections.abc import Generator

import pytest
from flask import Flask

from app.config import Settings
from app.core_exceptions import ExternalServiceException
from app.services.health_service import CheckStatus, HealthService
from app.services.notification_bridge_client import NotificationBridgeClient
from app.utils.lifecycle_coordinator import LifecycleCoordinator
from tests.support.fake_notification_bridge import (
    FAILURE_TELEGRAM_ERROR,
    REGISTRATION_TOKEN,
    FakeNotificationBridge,
)


@pytest.fixture
def bridge() -> Generator[FakeNotificationBridge]:
    with FakeNotificationBridge() as served:
        yield served


@pytest.fixture
def health_service(test_settings: Settings) -> HealthService:
    """A health service of its own, so no check lands on the app's."""
    return HealthService(
        lifecycle_coordinator=LifecycleCoordinator(graceful_shutdown_timeout=1),
        settings=test_settings,
    )


@pytest.fixture
def bridge_client(
    bridge: FakeNotificationBridge, health_service: HealthService
) -> NotificationBridgeClient:
    return NotificationBridgeClient(bridge.url, REGISTRATION_TOKEN, health_service)


def _unused_port_url() -> str:
    """The base URL of a port nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}"


class TestNotificationBridgeClient:
    def test_is_configured_with_url_and_token(
        self, health_service: HealthService
    ) -> None:
        client = NotificationBridgeClient("http://bridge:8090", "t", health_service)

        assert client.is_configured is True

    @pytest.mark.parametrize(
        ("base_url", "token"),
        [("", ""), ("http://bridge:8090", ""), ("", "token")],
    )
    def test_is_not_configured_without_url_or_token(
        self, health_service: HealthService, base_url: str, token: str
    ) -> None:
        client = NotificationBridgeClient(base_url, token, health_service)

        assert client.is_configured is False

    def test_registers_its_readiness_check_when_configured(
        self, app: Flask, health_service: HealthService, bridge: FakeNotificationBridge
    ) -> None:
        NotificationBridgeClient(bridge.url, REGISTRATION_TOKEN, health_service)

        with app.app_context():
            body, status = health_service.check_readyz()

        assert status == 200
        assert body["checks"]["notification_bridge"] == {
            "status": "ok",
            "critical": False,
        }

    def test_registers_no_readiness_check_when_not_configured(
        self, app: Flask, health_service: HealthService
    ) -> None:
        NotificationBridgeClient("", "", health_service)

        with app.app_context():
            body, status = health_service.check_readyz()

        assert status == 200
        assert body["checks"] == {}

    def test_failing_readiness_check_leaves_the_app_ready(
        self, app: Flask, health_service: HealthService
    ) -> None:
        NotificationBridgeClient(_unused_port_url(), REGISTRATION_TOKEN, health_service)

        with app.app_context():
            body, status = health_service.check_readyz()

        assert status == 200
        assert body["ready"] is True
        assert body["status"] == "degraded"
        assert body["checks"]["notification_bridge"]["status"] == "error"
        assert body["checks"]["notification_bridge"]["critical"] is False

    def test_check_readiness_ok_when_the_bridge_is_healthy(
        self, bridge_client: NotificationBridgeClient
    ) -> None:
        result = bridge_client.check_readiness()

        assert result.status is CheckStatus.OK

    def test_check_readiness_needs_no_token(
        self, bridge: FakeNotificationBridge, health_service: HealthService
    ) -> None:
        client = NotificationBridgeClient(
            bridge.url, "a-token-nobody-holds", health_service
        )

        assert client.check_readiness().status is CheckStatus.OK

    def test_check_readiness_error_when_the_bridge_answers_503(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.set_healthy(False)

        result = bridge_client.check_readiness()

        assert result.status is CheckStatus.ERROR
        assert result.detail == "the bridge answered 503"

    def test_check_readiness_raises_when_the_bridge_is_unreachable(
        self, health_service: HealthService
    ) -> None:
        # The health service reports an exception a check raises as an error.
        client = NotificationBridgeClient(
            _unused_port_url(), REGISTRATION_TOKEN, health_service
        )

        with pytest.raises(Exception, match="Connection"):
            client.check_readiness()

    def test_submit_sends_the_message_and_url_under_the_bearer_token(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge_client.submit("Familie Jansen *komt*", url="https://kerst.example/admin")

        assert len(bridge.submits) == 1
        submit = bridge.submits[0]
        assert submit.body == {
            "message": "Familie Jansen *komt*",
            "url": "https://kerst.example/admin",
        }
        assert submit.bearer == REGISTRATION_TOKEN

    def test_submit_without_url_sends_only_the_message(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge_client.submit("hello")

        assert bridge.submits[0].body == {"message": "hello"}

    def test_submit_sends_the_title_when_given_and_leaves_it_out_otherwise(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge_client.submit("- Komt niet.", title="Familie Jansen")
        bridge_client.submit("- Komt niet.")

        assert bridge.submits[0].body == {
            "message": "- Komt niet.",
            "title": "Familie Jansen",
        }
        assert "title" not in bridge.submits[1].body

    def test_submit_tolerates_a_trailing_slash_in_the_base_url(
        self, bridge: FakeNotificationBridge, health_service: HealthService
    ) -> None:
        client = NotificationBridgeClient(
            bridge.url + "/", REGISTRATION_TOKEN, health_service
        )

        client.submit("hello")

        assert len(bridge.submits) == 1

    def test_submit_sends_every_message_in_order(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        for number in range(3):
            bridge_client.submit(f"message {number}")

        assert [submit.body["message"] for submit in bridge.submits] == [
            "message 0",
            "message 1",
            "message 2",
        ]

    def test_submit_raises_when_the_bridge_answers_500(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.fail_next(1, "http_500")

        with pytest.raises(ExternalServiceException, match="answered 500") as raised:
            bridge_client.submit("hello")

        assert "the bridge broke" in raised.value.message
        assert bridge.submits == []

    def test_submit_raises_when_the_token_is_unknown(
        self, bridge: FakeNotificationBridge, health_service: HealthService
    ) -> None:
        client = NotificationBridgeClient(bridge.url, "a-wrong-token", health_service)

        with pytest.raises(ExternalServiceException, match="answered 401") as raised:
            client.submit("hello")

        assert "unknown bearer token" in raised.value.message
        assert bridge.attempts == []

    def test_submit_raises_when_the_bridge_refuses_the_body(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        with pytest.raises(ExternalServiceException, match="answered 400"):
            bridge_client.submit("   ")

        assert bridge.attempts == []

    def test_submit_raises_when_the_message_is_too_long(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        with pytest.raises(ExternalServiceException, match="answered 413"):
            bridge_client.submit("x" * 4097)

        assert bridge.attempts == []

    def test_submit_raises_when_the_path_is_not_the_bridges(
        self, bridge: FakeNotificationBridge, health_service: HealthService
    ) -> None:
        client = NotificationBridgeClient(
            bridge.url + "/elsewhere", REGISTRATION_TOKEN, health_service
        )

        with pytest.raises(ExternalServiceException, match="answered 404"):
            client.submit("hello")

    def test_submit_raises_when_telegram_did_not_take_it(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.fail_next(1, "telegram_error")

        with pytest.raises(ExternalServiceException) as raised:
            bridge_client.submit("hello")

        assert FAILURE_TELEGRAM_ERROR in raised.value.message
        assert bridge.submits == []
        assert len(bridge.attempts) == 1

    def test_submit_raises_when_the_registration_has_no_telegram_channel(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.fail_next(1, "no_telegram")

        with pytest.raises(ExternalServiceException, match="no Telegram channel"):
            bridge_client.submit("hello")

    def test_submit_raises_when_the_answer_is_not_json(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.fail_next(1, "not_json")

        with pytest.raises(ExternalServiceException, match="not JSON"):
            bridge_client.submit("hello")

    def test_submit_raises_when_the_answer_is_not_an_object(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.fail_next(1, "not_an_object")

        with pytest.raises(ExternalServiceException, match="no Telegram channel"):
            bridge_client.submit("hello")

    def test_submit_raises_when_the_bridge_closes_the_connection(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.fail_next(1, "drop")

        with pytest.raises(ExternalServiceException, match="did not answer"):
            bridge_client.submit("hello")

    def test_submit_raises_when_the_bridge_is_unreachable(
        self, health_service: HealthService
    ) -> None:
        client = NotificationBridgeClient(
            _unused_port_url(), REGISTRATION_TOKEN, health_service
        )

        with pytest.raises(ExternalServiceException, match="did not answer"):
            client.submit("hello")

    def test_submit_succeeds_again_after_a_failure(
        self, bridge: FakeNotificationBridge, bridge_client: NotificationBridgeClient
    ) -> None:
        bridge.fail_next(1, "http_500")
        with pytest.raises(ExternalServiceException):
            bridge_client.submit("first")

        bridge_client.submit("second")

        assert [submit.body["message"] for submit in bridge.submits] == ["second"]
        assert len(bridge.attempts) == 2
