"""The report queue: each change a household saves becomes one Telegram message.

The change writes its message to ``change_reports`` in its own transaction
(``ReportQueue``), and a background thread (``ReportSender``) sends the queued
messages through the notification bridge in order, marking each one sent. A
failed send stays queued and is tried again a minute later, so a household's
click never waits on Telegram or fails because of it, and no report is lost.
The backend runs as one replica, so one thread sends.
"""

import logging
import threading
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core_exceptions import ExternalServiceException
from app.exceptions import ConfigurationError
from app.models.change_report import ChangeReport
from app.services.notification_bridge_client import NotificationBridgeClient
from app.utils.after_commit import after_commit
from app.utils.lifecycle_coordinator import (
    LifecycleCoordinatorProtocol,
    LifecycleEvent,
)

logger = logging.getLogger(__name__)

RETRY_SECONDS = 60
"""How long a failed send waits, and how often the thread looks at the queue."""


class ReportSender:
    """Sends the queued reports in order, from a thread of its own."""

    def __init__(
        self,
        session_maker: sessionmaker[Session],
        bridge_client: NotificationBridgeClient,
        settings: Settings,
        lifecycle_coordinator: LifecycleCoordinatorProtocol,
        retry_seconds: float = RETRY_SECONDS,
    ) -> None:
        self._session_maker = session_maker
        self._bridge_client = bridge_client
        self._settings = settings
        self._retry_seconds = retry_seconds
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
        """Send the queued reports, oldest first, until the queue is empty or one fails.

        Returns:
            True when every queued report went out; False when one failed,
            which stays queued with every report after it.
        """
        session = self._session_maker()
        try:
            while not self._stop.is_set():
                report = session.scalars(
                    select(ChangeReport)
                    .where(ChangeReport.sent_at.is_(None))
                    .order_by(ChangeReport.id)
                    .limit(1)
                ).first()
                if report is None:
                    return True
                try:
                    self._bridge_client.submit(report.message, url=self._admin_url)
                except ExternalServiceException as error:
                    # Recovered: the report stays queued, and the thread tries
                    # again after RETRY_SECONDS.
                    logger.warning(
                        "Change report %d stays queued: %s", report.id, error.message
                    )
                    session.rollback()
                    return False
                report.sent_at = datetime.now(UTC)
                session.commit()
            return False
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
            try:
                self.send_pending()
            except Exception:
                # Recovered: a database error leaves the queue as it was, and
                # the next round tries again.
                logger.exception("Sending the change reports failed")
            self._wake.wait(self._retry_seconds)

    def _on_lifecycle_event(self, event: LifecycleEvent) -> None:
        if event == LifecycleEvent.SHUTDOWN:
            self.shutdown()


class ReportQueue:
    """Queues a report in the request's transaction; the sender sends it after commit."""

    def __init__(self, db_session: Session, report_sender: ReportSender) -> None:
        self.db_session = db_session
        self._report_sender = report_sender

    def queue(self, message: str) -> None:
        """Queue ``message``, to go out once the current transaction commits."""
        self.db_session.add(ChangeReport(message=message))
        after_commit(self._report_sender.wake)
