"""pytest-homeassistant-custom-component wiring for this repo."""
import pytest

from custom_components.avocado_irrigation import controller as controller_module

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/avocado_irrigation loadable in every test."""
    yield


@pytest.fixture(autouse=True)
def fast_startup_grace(monkeypatch):
    """The real code waits STARTUP_GRACE_SECONDS (120s) before checking for a
    stale lock on HA start -- correct in production, but every test would
    otherwise hang for two real minutes. Shrink it to near-zero everywhere
    except the one test that specifically verifies the grace period exists.
    """
    monkeypatch.setattr(controller_module, "STARTUP_GRACE_SECONDS", 0)
