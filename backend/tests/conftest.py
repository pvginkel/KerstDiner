"""Pytest configuration and fixtures.

Infrastructure fixtures (app, client, session, OIDC, SSE) are defined in
conftest_infrastructure.py. This file re-exports them and adds app-specific
domain fixtures.

A fixture defined here after the import replaces the template's fixture of
the same name. To change the settings the test apps are built from, replace
``test_settings`` or ``test_app_settings``. With a database they are
session-scoped, because the app is, and a replacement keeps that scope.

A process the suite starts builds its app from the environment and ``.env``
alone, not from these fixtures (``tests/test_openapi_cache.py`` builds one
for the OpenAPI document). A setting the app cannot start without, which
only a fixture here gives, gets a default for those processes at the top of
this file, after the imports: ``os.environ.setdefault("MY_SETTING", "value")``.
Without one the suite passes where ``.env`` sets it, and fails in CI.
"""

from collections.abc import Callable
from typing import Any

import pytest

from app.schemas.config_file import KerstDinerConfig
from app.services.config_sync_service import AppliedConfig
from app.services.container import ServiceContainer

# Import all infrastructure fixtures
from tests.conftest_infrastructure import *  # noqa: F403

# ---------------------------------------------------------------------------
# KerstDiner's fixtures
# ---------------------------------------------------------------------------

# The run's databases are built by the revisions and the post-migration hook,
# so they hold app/data/kerstdiner.yaml's test data. A test that needs a
# known state applies a config of its own with ``apply_config`` or ``seeded``,
# which wipe that first.
SEED_CONFIG: dict[str, Any] = {
    "reset": 1,
    "households": [
        {
            "key": "jansen",
            "name": "Familie Jansen",
            "guess": {"vegetarisch": 1, "normaal": 2, "kind": 2},
        },
        {"key": "de-boer", "name": "Familie de Boer", "guess": {"normaal": 2}},
        {"key": "tante-els", "name": "Tante Els", "guess": {"vegan": 1}},
    ],
    "dishes": [
        {"key": "soep", "name": "Pompoensoep", "image": "pompoensoep.jpg"},
        {"key": "rollade", "name": "Rollade", "for": ["normaal"]},
        {
            "key": "wellington",
            "name": "Linzen-wellington",
            "for": ["vegan", "vegetarisch"],
            "image": "wellington.jpg",
        },
    ],
    "servies": [
        {"key": "borden", "text": "20 borden", "image": "borden.jpg"},
        {"key": "glazen", "text": "20 wijnglazen"},
    ],
}
"""Three households, three dishes and two servies items, nobody answered yet."""


@pytest.fixture
def apply_config(
    container: ServiceContainer,
) -> Callable[[dict[str, Any]], AppliedConfig]:
    """Wipe the state and apply a config of the test's own, in the test's session."""

    def _apply(config: dict[str, Any]) -> AppliedConfig:
        return container.config_sync_service().replace_all(
            KerstDinerConfig.model_validate(config)
        )

    return _apply


@pytest.fixture
def seeded(apply_config: Callable[[dict[str, Any]], AppliedConfig]) -> AppliedConfig:
    """``SEED_CONFIG`` applied: parties, dishes and servies in config order."""
    return apply_config(SEED_CONFIG)


def link_headers(link_token: str) -> dict[str, str]:
    """The headers of a household's request."""
    return {"X-Link-Token": link_token}
