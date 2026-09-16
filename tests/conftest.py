"""pytest-homeassistant-custom-component wiring for this repo."""
import pytest
import pytest_socket

from custom_components.zoneflow import controller as controller_module

pytest_plugins = "pytest_homeassistant_custom_component"

# pytest_homeassistant_custom_component registers its own pytest_runtest_setup
# hook that unconditionally calls pytest_socket.disable_socket(allow_unix_socket=True)
# before every test -- a plain function call, not something pytest-socket's own
# CLI flags (--force-enable-socket, -p no:socket) can override, since HA's hook
# runs after pytest-socket's and simply overwrites socket.socket again.
#
# On Linux this is harmless: asyncio's default event loop only needs AF_UNIX
# sockets internally, which allow_unix_socket=True permits. On Windows, the
# default ProactorEventLoop sets itself up by creating a real loopback socket
# pair, and socket.socketpair() falls back to a real AF_INET pair there (no
# native AF_UNIX socketpair on Windows) -- which this guard still blocks,
# failing every single test at fixture setup with
# "pytest_socket.SocketBlockedError" before the test body ever runs.
#
# None of these tests make real network calls (everything is faked through
# hass fixtures), so just make disable_socket() a no-op instead of trying to
# out-order HA's hook.
pytest_socket.disable_socket = lambda *args, **kwargs: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/zoneflow loadable in every test."""
    yield


@pytest.fixture(autouse=True)
def fast_startup_grace(monkeypatch):
    """The real code waits STARTUP_GRACE_SECONDS (120s) before checking for a
    stale lock on HA start -- correct in production, but every test would
    otherwise hang for two real minutes. Shrink it to near-zero everywhere
    except the one test that specifically verifies the grace period exists.
    """
    monkeypatch.setattr(controller_module, "STARTUP_GRACE_SECONDS", 0)


@pytest.fixture
async def fake_valve_services(hass):
    """Register minimal switch.turn_on/turn_off handlers that just flip the
    faked valve entity's state directly.

    Tests that exercise real pulses (test_pulse, run_deep_soak,
    run_routine_irrigation) or the watchdogs that call switch.turn_off need
    the "switch" domain's services to actually exist -- in the plain `hass`
    fixture nothing has registered them, since we never load a real switch
    platform (the tests fake VALVE's state directly with
    hass.states.async_set instead of a template/demo platform). This gives
    the controller's service calls something real to land on without
    pulling in a whole switch platform, which is the right boundary: these
    tests are verifying our controller's decisions, not Home Assistant's
    own switch component.
    """

    async def _set_state(call, target_state):
        entity_ids = call.data.get("entity_id")
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        for entity_id in entity_ids or []:
            hass.states.async_set(entity_id, target_state)

    async def _turn_on(call):
        await _set_state(call, "on")

    async def _turn_off(call):
        await _set_state(call, "off")

    hass.services.async_register("switch", "turn_on", _turn_on)
    hass.services.async_register("switch", "turn_off", _turn_off)
    yield
