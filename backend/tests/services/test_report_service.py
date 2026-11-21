"""Tests of the report queue and the sender of each household's batched message.

A household's timer is the ``created_at`` of its newest queued line, on the
database's clock. Most tests set that time directly, ``age`` seconds back, so
they need not wait for a timer; the tests of the running thread use short real
timers instead.
"""

import threading
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from dependency_injector import providers
from flask import Flask, g
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.app_config import AppEnvironment, AppSettings
from app.config import Settings
from app.exceptions import ConfigurationError
from app.models.change_report import ChangeReport
from app.models.party import Party
from app.services.config_sync_service import AppliedConfig
from app.services.container import ServiceContainer
from app.services.health_service import HealthService
from app.services.notification_bridge_client import NotificationBridgeClient
from app.services.report_service import BATCH_SECONDS, ReportQueue, ReportSender
from app.utils.lifecycle_coordinator import LifecycleCoordinator
from tests.support.fake_notification_bridge import (
    REGISTRATION_TOKEN,
    Failure,
    FakeNotificationBridge,
)

ADMIN_URL = "http://localhost:3700/admin"
THREAD_NAME = "report-sender"

# The sender's timer in the tests that set ``created_at`` themselves: a line
# older than this is due, a younger one waits.
BATCH = 300
DUE = BATCH + 60
WAITING = BATCH - 60

Message = tuple[str, str]
"""What the group sees: the title, the household's name, and the message."""


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
        batch_seconds: float = BATCH,
    ) -> ReportSender:
        sender = ReportSender(
            session_maker,
            client,
            settings or test_settings,
            lifecycle_coordinator,
            retry_seconds=retry_seconds,
            batch_seconds=batch_seconds,
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


@pytest.fixture
def households(seeded: AppliedConfig) -> tuple[Party, Party, Party]:
    """Familie Jansen, Familie de Boer and Tante Els."""
    jansen, de_boer, els = seeded.parties
    return jansen, de_boer, els


def _db_now(session: Session) -> datetime:
    now: datetime | None = session.scalar(select(func.clock_timestamp()))
    assert now is not None
    return now


def _queue(
    session: Session, party: Party, *lines: str, age: float = DUE
) -> list[ChangeReport]:
    """Queue ``party``'s ``lines``, made ``age`` seconds ago: by default due."""
    made = _db_now(session) - timedelta(seconds=age)
    reports = [
        ChangeReport(party_id=party.id, message=line, created_at=made) for line in lines
    ]
    session.add_all(reports)
    # Committed, as the queue's own transaction leaves them: the sender rolls
    # its session back, and that must not take the reports with it.
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


def _parties(session_maker: sessionmaker[Session]) -> list[tuple[int, str]]:
    """The households a committed database holds, as (id, name), in config order."""
    with session_maker() as session:
        return [
            (party.id, party.name)
            for party in session.scalars(select(Party).order_by(Party.position))
        ]


def _commit(
    session_maker: sessionmaker[Session], party_id: int, *lines: str, age: float = 0
) -> None:
    with session_maker() as session:
        made = _db_now(session) - timedelta(seconds=age)
        session.add_all(
            [
                ChangeReport(party_id=party_id, message=line, created_at=made)
                for line in lines
            ]
        )
        session.commit()


def _sent_lines(session_maker: sessionmaker[Session]) -> list[str]:
    with session_maker() as session:
        return list(
            session.scalars(
                select(ChangeReport.message)
                .where(ChangeReport.sent_at.is_not(None))
                .order_by(ChangeReport.id)
            )
        )


def _delivered(bridge: FakeNotificationBridge) -> list[Message]:
    return [(s.body.get("title", ""), s.body["message"]) for s in bridge.submits]


def _attempted(bridge: FakeNotificationBridge) -> list[Message]:
    return [(s.body.get("title", ""), s.body["message"]) for s in bridge.attempts]


def _lock_waits(session_maker: sessionmaker[Session]) -> int:
    """How many connections to the test's database wait on a lock."""
    with session_maker() as session:
        return session.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
        )


class TestBatchSetting:
    def test_the_timer_runs_five_minutes_by_default(self) -> None:
        assert BATCH_SECONDS == 300
        assert AppSettings().report_batch_seconds == 300

    def test_report_batch_seconds_sets_the_timer(self) -> None:
        env = AppEnvironment(REPORT_BATCH_SECONDS=2.5)  # type: ignore[call-arg]

        assert AppSettings.load(env).report_batch_seconds == 2.5

    def test_the_container_gives_the_sender_the_configured_timer(
        self, container: ServiceContainer
    ) -> None:
        container.app_config.override(AppSettings(report_batch_seconds=7))
        container.report_sender.reset()
        try:
            assert container.report_sender()._batch == timedelta(seconds=7)
        finally:
            container.app_config.reset_last_overriding()
            container.report_sender.reset()


class TestReportSender:
    def test_a_household_s_changes_go_out_as_one_message_headed_by_its_name(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen = households[0]
        reports = _queue(
            session, jansen, "Komt met 2: 2 eet alles.", "Maakt Pompoensoep."
        )

        assert sender.send_pending() is True

        assert _delivered(bridge) == [
            ("Familie Jansen", "- Komt met 2: 2 eet alles.\n- Maakt Pompoensoep.")
        ]
        assert bridge.submits[0].bearer == REGISTRATION_TOKEN
        assert bridge.submits[0].body["url"] == ADMIN_URL
        session.expire_all()
        assert all(report.sent_at is not None for report in reports)

    def test_a_household_whose_timer_still_runs_waits(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        reports = _queue(session, households[0], "Maakt Pompoensoep.", age=WAITING)

        assert sender.send_pending() is True

        assert bridge.attempts == []
        session.expire_all()
        assert reports[0].sent_at is None

    def test_a_new_change_starts_the_household_s_timer_again(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen = households[0]
        old = _queue(session, jansen, "Maakt Pompoensoep.", age=DUE * 3)
        _queue(session, jansen, "Maakt Pompoensoep toch niet.", age=WAITING)

        assert sender.send_pending() is True

        assert bridge.attempts == []
        session.expire_all()
        assert old[0].sent_at is None

    def test_once_the_timer_runs_out_every_change_since_goes_in_order(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen = households[0]
        _queue(session, jansen, "Maakt Pompoensoep.", age=DUE * 3)
        _queue(session, jansen, "Maakt Pompoensoep toch niet.", age=DUE * 2)
        _queue(session, jansen, "Maakt Rollade.", age=DUE)

        sender.send_pending()

        assert _delivered(bridge) == [
            (
                "Familie Jansen",
                "- Maakt Pompoensoep.\n- Maakt Pompoensoep toch niet.\n"
                "- Maakt Rollade.",
            )
        ]

    def test_each_household_gets_its_own_message_the_longest_waiting_first(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen, de_boer, els = households
        _queue(session, jansen, "Maakt Rollade.", age=DUE)
        _queue(session, de_boer, "Komt niet.", age=DUE * 2)
        _queue(session, els, "Komt met 1: 1 vegan.", age=WAITING)

        assert sender.send_pending() is True

        assert _delivered(bridge) == [
            ("Familie de Boer", "- Komt niet."),
            ("Familie Jansen", "- Maakt Rollade."),
        ]

    def test_the_next_message_holds_only_the_changes_since_the_last(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen = households[0]
        _queue(session, jansen, "Maakt Rollade.")
        sender.send_pending()
        _queue(session, jansen, "Neemt 20 borden mee.")

        assert sender.send_pending() is True

        assert _delivered(bridge) == [
            ("Familie Jansen", "- Maakt Rollade."),
            ("Familie Jansen", "- Neemt 20 borden mee."),
        ]

    def test_admin_url_ignores_a_trailing_slash_of_the_base_url(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        container: ServiceContainer,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
        test_settings: Settings,
        households: tuple[Party, Party, Party],
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
        _queue(session, households[0], "Maakt Rollade.")

        sender.send_pending()

        assert bridge.submits[0].body["url"] == "https://kerst.example.org/admin"

    def test_a_batch_past_the_bridge_s_limit_goes_out_in_several_messages(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        lines = [
            f"Maakt gerecht nummer {i:03} met een wat langere naam." for i in range(150)
        ]
        reports = _queue(session, households[0], *lines)

        assert sender.send_pending() is True

        assert len(bridge.submits) == 2
        assert {title for title, _ in _delivered(bridge)} == {"Familie Jansen"}
        sent = "\n".join(message for _, message in _delivered(bridge))
        assert sent == "\n".join(f"- {line}" for line in lines)
        session.expire_all()
        assert all(report.sent_at is not None for report in reports)

    def test_send_pending_returns_true_with_an_empty_queue(
        self, bridge: FakeNotificationBridge, sender: ReportSender
    ) -> None:
        assert sender.send_pending() is True

        assert bridge.attempts == []

    def test_send_pending_sends_a_message_once(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        _queue(session, households[0], "Maakt Rollade.")

        sender.send_pending()
        sender.send_pending()

        assert _delivered(bridge) == [("Familie Jansen", "- Maakt Rollade.")]

    def test_failed_send_leaves_that_household_and_every_later_one_queued(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen, de_boer, _ = households
        fails = _queue(session, de_boer, "Komt niet.", age=DUE * 2)
        after = _queue(session, jansen, "Maakt Rollade.")
        bridge.fail_next(1)

        assert sender.send_pending() is False

        session.expire_all()
        assert [r.sent_at for r in fails + after] == [None, None]
        assert _attempted(bridge) == [("Familie de Boer", "- Komt niet.")]

    def test_later_send_pending_sends_what_a_failure_left_in_order(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen, de_boer, _ = households
        reports = _queue(session, de_boer, "Komt niet.", age=DUE * 2)
        reports += _queue(session, jansen, "Maakt Rollade.")
        bridge.fail_next(1)
        assert sender.send_pending() is False

        assert sender.send_pending() is True

        assert _delivered(bridge) == [
            ("Familie de Boer", "- Komt niet."),
            ("Familie Jansen", "- Maakt Rollade."),
        ]
        session.expire_all()
        assert all(report.sent_at is not None for report in reports)

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
    def test_every_way_the_bridge_fails_leaves_the_changes_queued(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
        how: Failure,
    ) -> None:
        report = _queue(session, households[0], "Maakt Rollade.")[0]
        bridge.fail_next(1, how)

        assert sender.send_pending() is False

        session.expire_all()
        assert report.sent_at is None
        assert bridge.submits == []
        assert sender.send_pending() is True
        assert _delivered(bridge) == [("Familie Jansen", "- Maakt Rollade.")]

    def test_send_pending_leaves_the_queue_when_the_bridge_is_unreachable(
        self,
        session: Session,
        container: ServiceContainer,
        make_sender: Callable[..., ReportSender],
        test_settings: Settings,
        households: tuple[Party, Party, Party],
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
        report = _queue(session, households[0], "Maakt Rollade.")[0]

        assert sender.send_pending() is False

        session.expire_all()
        assert report.sent_at is None

    def test_send_pending_sends_nothing_after_shutdown(
        self,
        session: Session,
        bridge: FakeNotificationBridge,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        _queue(session, households[0], "Maakt Rollade.")
        sender.shutdown()

        assert sender.send_pending() is False

        assert bridge.attempts == []

    def test_a_household_s_queued_changes_go_with_it(
        self,
        session: Session,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen = households[0]
        _queue(session, jansen, "Maakt Rollade.")

        session.delete(jansen)
        session.flush()

        assert session.scalars(select(ChangeReport)).all() == []


class TestSecondsUntilDue:
    def test_none_with_nothing_queued(self, sender: ReportSender) -> None:
        assert sender.seconds_until_due() is None

    def test_the_soonest_household_s_timer(
        self,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen, de_boer, _ = households
        _queue(session, jansen, "Maakt Rollade.", age=100)
        _queue(session, de_boer, "Komt niet.", age=250)

        due = sender.seconds_until_due()

        assert due is not None
        assert BATCH - 250 - 5 < due <= BATCH - 250

    def test_a_household_s_newest_change_sets_its_timer(
        self,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen = households[0]
        _queue(session, jansen, "Maakt Rollade.", age=250)
        _queue(session, jansen, "Maakt Rollade toch niet.", age=100)

        due = sender.seconds_until_due()

        assert due is not None
        assert BATCH - 100 - 5 < due <= BATCH - 100

    def test_zero_for_a_household_whose_timer_ran_out(
        self,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        _queue(session, households[0], "Maakt Rollade.", age=DUE)

        assert sender.seconds_until_due() == 0

    def test_ignores_what_was_sent(
        self,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        _queue(session, households[0], "Maakt Rollade.")
        sender.send_pending()

        assert sender.seconds_until_due() is None


class TestRunningSender:
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

    def test_after_a_restart_each_timer_runs_on_from_its_last_change(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        (first, first_name), (second, _) = _parties(session_maker)[:2]
        sender = make_sender(
            session_maker, bridge_client, container.lifecycle_coordinator()
        )
        sender.start()
        sender.shutdown()
        # Queued before the restart: the first household's timer ran out
        # while the pod was down, the second's still runs.
        _commit(session_maker, first, "Maakt Rollade.", age=DUE)
        _commit(session_maker, second, "Komt niet.", age=WAITING)

        sender.start()

        _wait_for(
            lambda: _delivered(bridge) == [(first_name, "- Maakt Rollade.")],
            "the first household's message",
        )
        _wait_for(
            lambda: _sent_lines(session_maker) == ["Maakt Rollade."],
            "the sent marks",
        )
        assert sender.seconds_until_due() is not None

    def test_running_sender_waits_for_the_timer_which_each_change_starts_again(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        (party, name), *_ = _parties(session_maker)
        sender = make_sender(
            session_maker,
            bridge_client,
            container.lifecycle_coordinator(),
            batch_seconds=1.5,
        )
        sender.start()

        _commit(session_maker, party, "Maakt Rollade.")
        sender.wake()
        time.sleep(0.75)
        _commit(session_maker, party, "Maakt Rollade toch niet.")
        sender.wake()
        # The first change's timer would have run out by now: the second
        # started it again.
        time.sleep(1.0)
        assert bridge.attempts == []

        _wait_for(
            lambda: (
                _delivered(bridge)
                == [(name, "- Maakt Rollade.\n- Maakt Rollade toch niet.")]
            ),
            "the household's message",
        )
        assert bridge.submits[0].body["url"] == ADMIN_URL
        _wait_for(
            lambda: (
                _sent_lines(session_maker)
                == ["Maakt Rollade.", "Maakt Rollade toch niet."]
            ),
            "the sent marks",
        )

    def test_running_sender_keeps_each_household_s_timer_apart(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        (first, first_name), (second, second_name) = _parties(session_maker)[:2]
        sender = make_sender(
            session_maker,
            bridge_client,
            container.lifecycle_coordinator(),
            batch_seconds=0.5,
        )
        sender.start()

        _commit(session_maker, first, "Maakt Rollade.")
        sender.wake()
        _commit(session_maker, second, "Komt niet.")
        sender.wake()

        _wait_for(lambda: len(bridge.submits) == 2, "both messages")
        assert _delivered(bridge) == [
            (first_name, "- Maakt Rollade."),
            (second_name, "- Komt niet."),
        ]

    def test_running_sender_tries_a_failed_send_again_after_the_retry_time(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        (party, name), *_ = _parties(session_maker)
        _commit(session_maker, party, "Maakt Rollade.", age=DUE)
        bridge.fail_next(2)
        sender = make_sender(
            session_maker,
            bridge_client,
            container.lifecycle_coordinator(),
            retry_seconds=0.2,
        )

        sender.start()

        _wait_for(
            lambda: _delivered(bridge) == [(name, "- Maakt Rollade.")], "the retries"
        )
        assert len(bridge.attempts) == 3
        _wait_for(
            lambda: _sent_lines(session_maker) == ["Maakt Rollade."], "the sent marks"
        )

    def test_wake_has_the_running_sender_try_a_failed_send_again(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> None:
        container = committed_app.container
        session_maker = container.session_maker()
        (party, name), *_ = _parties(session_maker)
        _commit(session_maker, party, "Maakt Rollade.", age=DUE)
        bridge.fail_next(1)
        sender = make_sender(
            session_maker, bridge_client, container.lifecycle_coordinator()
        )

        sender.start()

        _wait_for(lambda: len(bridge.attempts) == 1, "the failed attempt")
        assert _sent_lines(session_maker) == []
        sender.wake()
        _wait_for(
            lambda: _delivered(bridge) == [(name, "- Maakt Rollade.")], "the message"
        )


class TestTwoSenders:
    """Two senders on one queue, as a rollout's surge runs two pods."""

    @pytest.fixture
    def two_senders(
        self,
        committed_app: Flask,
        bridge_client: NotificationBridgeClient,
        make_sender: Callable[..., ReportSender],
    ) -> tuple[ReportSender, ReportSender]:
        container = committed_app.container
        return (
            make_sender(
                container.session_maker(),
                bridge_client,
                container.lifecycle_coordinator(),
            ),
            make_sender(
                container.session_maker(),
                bridge_client,
                container.lifecycle_coordinator(),
            ),
        )

    def _second_sender_meets_the_first(
        self,
        session_maker: sessionmaker[Session],
        bridge: FakeNotificationBridge,
    ) -> None:
        """Wait until the second sender waits on the first's lock or sends too."""
        _wait_for(
            lambda: _lock_waits(session_maker) > 0 or len(bridge.attempts) > 1,
            "the second sender",
        )

    def test_each_message_goes_out_once_and_in_order(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        two_senders: tuple[ReportSender, ReportSender],
    ) -> None:
        session_maker = committed_app.container.session_maker()
        (first, first_name), (second, second_name) = _parties(session_maker)[:2]
        _commit(
            session_maker, first, "Maakt Rollade.", "Neemt 20 borden mee.", age=DUE * 2
        )
        _commit(session_maker, second, "Komt niet.", age=DUE)
        one, two = two_senders
        release = bridge.hold_next()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_round = pool.submit(one.send_pending)
            _wait_for(lambda: len(bridge.attempts) == 1, "the first sender's send")
            second_round = pool.submit(two.send_pending)
            self._second_sender_meets_the_first(session_maker, bridge)

            # While the first household's message is in flight, the second
            # sender sends neither it nor the message after it.
            assert len(bridge.attempts) == 1
            release.set()

            assert first_round.result(timeout=15) is True
            assert second_round.result(timeout=15) is True

        expected = [
            (first_name, "- Maakt Rollade.\n- Neemt 20 borden mee."),
            (second_name, "- Komt niet."),
        ]
        assert _attempted(bridge) == expected
        assert _delivered(bridge) == expected
        assert _sent_lines(session_maker) == [
            "Maakt Rollade.",
            "Neemt 20 borden mee.",
            "Komt niet.",
        ]

    def test_a_failed_send_holds_the_later_messages_and_the_other_sender_retries(
        self,
        committed_app: Flask,
        bridge: FakeNotificationBridge,
        two_senders: tuple[ReportSender, ReportSender],
    ) -> None:
        session_maker = committed_app.container.session_maker()
        (first, first_name), (second, second_name) = _parties(session_maker)[:2]
        _commit(session_maker, first, "Maakt Rollade.", age=DUE * 2)
        _commit(session_maker, second, "Komt niet.", age=DUE)
        one, two = two_senders
        bridge.fail_next(1)
        release = bridge.hold_next()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_round = pool.submit(one.send_pending)
            _wait_for(lambda: len(bridge.attempts) == 1, "the first sender's send")
            second_round = pool.submit(two.send_pending)
            self._second_sender_meets_the_first(session_maker, bridge)

            assert len(bridge.attempts) == 1
            release.set()

            assert first_round.result(timeout=15) is False
            assert second_round.result(timeout=15) is True

        first_message = (first_name, "- Maakt Rollade.")
        second_message = (second_name, "- Komt niet.")
        assert _attempted(bridge) == [first_message, first_message, second_message]
        assert _delivered(bridge) == [first_message, second_message]
        assert _sent_lines(session_maker) == ["Maakt Rollade.", "Komt niet."]


class TestReportQueue:
    def test_queue_adds_an_unsent_line_of_the_household(
        self,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        jansen = households[0]
        queue = ReportQueue(session, sender)

        queue.queue(jansen, "Komt niet.")
        session.flush()

        report = session.scalars(select(ChangeReport)).one()
        assert report.party_id == jansen.id
        assert report.message == "Komt niet."
        assert report.sent_at is None
        assert report.created_at is not None

    def test_queue_keeps_each_line_in_order(
        self,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        queue = ReportQueue(session, sender)

        queue.queue(households[0], "one")
        queue.queue(households[0], "two")
        session.flush()

        reports = session.scalars(select(ChangeReport).order_by(ChangeReport.id)).all()
        assert [report.message for report in reports] == ["one", "two"]

    def test_queue_does_not_wake_the_sender_before_the_commit(
        self,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        ReportQueue(session, sender).queue(households[0], "not yet")
        session.flush()

        assert not sender._wake.is_set()

    def test_request_commit_wakes_the_sender(
        self,
        app: Flask,
        container: ServiceContainer,
        session: Session,
        sender: ReportSender,
        households: tuple[Party, Party, Party],
    ) -> None:
        container.report_sender.override(providers.Object(sender))

        with app.test_request_context("/"):
            container.report_queue().queue(households[0], "a request's change")
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
        households: tuple[Party, Party, Party],
    ) -> None:
        container.report_sender.override(providers.Object(sender))
        session.commit()

        with app.test_request_context("/"):
            container.report_queue().queue(households[0], "rolled back")
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
        households: tuple[Party, Party, Party],
    ) -> None:
        container.report_sender.override(providers.Object(sender))

        with app.test_request_context("/"):
            queue = container.report_queue()
            queue.queue(households[0], "one")
            queue.queue(households[0], "two")

        assert sender._wake.is_set()

    def test_request_commit_gets_the_message_sent_by_the_running_sender(
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
            batch_seconds=0.2,
        )
        container.report_sender.override(providers.Object(sender))
        sender.start()

        with committed_app.test_request_context("/"):
            party = (
                container.db_session()
                .scalars(select(Party).order_by(Party.position))
                .first()
            )
            assert party is not None
            name = party.name
            queue = container.report_queue()
            queue.queue(party, "Komt met 2: 2 eet alles.")
            queue.queue(party, "Maakt Rollade.")

        _wait_for(
            lambda: (
                _delivered(bridge)
                == [(name, "- Komt met 2: 2 eet alles.\n- Maakt Rollade.")]
            ),
            "the message",
        )
        assert bridge.submits[0].body["url"] == ADMIN_URL
        _wait_for(
            lambda: (
                _sent_lines(session_maker)
                == ["Komt met 2: 2 eet alles.", "Maakt Rollade."]
            ),
            "the sent marks",
        )

    def test_change_queued_while_the_bridge_is_down_goes_out_when_it_answers(
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
            batch_seconds=0,
        )
        container.report_sender.override(providers.Object(sender))
        bridge.fail_next(3, "telegram_error")
        sender.start()

        with committed_app.test_request_context("/"):
            party = (
                container.db_session()
                .scalars(select(Party).order_by(Party.position))
                .first()
            )
            assert party is not None
            name = party.name
            container.report_queue().queue(party, "Maakt Rollade.")

        _wait_for(
            lambda: _delivered(bridge) == [(name, "- Maakt Rollade.")], "the message"
        )
        assert len(bridge.attempts) == 4
