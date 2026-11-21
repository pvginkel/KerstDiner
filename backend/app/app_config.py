"""Application-specific configuration.

This module implements app-specific configuration that is separate from the
infrastructure configuration in config.py.
"""

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import Sensitive, dump_config_for_logging

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AppEnvironment(BaseSettings):
    """Raw environment variable loading for app-specific settings."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    NOTIFICATIONS_URL: str = Field(
        default="",
        description=(
            "The notification bridge's base URL, such as "
            "http://notification-bridge.<namespace>.svc:8090; empty: no bridge, "
            "and the change reports stay queued (refused under FLASK_ENV=production)"
        ),
    )
    NOTIFICATIONS_TOKEN: str = Field(
        default="",
        description="The bearer token of the bridge's kerstdiner registration",
    )
    REPORT_BATCH_SECONDS: float = Field(
        default=300,
        ge=0,
        description=(
            "How long a household's timer runs: its changes go to Telegram in one "
            "message once this many seconds pass without another change"
        ),
    )


class AppSettings(BaseModel):
    """Application-specific settings.

    Annotate every field that holds a secret ``Annotated[str, Sensitive]``
    (``from app.config import Sensitive``): run.py logs these settings at boot.
    """

    model_config = ConfigDict(from_attributes=True)

    notification_bridge_url: str = ""
    notification_bridge_token: Annotated[str, Sensitive] = ""
    report_batch_seconds: float = 300

    def dump_for_logging(self) -> dict[str, str]:
        """Every setting, for the boot log, with the Sensitive ones as ``***``."""
        return dump_config_for_logging(self)

    @classmethod
    def load(
        cls, env: "AppEnvironment | None" = None, flask_env: str = "development"
    ) -> "AppSettings":
        """Load app settings from environment variables."""
        if env is None:
            env = AppEnvironment()
        return cls(
            notification_bridge_url=env.NOTIFICATIONS_URL,
            notification_bridge_token=env.NOTIFICATIONS_TOKEN,
            report_batch_seconds=env.REPORT_BATCH_SECONDS,
        )
