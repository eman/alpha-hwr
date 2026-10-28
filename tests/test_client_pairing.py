"""
Tests for BLE pairing/bonding via AlphaHWRClient.bond().

The pump starts the pairing: in pairing mode it sends a security request
as soon as the link opens, and on Linux BlueZ answers it only if a pairing
agent is registered. So what these pin down is the order - agent first,
then the connection, then ``pair()`` - and that a bond the pump's own
request already completed counts as success.

Note: `bluez_pairing_agent()` talks to the real system D-Bus/BlueZ on
Linux. It is patched out with a recorder in these tests so they don't
depend on (or mutate) real BlueZ state on the test host.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from alpha_hwr.client import AlphaHWRClient
from alpha_hwr.exceptions import ConnectionError


@pytest_asyncio.fixture
async def pump():
    """
    A mocked BleakClient, and the order things happened in.

    Yields ``(bleak, events)``. The client is not connected yet.
    """
    events: list[str] = []

    @contextlib.asynccontextmanager
    async def recording_agent(address=None):
        events.append(f"agent up for {address}")
        try:
            yield
        finally:
            events.append("agent down")

    with (
        patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak,
        patch(
            "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
            new_callable=AsyncMock,
        ),
        patch(
            "alpha_hwr.client.bluez_pairing_agent",
            side_effect=recording_agent,
        ),
    ):
        bleak = AsyncMock()
        bleak.connect = AsyncMock(
            side_effect=lambda **_: events.append("connect")
        )
        bleak.pair = AsyncMock(side_effect=lambda: events.append("pair"))
        bleak.disconnect = AsyncMock()
        bleak.start_notify = AsyncMock()
        bleak.write_gatt_char = AsyncMock()
        bleak.is_connected = True
        mock_bleak.return_value = bleak
        yield bleak, events


def new_client() -> AlphaHWRClient:
    return AlphaHWRClient("AA:BB:CC:DD:EE:FF", auto_authenticate=False)


@pytest.mark.asyncio
async def test_the_agent_is_up_before_the_link_opens(pump):
    """The pump's security request arrives on connect; BlueZ needs the agent."""
    _, events = pump
    client = new_client()

    await client.bond()

    assert events == [
        "agent up for AA:BB:CC:DD:EE:FF",
        "connect",
        "pair",
        "agent down",
    ]
    await client.disconnect()


@pytest.mark.asyncio
async def test_an_existing_connection_is_reused(pump):
    bleak, events = pump
    client = new_client()
    await client.connect()
    events.clear()

    await client.bond()

    assert events == ["agent up for AA:BB:CC:DD:EE:FF", "pair", "agent down"]
    bleak.connect.assert_awaited_once()
    await client.disconnect()


@pytest.mark.asyncio
async def test_a_bond_the_pump_already_completed_is_success(pump):
    """BlueZ's Pair() says AlreadyExists when the security request won."""
    bleak, _ = pump
    bleak.pair.side_effect = Exception(
        "[org.bluez.Error.AlreadyExists] Already Exists"
    )
    client = new_client()

    await client.bond()

    await client.disconnect()


@pytest.mark.asyncio
async def test_a_failed_pairing_raises_connection_error(pump):
    bleak, events = pump
    bleak.pair.side_effect = Exception(
        "[org.bluez.Error.AuthenticationFailed] Authentication Failed"
    )
    client = new_client()

    with pytest.raises(ConnectionError, match="AuthenticationFailed"):
        await client.bond()

    assert events[-1] == "agent down", "the agent is removed on failure too"
    await client.disconnect()


@pytest.mark.asyncio
async def test_bond_translates_not_implemented_error(pump):
    """bond() raises a clear ConnectionError on unsupported platforms."""
    bleak, _ = pump
    bleak.pair.side_effect = NotImplementedError()
    client = new_client()

    with pytest.raises(ConnectionError, match="not supported on this platform"):
        await client.bond()

    await client.disconnect()


@pytest.mark.asyncio
async def test_bond_needs_an_address(pump):
    """
    The agent is the host's default while it is up, and is told which
    device to accept. Without an address it would accept any.
    """
    _, events = pump
    client = AlphaHWRClient(None, auto_authenticate=False)
    client.address = None  # not even from settings

    with pytest.raises(ConnectionError, match="address"):
        await client.bond()

    assert events == [], "nothing registered, nothing connected"


def test_there_is_no_unbond():
    """
    Removing the host's bond strands the pump.

    The pump keeps its half and refuses the host until it is re-paired at
    the unit, so the client does not offer the operation.
    """
    assert not hasattr(AlphaHWRClient, "unbond")


@pytest.mark.asyncio
async def test_an_agent_bluez_refuses_is_a_connection_error():
    """
    RegisterAgent or RequestDefaultAgent failing is a pairing failure,
    and surfaces as the ConnectionError bond() documents.
    """

    @contextlib.asynccontextmanager
    async def refused_agent(address=None):
        raise RuntimeError("[org.bluez.Error.AlreadyExists] Already Exists")
        yield

    with patch(
        "alpha_hwr.client.bluez_pairing_agent", side_effect=refused_agent
    ):
        client = new_client()
        with pytest.raises(ConnectionError, match="pairing failed"):
            await client.bond()
