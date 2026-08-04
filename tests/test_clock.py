"""Tests for time/clock operations."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from alpha_hwr.client import AlphaHWRClient


@pytest_asyncio.fixture
async def client():
    """Create a connected client with mocked transport."""
    with (
        patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak,
        patch(
            "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
            new_callable=AsyncMock,
        ),
    ):
        # Set up mock BleakClient
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        mock_instance.start_notify = AsyncMock()
        mock_instance.write_gatt_char = AsyncMock()
        mock_instance.is_connected = True
        mock_bleak.return_value = mock_instance

        # Create and connect client
        client = AlphaHWRClient("XX:XX:XX:XX:XX:XX")
        await client.connect()

        # Mock transport methods
        assert client.transport is not None
        client.transport.write = AsyncMock()
        client.transport.read_response = AsyncMock(return_value=b"\x00" * 7)
        client.transport.send_with_response = AsyncMock(
            return_value=b"\x00" * 7
        )
        client.transport.query = AsyncMock(return_value=b"\x00" * 7)

        yield client
        await client.disconnect()


@pytest.mark.asyncio
async def test_get_clock_object_94(client):
    """Test reading clock from Object 94, Sub 101 (DateTimeActual)."""

    # Mock response for Object 94, Sub 101
    # Frame: [STX][LEN][DST][SRC][Class][OpSpec][ObjH][ObjL][SubH][SubL]
    # Followed by: [StatH][StatL][DataLen][Data...]
    # Date: 2026-01-30 07:34:42
    # Data format: [00 00 0c] [07 ea 01 1e 07 22 2a ...] (year=2026, month=1, day=30, hour=7, min=34, sec=42)
    mock_resp = bytes.fromhex(
        "2417f8e70a13005ef8e700000c07ea011e07222a0102050102abcd"
    )

    client.transport.query = AsyncMock(return_value=mock_resp)

    clock = await client.time.get_clock()

    assert clock is not None
    assert clock.year == 2026
    assert clock.month == 1
    assert clock.day == 30
    assert clock.hour == 7
    assert clock.minute == 34
    assert clock.second == 42


@pytest.mark.asyncio
async def test_set_clock_object_94(client):
    """Test setting clock via Object 94.

    set_clock now uses standard Class 10 SET via build_data_object_set,
    sending through transport.query() and verifying with a read-back.
    """
    # ACK for the SET command
    ack_resp = b"\x24\x05\xf8\xe7\x0a\x01\x00\xae\xa2"

    # Verification read-back response
    # Date: 2026-01-30 11:35:00
    verify_resp = bytes.fromhex(
        "2417f8e70a13005ef8e700000c07ea011e0b23000102050102abcd"
    )
    client.transport.query = AsyncMock(side_effect=[ack_resp, verify_resp])

    dt = datetime(2026, 1, 30, 11, 35, 0)  # noqa: DTZ001  # pump wall clock is naive
    success = await client.time.set_clock(dt)

    assert success is True
    # Two query calls: SET + read-back verification
    assert client.transport.query.call_count == 2
