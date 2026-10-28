"""
Tests for the BlueZ pairing agent helper (core/pairing_agent.py).

These mock bleak's global BlueZ manager and the D-Bus message bus so that
tests never touch the real system D-Bus / BlueZ daemon, even when running
on a Linux host that has bluetoothd running.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alpha_hwr.core.pairing_agent import (
    AGENT_CAPABILITY,
    AGENT_PATH,
    bluez_pairing_agent,
)


@pytest.mark.asyncio
async def test_noop_on_non_linux_platform():
    """bluez_pairing_agent() is a no-op on non-Linux platforms."""
    with patch.object(sys, "platform", "darwin"):
        async with bluez_pairing_agent():
            pass  # Should not raise, and should not touch D-Bus at all.


@pytest.mark.asyncio
async def test_noop_when_dbus_fast_unavailable(monkeypatch):
    """Falls back to a no-op if the dbus_fast import fails."""
    # Setting a sys.modules entry to None forces the next `import` of that
    # module to raise ImportError, simulating dbus_fast being unavailable.
    monkeypatch.setitem(sys.modules, "dbus_fast.service", None)

    async with bluez_pairing_agent():
        pass  # Should not raise, and should not touch D-Bus at all.


@pytest.mark.asyncio
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
