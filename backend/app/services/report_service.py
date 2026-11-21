"""The report queue: a household's changes go to Telegram together, in one message.

The change writes its line to ``change_reports`` in its own transaction
(``ReportQueue``), and a background thread (``ReportSender``) sends the queued
lines through the notification bridge. A household's changes wait for its
timer: each change starts it again, and once ``batch_seconds`` pass without
another, its lines since its last message go out as one message headed by its
name, and are marked sent. The timer is the newest line's ``created_at``, so it
lives in the database and survives a restart of the pod. A failed send stays
queued and is tried again a minute later, so a household's click never waits on
Telegram or fails because of it, and no report is lost.
The backend runs as one replica, but a rollout's surge runs a second beside it,
and each pod's thread sends. So a sender locks the lines it takes
(``FOR UPDATE``): the other sender waits on them, and finds them sent once it
gets them, or tries them itself when the send failed. Each line goes out once,
in its household's message, in the order of its changes.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core_exceptions import ExternalServiceException
from app.exceptions import ConfigurationError
from app.models.change_report import ChangeReport
from app.models.party import Party
from app.services.notification_bridge_client import NotificationBridgeClient
from app.services.report_texts import batch_messages, batch_title
from app.utils.after_commit import after_commit
from app.utils.lifecycle_coordinator import (
    LifecycleCoordinatorProtocol,
    LifecycleEvent,
)

logger = logging.getLogger(__name__)

RETRY_SECONDS = 60
"""How long a failed send waits, and the longest the thread sleeps between looks at the queue."""

BATCH_SECONDS = 300
"""How long a household's timer runs: five minutes after its last change, its message goes."""

_MIN_WAIT_SECONDS = 0.05
"""The shortest sleep, so a timer that is just running out never spins the thread."""


class ReportSender:
    """Sends each household's queued lines once its timer runs out, from a thread of its own."""

    def __init__(
        self,
        session_maker: sessionmaker[Session],
        bridge_client: NotificationBridgeClient,
        settings: Settings,
        lifecycle_coordinator: LifecycleCoordinatorProtocol,
        retry_seconds: float = RETRY_SECONDS,
        batch_seconds: float = BATCH_SECONDS,
    ) -> None:
        self._session_maker = session_maker
        self._bridge_client = bridge_client
        self._settings = settings
        self._retry_seconds = retry_seconds
        self._batch = timedelta(seconds=batch_seconds)
        self._admin_url = f"{settings.baseurl.rstrip('/')}/admin"
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        lifecycle_coordinator.register_lifecycle_notification(self._on_lifecycle_event)

    def start(self) -> None:
        """Start the sending thread; without a bridge, reports stay queued.

        Raises:
            ConfigurationError: Under FLASK_ENV=production without the bridge's
                URL and token.
        """
        if not self._bridge_client.is_configured:
            if self._settings.is_production:
                raise ConfigurationError(
                    "NOTIFICATIONS_URL and NOTIFICATIONS_TOKEN must be set "
                    "in production: without them no change report is sent"
                )
            logger.warning(
                "No notification bridge configured: change reports stay queued"
            )
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="report-sender", daemon=True
        )
        self._thread.start()

    def wake(self) -> None:
        """Have the thread look at the queue now: a report was just committed."""
        self._wake.set()

    def send_pending(self) -> bool:
        """Send the message of every household whose timer ran out, the longest-waiting first.

        Returns:
            True when every message that was due went out; False when one
            failed, which stays queued with every message after it.
        """
        session = self._session_maker()
        try:
            while not self._stop.is_set():
                party_id = self._next_due(session)
                if party_id is None:
                    session.rollback()
                    return True
                reports = list(
                    session.scalars(
                        select(ChangeReport)
                        .where(
                            ChangeReport.party_id == party_id,
                            ChangeReport.sent_at.is_(None),
                        )
                        .order_by(ChangeReport.id)
                        # Locked until the commit: another sender waits here,
                        # and finds the lines sent once it gets them.
                        .with_for_update()
                    )
                )
                # Another sender sent them while this one waited for the lock,
                # or the household changed something since and its timer runs
                # again: either way, nothing of it is due now.
                if not reports or not self._timer_ran_out(session, reports):
                    session.rollback()
                    continue
                party = session.get(Party, party_id)
                assert party is not None  # its lines go with it (ON DELETE CASCADE)
                try:
                    for message in batch_messages([r.message for r in reports]):
                        self._bridge_client.submit(
                            message, title=batch_title(party), url=self._admin_url
                        )
                except ExternalServiceException as error:
                    # Recovered: the lines stay queued, and the thread tries
                    # again after RETRY_SECONDS.
                    logger.warning(
                        "The message of %s stays queued: %s", party.name, error.message
                    )
                    session.rollback()
                    return False
                sent_at = datetime.now(UTC)
                for report in reports:
                    report.sent_at = sent_at
                session.commit()
            return False
        finally:
            session.close()

    def seconds_until_due(self) -> float | None:
        """How long until the next household's timer runs out; None with nothing queued."""
        session = self._session_maker()
        try:
            last_changes = (
                select(func.max(ChangeReport.created_at).label("last_change"))
                .where(ChangeReport.sent_at.is_(None))
                .group_by(ChangeReport.party_id)
                .subquery()
            )
            row = session.execute(
                select(func.min(last_changes.c.last_change), func.clock_timestamp())
            ).one()
            first: datetime | None = row[0]
            now: datetime = row[1]
            if first is None:
                return None
            return max((first + self._batch - now).total_seconds(), 0.0)
        finally:
            session.close()

    def shutdown(self) -> None:
        """Stop the thread. Safe to call more than once."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            wait = self._retry_seconds
            try:
                if self.send_pending():
                    due = self.seconds_until_due()
                    if due is not None:
                        wait = min(wait, max(due, _MIN_WAIT_SECONDS))
            except Exception:
                # Recovered: a database error leaves the queue as it was, and
                # the next round tries again.
                logger.exception("Sending the change reports failed")
            self._wake.wait(wait)

    def _next_due(self, session: Session) -> int | None:
        """The household whose timer ran out longest ago, or None."""
        last_change = func.max(ChangeReport.created_at)
        return session.scalars(
            select(ChangeReport.party_id)
            .where(ChangeReport.sent_at.is_(None))
            .group_by(ChangeReport.party_id)
            .having(last_change <= func.clock_timestamp() - self._batch)
            .order_by(last_change, ChangeReport.party_id)
            .limit(1)
        ).first()

    def _timer_ran_out(self, session: Session, reports: list[ChangeReport]) -> bool:
        """Whether the newest of ``reports`` is ``batch_seconds`` old."""
        now: datetime | None = session.scalar(select(func.clock_timestamp()))
        assert now is not None
        newest: datetime = max(r.created_at for r in reports)
        return newest <= now - self._batch

    def _on_lifecycle_event(self, event: LifecycleEvent) -> None:
        if event == LifecycleEvent.SHUTDOWN:
            self.shutdown()


class ReportQueue:
    """Queues a change in the request's transaction; the sender is woken after commit."""

    def __init__(self, db_session: Session, report_sender: ReportSender) -> None:
        self.db_session = db_session
        self._report_sender = report_sender

    def queue(self, party: Party, line: str) -> None:
        """Queue ``party``'s change ``line``, which starts its timer again once committed."""
        self.db_session.add(ChangeReport(party_id=party.id, message=line))
        after_commit(self._report_sender.wake)
