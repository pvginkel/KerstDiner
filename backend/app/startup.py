"""App-specific startup hooks.

Hook points called by create_app():
  - create_container()
  - register_blueprints()
  - register_error_handlers()
  - register_root_blueprints()

Hook points called by CLI command handlers:
  - register_cli_commands()
  - post_migration_hook()
  - load_test_data_hook()
"""

from __future__ import annotations

import sys
from typing import cast

import click
from flask import Blueprint, Flask

from app.exceptions import ConfigurationError
from app.services.container import ServiceContainer


def create_container() -> ServiceContainer:
    """Create and configure the application's service container."""
    return ServiceContainer()


def register_blueprints(api_bp: Blueprint, app: Flask) -> None:
    """Register all app-specific blueprints on api_bp (under /api prefix)."""
    # api_bp is the process's one; a second app (the tests build several)
    # finds it registered already, with these on it.
    if api_bp._got_registered_once:
        return

    from app.api.admin import admin_bp
    from app.api.dishes import dishes_bp
    from app.api.party import party_bp
    from app.api.tableware import tableware_bp
    from app.api.testing_reset import testing_reset_bp

    api_bp.register_blueprint(party_bp)
    api_bp.register_blueprint(dishes_bp)
    api_bp.register_blueprint(tableware_bp)
    api_bp.register_blueprint(admin_bp)
    api_bp.register_blueprint(testing_reset_bp)


def register_error_handlers(app: Flask) -> None:
    """Register app-specific error handlers."""
    pass


def register_root_blueprints(app: Flask) -> None:
    """Register app-specific blueprints directly on the app (not under /api prefix).

    Use this for internal endpoints, WebSocket handlers, or other routes
    that should not be nested under the /api URL prefix.
    """
    pass


def register_cli_commands(cli: click.Group) -> None:
    """Register app-specific CLI commands."""
    pass


def post_migration_hook(app: Flask) -> None:
    """Sync the config file into the database: the deploy's migration step.

    An invalid config file stops the step with exit status 1, so the deploy
    fails and the previous version keeps running.
    """
    sync_config_file(app)


def load_test_data_hook(app: Flask) -> None:
    """Load the config file into the recreated database, as a deploy would."""
    sync_config_file(app)


def sync_config_file(app: Flask) -> None:
    """Apply ``app/data/kerstdiner.yaml`` in one transaction, or exit 1 when it is invalid."""
    from app.app import App
    from app.schemas.config_file import CONFIG_FILE, load_config_file

    container = cast(App, app).container
    with app.app_context():
        try:
            config = load_config_file(CONFIG_FILE)
        except ConfigurationError as error:
            print(f"Config sync failed: {error}", file=sys.stderr)
            sys.exit(1)
        session = container.db_session()
        try:
            summary = container.config_sync_service().sync(config)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            container.db_session.reset()
    if summary.reset:
        print(f"Config reset {config.reset}: every answer, claim and link cleared")
    print(
        f"Config synced: {summary.households} households, {summary.dishes} dishes, "
        f"{summary.servies} servies items"
    )
