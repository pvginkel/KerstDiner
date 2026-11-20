"""Tests of the report queue and the sender of its messages."""

import threading
import time
from collections.abc import Callable, Generator

import pytest
from dependency_injector import providers
from flask import Flask, g
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.exceptions import ConfigurationError
from app.models.change_report import ChangeReport
from app.services.container import ServiceContainer
from app.services.health_service import HealthService
from app.services.notification_bridge_client import NotificationBridgeClient
from app.services.report_service import ReportQueue, ReportSender
from app.utils.lifecycle_coordinator import LifecycleCoordinator
from tests.support.fake_notification_bridge import (
    REGISTRATION_TOKEN,
    Failure,
    FakeNotificationBridge,
)

ADMIN_URL = "http://localhost:3700/admin"
THREAD_NAME = "report-sender"


@pytest.fixture
def bridge() -> Generator[FakeNotificationBridge]:
    with FakeNotificationBridge() as served:
        yield served


@pytest.fixture
def bridge_client(
    bridge: FakeNotificationBridge, test_settings: Settings
) -> NotificationBridgeClient:
    health_service = HealthService(
        lifecycle_coordinator=LifecycleCoordinator(graceful_shutdown_timeout=1),
        settings=test_settings,
    )
    return NotificationBridgeClient(bridge.url, REGISTRATION_TOKEN, health_service)


@pytest.fixture
def unconfigured_client(test_settings: Settings) -> NotificationBridgeClient:
    health_service = HealthService(
        lifecycle_coordinator=LifecycleCoordinator(graceful_shutdown_timeout=1),
        settings=test_settings,
    )
    return NotificationBridgeClient("", "", health_service)


@pytest.fixture
def senders() -> Generator[list[ReportSender]]:
    """The senders a test builds: shut down at teardown, so no thread outlives it."""
    built: list[ReportSender] = []
    yield built
    for sender in built:
        sender.shutdown()


@pytest.fixture
def make_sender(
    senders: list[ReportSender], test_settings: Settings
) -> Callable[..., ReportSender]:
    def make(
        session_maker: sessionmaker[Session],
        client: NotificationBridgeClient,
        lifecycle_coordinator: LifecycleCoordinator,
        settings: Settings | None = None,
        retry_seconds: float = 60,
    ) -> ReportSender:
        sender = ReportSender(
            session_maker,
            client,
            settings or test_settings,
            lifecycle_coordinator,
            retry_seconds=retry_seconds,
        )
        senders.append(sender)
        return sender

    return make


@pytest.fixture
def sender(
    container: ServiceContainer,
    bridge_client: NotificationBridgeClient,
    make_sender: Callable[..., ReportSender],
) -> ReportSender:
    """A sender on the test's session and the stand-in, not started."""
    return make_sender(
        container.session_maker(), bridge_client, container.lifecycle_coordinator()
    )


def _queue(session: Session, *messages: str) -> list[ChangeReport]:
    reports = [ChangeReport(message=message) for message in messages]
    session.add_all(reports)
    # Committed, as the queue's own transaction leaves them: a failed send rolls
    # the sender's session back, and that must not take the reports with it.
    session.commit()
    return reports


def _wait_for(condition: Callable[[], bool], what: str, timeout: float = 15) -> None:
    """Wait, bounded, for what a thread does eventually."""
    deadline = time.perf_counter() + timeout
    while not condition():
        assert time.perf_counter() < deadline, f"timed out waiting for {what}"
        time.sleep(0.02)


def _sender_threads() -> list[threading.Thread]:
    return [
        thread
        for thread in threading.enumerate()
        if thread.name == THREAD_NAME and thread.is_alive()
    ]


def _commit(session_maker: sessionmaker[Session], *messages: str) -> None:
    with session_maker() as session:
        session.add_all([ChangeReport(message=message) for message in messages])
        session.commit()


def _sent_messages(session_maker: sessionmaker[Session]) -> list[str]:
    with session_maker() as session:
        return list(
            session.scalars(
                select(ChangeReport.message)
                .where(ChangeReport.sent_at.is_not(None))
                .order_by(ChangeReport.id)
            )
        )


def _delivered(bridge: FakeNotificationBridge) -> list[str]:
    return [submit.body["message"] for submit in bridge.submits]


class TestReportSender:
    def test_send_pending_sends_the_queue_oldest_first_and_marks_each_sent(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        reports = _queue(session, "first", "second", "third")

        assert sender.send_pending() is True

        assert _delivered(bridge) == ["first", "second", "third"]
        assert all(submit.bearer == REGISTRATION_TOKEN for submit in bridge.submits)
        session.expire_all()
        assert all(report.sent_at is not None for report in reports)
        sent = [report.sent_at for report in reports]
        assert sent == sorted(sent)  # type: ignore[type-var]

    def test_send_pending_gives_each_message_the_admin_url(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        _queue(session, "first", "second")

        sender.send_pending()

        assert [submit.body["url"] for submit in bridge.submits] == [ADMIN_URL] * 2

    def test_admin_url_ignores_a_trailing_slash_of_the_base_url(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        container: ServiceContainer,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
        test_settings: Settings,
    ) -> None:
        settings = test_settings.model_copy(
            update={"baseurl": "https://kerst.example.org/"}
        )
        sender = make_sender(
            container.session_maker(),
            bridge_client,
            container.lifecycle_coordinator(),
            settings=settings,
        )
        _queue(session, "first")

        sender.send_pending()

        assert bridge.submits[0].body["url"] == "https://kerst.example.org/admin"

    def test_send_pending_returns_true_with_an_empty_queue(
        self, bridge: FakeNotificationBridge, sender: ReportSender
    ) -> None:
        assert sender.send_pending() is True

        assert bridge.attempts == []

    def test_send_pending_leaves_the_reports_already_sent_alone(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        _queue(session, "first")
        sender.send_pending()
        _queue(session, "second")

        assert sender.send_pending() is True

        assert _delivered(bridge) == ["first", "second"]

    def test_send_pending_sends_a_report_once(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        _queue(session, "only")

        sender.send_pending()
        sender.send_pending()

        assert _delivered(bridge) == ["only"]

    def test_failed_send_leaves_that_report_and_every_later_one_unsent(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        sent_before = _queue(session, "before")[0]
        sender.send_pending()
        pending = _queue(session, "fails", "after", "last")
        bridge.fail_next(1)

        assert sender.send_pending() is False

        session.expire_all()
        assert sent_before.sent_at is not None
        assert [report.sent_at for report in pending] == [None, None, None]
        assert [submit.body["message"] for submit in bridge.attempts] == [
            "before",
            "fails",
        ]

    def test_later_send_pending_sends_what_a_failure_left_in_order(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        reports = _queue(session, "first", "second", "third")
        bridge.fail_next(1)
        assert sender.send_pending() is False

        assert sender.send_pending() is True

        assert _delivered(bridge) == ["first", "second", "third"]
        session.expire_all()
        assert all(report.sent_at is not None for report in reports)

    def test_a_failure_in_the_middle_keeps_the_order(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        _queue(session, "one")
        sender.send_pending()
        _queue(session, "two", "three")
        bridge.fail_next(2)

        assert sender.send_pending() is False
        assert sender.send_pending() is False
        assert sender.send_pending() is True

        assert _delivered(bridge) == ["one", "two", "three"]
        assert [submit.body["message"] for submit in bridge.attempts] == [
            "one",
            "two",
            "two",
            "two",
            "three",
        ]

    @pytest.mark.parametrize(
        "how",
        [
            "http_500",
            "telegram_error",
            "no_telegram",
            "not_json",
            "not_an_object",
            "drop",
        ],
    )
    def test_every_way_the_bridge_fails_leaves_the_report_queued(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        how: Failure,
    ) -> None:
        report = _queue(session, "stays")[0]
        bridge.fail_next(1, how)

        assert sender.send_pending() is False

        session.expire_all()
        assert report.sent_at is None
        assert bridge.submits == []
        assert sender.send_pending() is True
        assert _delivered(bridge) == ["stays"]

    def test_send_pending_leaves_the_queue_when_the_bridge_is_unreachable(
        self,
        session: Session,
        container: ServiceContainer,
        make_sender: Callable[..., ReportSender],
        test_settings: Settings,
    ) -> None:
        with FakeNotificationBridge() as gone:
            url = gone.url
        health_service = HealthService(
            lifecycle_coordinator=LifecycleCoordinator(graceful_shutdown_timeout=1),
            settings=test_settings,
        )
        client = NotificationBridgeClient(url, REGISTRATION_TOKEN, health_service)
        sender = make_sender(
            container.session_maker(), client, container.lifecycle_coordinator()
        )
        report = _queue(session, "stays")[0]

        assert sender.send_pending() is False

        session.expire_all()
        assert report.sent_at is None

    def test_send_pending_sends_nothing_after_shutdown(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
    ) -> None:
        _queue(session, "stays")
        sender.shutdown()

        assert sender.send_pending() is False

        assert bridge.attempts == []

    def test_start_without_a_bridge_starts_no_thread(
        self,
        container: ServiceContainer,
        unconfigured_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        sender = make_sender(
            container.session_maker(),
            unconfigured_client,
            container.lifecycle_coordinator(),
        )
        threads = len(_sender_threads())

        sender.start()

        assert len(_sender_threads()) == threads

    def test_start_without_a_bridge_raises_in_production(
        self,
        container: ServiceContainer,
        unconfigured_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
        test_settings: Settings,
    ) -> None:
        settings = test_settings.model_copy(update={"flask_env": "production"})
        sender = make_sender(
            container.session_maker(),
            unconfigured_client,
            container.lifecycle_coordinator(),
            settings=settings,
        )
        threads = len(_sender_threads())

        with pytest.raises(ConfigurationError, match="NOTIFICATIONS_URL"):
            sender.start()

        assert len(_sender_threads()) == threads

    def test_start_with_a_bridge_starts_one_thread_in_production(
        self,
        container: ServiceContainer,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
        test_settings: Settings,
    ) -> None:
        settings = test_settings.model_copy(update={"flask_env": "production"})
        sender = make_sender(
            container.session_maker(),
            bridge_client,
            container.lifecycle_coordinator(),
            settings=settings,
        )
        threads = len(_sender_threads())

        sender.start()
        sender.start()

        assert len(_sender_threads()) == threads + 1

    def test_shutdown_stops_the_thread(
        self,
        committed_app: Flask,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        sender = make_sender(
            container.session_maker(), bridge_client, container.lifecycle_coordinator()
        )
        threads = len(_sender_threads())
        sender.start()
        assert len(_sender_threads()) == threads + 1

        sender.shutdown()

        assert len(_sender_threads()) == threads

    def test_shutdown_is_safe_to_repeat_and_without_start(
        self, sender: ReportSender
    ) -> None:
        sender.shutdown()
        sender.shutdown()

    def test_start_again_after_shutdown_sends_again(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        sender = make_sender(
            session_maker, bridge_client, container.lifecycle_coordinator()
        )
        sender.start()
        sender.shutdown()
        _commit(session_maker, "after the restart")

        sender.start()

        _wait_for(lambda: _delivered(bridge) == ["after the restart"], "the report")

    def test_lifecycle_shutdown_stops_the_thread(
        self,
        committed_app: Flask,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        coordinator = container.lifecycle_coordinator()
        sender = make_sender(container.session_maker(), bridge_client, coordinator)
        threads = len(_sender_threads())
        sender.start()
        assert len(_sender_threads()) == threads + 1

        coordinator.shutdown()

        assert len(_sender_threads()) == threads

    def test_started_sender_sends_what_was_queued_and_what_wake_announces(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        _commit(session_maker, "queued before the start")
        sender = make_sender(
            session_maker, bridge_client, container.lifecycle_coordinator()
        )

        sender.start()

        _wait_for(
            lambda: _delivered(bridge) == ["queued before the start"],
            "the first report",
        )
        _commit(session_maker, "queued while running")
        sender.wake()
        _wait_for(
            lambda: (
                _delivered(bridge)
                == ["queued before the start", "queued while running"]
            ),
            "the second report",
        )
        assert bridge.submits[1].body["url"] == ADMIN_URL
        _wait_for(
            lambda: (
                _sent_messages(session_maker)
                == ["queued before the start", "queued while running"]
            ),
            "the sent marks",
        )

    def test_started_sender_tries_a_failed_send_again_after_the_retry_time(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        _commit(session_maker, "first", "second")
        bridge.fail_next(2)
        sender = make_sender(
            session_maker,
            bridge_client,
            container.lifecycle_coordinator(),
            retry_seconds=0.2,
        )

        sender.start()

        _wait_for(lambda: _delivered(bridge) == ["first", "second"], "the retries")
        assert [submit.body["message"] for submit in bridge.attempts] == [
            "first",
            "first",
            "first",
            "second",
        ]
        _wait_for(
            lambda: _sent_messages(session_maker) == ["first", "second"],
            "the sent marks",
        )

    def test_wake_has_the_started_sender_try_a_failed_send_again(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        _commit(session_maker, "stays")
        bridge.fail_next(1)
        sender = make_sender(
            session_maker, bridge_client, container.lifecycle_coordinator()
        )

        sender.start()

        _wait_for(lambda: len(bridge.attempts) == 1, "the failed attempt")
        assert _sent_messages(session_maker) == []
        sender.wake()
        _wait_for(lambda: _delivered(bridge) == ["stays"], "the report")


class TestReportQueue:
    def test_queue_adds_an_unsent_report(
        self, session: Session, sender: ReportSender
    ) -> None:
        queue = ReportQueue(session, sender)

        queue.queue("Familie Jansen komt")
        session.flush()

        report = session.scalars(
            select(ChangeReport).where(ChangeReport.message == "Familie Jansen komt")
        ).one()
        assert report.sent_at is None
        assert report.created_at is not None

    def test_queue_keeps_each_message_in_order(
        self, session: Session, sender: ReportSender
    ) -> None:
        queue = ReportQueue(session, sender)

        queue.queue("one")
        queue.queue("two")
        session.flush()

        reports = session.scalars(
            select(ChangeReport)
            .where(ChangeReport.message.in_(["one", "two"]))
            .order_by(ChangeReport.id)
        ).all()
        assert [report.message for report in reports] == ["one", "two"]

    def test_queue_does_not_wake_the_sender_before_the_commit(
        self, session: Session, sender: ReportSender
    ) -> None:
        ReportQueue(session, sender).queue("not yet")
        session.flush()

        assert not sender._wake.is_set()

    def test_request_commit_wakes_the_sender(
        self,
        app: Flask,
        container: ServiceContainer,
        session: Session,
        sender: ReportSender,
    ) -> None:
        container.report_sender.override(providers.Object(sender))

        with app.test_request_context("/"):
            container.report_queue().queue("a request's change")
            assert not sender._wake.is_set()

        assert sender._wake.is_set()
        session.expire_all()
        report = session.scalars(
            select(ChangeReport).where(ChangeReport.message == "a request's change")
        ).one()
        assert report.sent_at is None

    def test_request_rollback_neither_queues_nor_wakes(
        self,
        app: Flask,
        container: ServiceContainer,
        session: Session,
        sender: ReportSender,
    ) -> None:
        container.report_sender.override(providers.Object(sender))

        with app.test_request_context("/"):
            container.report_queue().queue("rolled back")
            g.needs_rollback = True

        assert not sender._wake.is_set()
        session.expire_all()
        assert (
            session.scalars(
                select(ChangeReport).where(ChangeReport.message == "rolled back")
            ).first()
            is None
        )

    def test_request_that_queues_twice_wakes_the_sender(
        self,
        app: Flask,
        container: ServiceContainer,
        sender: ReportSender,
    ) -> None:
        container.report_sender.override(providers.Object(sender))

        with app.test_request_context("/"):
            queue = container.report_queue()
            queue.queue("one")
            queue.queue("two")

        assert sender._wake.is_set()

    def test_request_commit_gets_the_report_sent_by_the_running_sender(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        sender = make_sender(
            session_maker, bridge_client, container.lifecycle_coordinator()
        )
        container.report_sender.override(providers.Object(sender))
        sender.start()

        with committed_app.test_request_context("/"):
            queue = container.report_queue()
            queue.queue("first change")
            queue.queue("second change")

        _wait_for(
            lambda: _delivered(bridge) == ["first change", "second change"],
            "the reports",
        )
        assert [submit.body["url"] for submit in bridge.submits] == [ADMIN_URL] * 2
        _wait_for(
            lambda: _sent_messages(session_maker) == ["first change", "second change"],
            "the sent marks",
        )

    def test_report_queued_while_the_bridge_is_down_goes_out_when_it_answers(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        sender = make_sender(
            session_maker,
            bridge_client,
            container.lifecycle_coordinator(),
            retry_seconds=0.2,
        )
        container.report_sender.override(providers.Object(sender))
        bridge.fail_next(3, "telegram_error")
        sender.start()

        with committed_app.test_request_context("/"):
            container.report_queue().queue("patient change")

        _wait_for(lambda: _delivered(bridge) == ["patient change"], "the report")
        assert len(bridge.attempts) == 4
