"""
Tests for the BlueZ pairing agent helper (core/pairing_agent.py).

These mock bleak's global BlueZ manager and the D-Bus message bus so that
tests never touch the real system D-Bus / BlueZ daemon, even when running
on a Linux host that has bluetoothd running.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alpha_hwr.core.pairing_agent import (
    AGENT_CAPABILITY,
    AGENT_PATH,
    bluez_pairing_agent,
)

PUMP = "AA:BB:CC:DD:EE:FF"
PUMP_PATH = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"


@pytest.fixture
def linux(monkeypatch):
    """
    Run the Linux path whatever the host is.

    The agent is a no-op off Linux, so these would assert against nothing
    there; dbus_fast and bleak's BlueZ backend may not import there either.
    """
    pytest.importorskip("dbus_fast")
    pytest.importorskip("bleak.backends.bluezdbus.manager")
    monkeypatch.setattr(sys, "platform", "linux")


def fake_bluez():
    """A bus and agent manager that record calls, and the patched manager."""
    bus = MagicMock()
    bus.introspect = AsyncMock(return_value=MagicMock())
    agent_manager = MagicMock()
    agent_manager.call_register_agent = AsyncMock()
    agent_manager.call_request_default_agent = AsyncMock()
    agent_manager.call_unregister_agent = AsyncMock()
    bus.get_proxy_object.return_value.get_interface.return_value = agent_manager
    manager = MagicMock()
    manager._bus = bus
    patched = patch(
        "bleak.backends.bluezdbus.manager.get_global_bluez_manager",
        new=AsyncMock(return_value=manager),
    )
    return bus, agent_manager, patched


@pytest.mark.asyncio
async def test_noop_on_non_linux_platform():
    """bluez_pairing_agent() is a no-op on non-Linux platforms."""
    with patch.object(sys, "platform", "darwin"):
        async with bluez_pairing_agent():
            pass  # Should not raise, and should not touch D-Bus at all.


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_noop_when_dbus_fast_unavailable(monkeypatch):
    """Falls back to a no-op if the dbus_fast import fails."""
    # Setting a sys.modules entry to None forces the next `import` of that
    # module to raise ImportError, simulating dbus_fast being unavailable.
    monkeypatch.setitem(sys.modules, "dbus_fast.service", None)

    async with bluez_pairing_agent():
        pass  # Should not raise, and should not touch D-Bus at all.


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_registers_and_unregisters_agent():
    """Registers a NoInputNoOutput agent and cleans up on exit."""
    mock_bus = MagicMock()
    mock_bus.export = MagicMock()
    mock_bus.unexport = MagicMock()
    mock_bus.introspect = AsyncMock(return_value=MagicMock())

    mock_agent_manager = MagicMock()
    mock_agent_manager.call_register_agent = AsyncMock()
    mock_agent_manager.call_request_default_agent = AsyncMock()
    mock_agent_manager.call_unregister_agent = AsyncMock()

    mock_proxy = MagicMock()
    mock_proxy.get_interface.return_value = mock_agent_manager
    mock_bus.get_proxy_object.return_value = mock_proxy

    mock_manager = MagicMock()
    mock_manager._bus = mock_bus

    with patch(
        "bleak.backends.bluezdbus.manager.get_global_bluez_manager",
        new=AsyncMock(return_value=mock_manager),
    ):
        async with bluez_pairing_agent():
            # Agent should be registered and set as default before the
            # caller's pairing operation runs.
            mock_bus.export.assert_called_once()
            assert mock_bus.export.call_args[0][0] == AGENT_PATH
            mock_agent_manager.call_register_agent.assert_awaited_once_with(
                AGENT_PATH, AGENT_CAPABILITY
            )
            mock_agent_manager.call_request_default_agent.assert_awaited_once_with(
                AGENT_PATH
            )
            mock_agent_manager.call_unregister_agent.assert_not_awaited()

    # After the context exits, the agent should be unregistered and unexported.
    mock_agent_manager.call_unregister_agent.assert_awaited_once_with(
        AGENT_PATH
    )
    mock_bus.unexport.assert_called_once_with(AGENT_PATH)


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_unregisters_agent_even_if_body_raises():
    """The agent is still cleaned up if the caller's operation fails."""
    mock_bus = MagicMock()
    mock_bus.export = MagicMock()
    mock_bus.unexport = MagicMock()
    mock_bus.introspect = AsyncMock(return_value=MagicMock())

    mock_agent_manager = MagicMock()
    mock_agent_manager.call_register_agent = AsyncMock()
    mock_agent_manager.call_request_default_agent = AsyncMock()
    mock_agent_manager.call_unregister_agent = AsyncMock()

    mock_proxy = MagicMock()
    mock_proxy.get_interface.return_value = mock_agent_manager
    mock_bus.get_proxy_object.return_value = mock_proxy

    mock_manager = MagicMock()
    mock_manager._bus = mock_bus

    with (
        patch(
            "bleak.backends.bluezdbus.manager.get_global_bluez_manager",
            new=AsyncMock(return_value=mock_manager),
        ),
        pytest.raises(RuntimeError, match="pairing failed"),
    ):
        async with bluez_pairing_agent():
            raise RuntimeError("pairing failed")

    mock_agent_manager.call_unregister_agent.assert_awaited_once_with(
        AGENT_PATH
    )
    mock_bus.unexport.assert_called_once_with(AGENT_PATH)


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_noop_when_bus_unavailable():
    """No agent is registered if the BlueZ manager has no bus."""
    mock_manager = MagicMock()
    mock_manager._bus = None

    with patch(
        "bleak.backends.bluezdbus.manager.get_global_bluez_manager",
        new=AsyncMock(return_value=mock_manager),
    ):
        async with bluez_pairing_agent():
            pass


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_requests_for_other_devices_are_rejected():
    """
    The agent is the host's default while it is up, so it hears every
    device's requests. It accepts the pump's and rejects the rest.
    """
    from dbus_fast.errors import DBusError

    bus, _, patched = fake_bluez()
    with patched:
        async with bluez_pairing_agent(PUMP):
            agent = bus.export.call_args[0][1]

            agent.RequestConfirmation(PUMP_PATH, 0)
            agent.RequestAuthorization(PUMP_PATH)
            agent.AuthorizeService(
                PUMP_PATH, "0000fdd0-0000-1000-8000-00805f9b34fb"
            )

            other = "/org/bluez/hci0/dev_11_22_33_44_55_66"
            for call in (
                lambda: agent.RequestConfirmation(other, 0),
                lambda: agent.RequestAuthorization(other),
                lambda: agent.AuthorizeService(
                    other, "0000110b-0000-1000-8000-00805f9b34fb"
                ),
            ):
                with pytest.raises(DBusError):
                    call()


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_a_lowercase_address_still_matches():
    bus, _, patched = fake_bluez()
    with patched:
        async with bluez_pairing_agent(PUMP.lower()):
            bus.export.call_args[0][1].RequestAuthorization(PUMP_PATH)


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_concurrent_agents_take_turns():
    """
    They share one object path. Overlapping, the second export would fail
    and its cleanup would tear down the first agent mid-pairing.
    """
    bus, _, patched = fake_bluez()
    events: list[str] = []
    bus.export.side_effect = lambda *_: events.append("export")
    bus.unexport.side_effect = lambda *_: events.append("unexport")

    async def pair(label: str) -> None:
        async with bluez_pairing_agent(PUMP):
            events.append(f"{label} pairing")
            await asyncio.sleep(0)
            events.append(f"{label} done")

    with patched:
        await asyncio.gather(pair("first"), pair("second"))

    assert events == [
        "export",
        "first pairing",
        "first done",
        "unexport",
        "export",
        "second pairing",
        "second done",
        "unexport",
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux")
async def test_a_failed_export_unexports_nothing():
    """The path may belong to someone else; only remove what was exported."""
    bus, agent_manager, patched = fake_bluez()
    bus.export.side_effect = ValueError("already exported")

    with patched, pytest.raises(ValueError, match="already exported"):
        async with bluez_pairing_agent(PUMP):
            pass

    bus.unexport.assert_not_called()
    agent_manager.call_unregister_agent.assert_not_awaited()
