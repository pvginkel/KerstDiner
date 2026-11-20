"""Dependency injection container for services."""

from collections.abc import Callable
from typing import Any

from dependency_injector import containers, providers
from sqlalchemy.orm import sessionmaker

from app.app_config import AppSettings
from app.config import Settings
from app.services.auth_service import AuthService
from app.services.config_sync_service import ConfigSyncService
from app.services.dish_service import DishService
from app.services.health_service import HealthService
from app.services.metrics_service import MetricsService
from app.services.notification_bridge_client import NotificationBridgeClient
from app.services.oidc_client_service import OidcClientService
from app.services.party_service import PartyService
from app.services.report_service import ReportQueue, ReportSender
from app.services.sse_connection_manager import SSEConnectionManager
from app.services.tableware_service import TablewareService
from app.services.task_service import TaskService
from app.services.testing_service import TestingService
from app.utils.lifecycle_coordinator import LifecycleCoordinator
from app.utils.temp_file_manager import TempFileManager

# Background service startup registry. Services register lambdas here
# (co-located with their provider definitions) that are invoked by
# start_background_services() during app startup.
_background_starters: list[Callable[[Any], None]] = []


def register_for_background_startup(fn: Callable[[Any], None]) -> None:
    """Register a callable to be invoked during background service startup."""
    _background_starters.append(fn)


class ServiceContainer(containers.DeclarativeContainer):
    """Container for service dependency injection."""

    # Configuration providers
    config = providers.Dependency(instance_of=Settings)
    app_config = providers.Dependency(instance_of=AppSettings)
    session_maker = providers.Dependency(instance_of=sessionmaker)
    db_session = providers.ContextLocalSingleton(session_maker.provided.call())

    # Lifecycle coordinator - manages startup and graceful shutdown
    lifecycle_coordinator = providers.Singleton(
        LifecycleCoordinator,
        graceful_shutdown_timeout=config.provided.graceful_shutdown_timeout,
    )

    # Health service - services register their own readiness checks with it
    health_service = providers.Singleton(
        HealthService,
        lifecycle_coordinator=lifecycle_coordinator,
        settings=config,
    )

    # Testing service - test sessions, content generation, the SSE test hooks
    testing_service = providers.Factory(TestingService)

    # Temp file manager
    temp_file_manager = providers.Singleton(
        TempFileManager,
        lifecycle_coordinator=lifecycle_coordinator,
    )
    register_for_background_startup(
        lambda c: c.temp_file_manager().start_cleanup_thread()
    )

    # Metrics service - background thread for Prometheus metrics
    metrics_service = providers.Singleton(
        MetricsService,
        container=providers.Self(),
        lifecycle_coordinator=lifecycle_coordinator,
    )

    # Auth services - OIDC authentication. /admin's endpoints require the
    # client role "admin" (@allow_roles("admin")); the household endpoints are
    # @public and carry the household's link token.
    auth_service = providers.Singleton(AuthService, config=config, admin_role="admin")
    oidc_client_service = providers.Singleton(OidcClientService, config=config)

    # SSE connection manager (always included - TaskService depends on it)
    sse_connection_manager = providers.Singleton(
        SSEConnectionManager,
        lifecycle_coordinator=lifecycle_coordinator,
    )

    # Task service - in-memory task management
    task_service = providers.Singleton(
        TaskService,
        lifecycle_coordinator=lifecycle_coordinator,
        sse_connection_manager=sse_connection_manager,
        max_workers=config.provided.task_max_workers,
        task_timeout=config.provided.task_timeout_seconds,
        cleanup_interval=config.provided.task_cleanup_interval_seconds,
    )
    register_for_background_startup(lambda c: c.task_service().startup())

    # The report queue: the notification bridge, the thread that sends the
    # queued reports, and the queue the household's changes write to.
    notification_bridge_client = providers.Singleton(
        NotificationBridgeClient,
        base_url=app_config.provided.notification_bridge_url,
        token=app_config.provided.notification_bridge_token,
        health_service=health_service,
    )
    report_sender = providers.Singleton(
        ReportSender,
        session_maker=session_maker,
        bridge_client=notification_bridge_client,
        settings=config,
        lifecycle_coordinator=lifecycle_coordinator,
    )
    register_for_background_startup(lambda c: c.report_sender().start())
    report_queue = providers.Factory(
        ReportQueue, db_session=db_session, report_sender=report_sender
    )

    # KerstDiner's domain services, one per request's session
    config_sync_service = providers.Factory(ConfigSyncService, db_session=db_session)
    party_service = providers.Factory(
        PartyService, db_session=db_session, report_queue=report_queue
    )
    dish_service = providers.Factory(
        DishService, db_session=db_session, report_queue=report_queue
    )
    tableware_service = providers.Factory(
        TablewareService, db_session=db_session, report_queue=report_queue
    )


def start_background_services(container: Any) -> None:
    """Eagerly instantiate and start all registered background services."""
    for starter in _background_starters:
        starter(container)
