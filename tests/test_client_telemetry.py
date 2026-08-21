"""
Tests for telemetry notification handling and polling behavior.

This module tests the telemetry service's ability to:
1. Process Class 10 telemetry notifications
2. Update state from notifications
3. Skip polling when notifications are active
4. Fall back to polling when no notifications
"""

import struct
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from wire import class10_reply

from alpha_hwr.client import AlphaHWRClient


@pytest_asyncio.fixture
async def client():
    """Create connected client with mocked transport."""
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
        client = AlphaHWRClient("AA:BB:CC:DD:EE:FF")
        await client.connect()

        # Mock transport methods
        assert client.transport is not None
        client.transport.query = AsyncMock(return_value=b"\x00" * 7)
        client.transport.write = AsyncMock()

        yield client
        await client.disconnect()


@pytest.mark.asyncio
async def test_class10_notification_handling(client):
    """Test that Class 10 notifications update telemetry and set the stream flag."""
    # Build Class 10 Motor State packet (Sub 0x45, Obj 0x57)
    # Layout: V(4) + Pad(4) + I(4) + Pad(4) + P(4) + S(4) = 24 bytes
    volt_bytes = struct.pack(">f", 230.0)
    curr_bytes = struct.pack(">f", 1.5)
    pwr_bytes = struct.pack(">f", 45.0)
    speed_bytes = struct.pack(">f", 1500.0)
    padding = bytes(4)

    payload = (
        volt_bytes + padding + curr_bytes + padding + pwr_bytes + speed_bytes
    )

    # A motor-state reply is typed 3 version 1; nothing in it echoes the
    # Object 87 / Sub-ID 69 that was requested. The frame this replaced put
    # those in bytes 6-9, chose 0x90 as a constant "notification opcode"
    # where that byte is a payload length, and carried a dummy CRC.
    packet = class10_reply(0x0001, 0x0003, payload)

    # Send notification through telemetry service
    client.telemetry.update_from_notification(bytearray(packet))

    # Verify stream flag is set
    assert client.telemetry._has_motor_state_stream is True

    # Verify telemetry updated
    assert client.telemetry.current.speed_rpm == 1500.0
    assert client.telemetry.current.power_w == 45.0
    assert client.telemetry.current.voltage_ac_v == 230.0


@pytest.mark.asyncio
async def test_read_once_skips_polling_with_active_stream(client):
    """Test that read_once skips polling motor state when Class 10 stream is active."""
    # Set flags manually to simulate active streams
    client.telemetry._has_motor_state_stream = True
    client.telemetry._has_flow_stream = True

    # Populate temperature to prevent errors
    client.telemetry._telemetry = client.telemetry._telemetry.model_copy(
        update={"media_temperature_c": 20.0}
    )

    # Mock only temperature response (motor and flow should be skipped)
    def query_side_effect(request, timeout=2.0, match_func=None):
        """Return response for temperature query only."""
        if len(request) >= 9 and request[6:9] == bytes.fromhex("5D012C"):
            # Temperature query - return minimal valid frame
            return bytes(
                [
                    0x24,  # STX
                    0x0E,  # LEN = 14
                    0xF8,
                    0xE7,  # DST, SRC
                    0x0A,
                    0x90,  # Class 10, OpSpec
                    0x01,
                    0x2C,  # Sub ID
                    0x00,
                    0x5D,  # Obj ID
                    0x00,
                    0x00,  # Minimal payload (will be ignored)
                    0x00,
                    0x00,  # CRC
                ]
            )
        return b"\x00" * 7

    client.transport.query = AsyncMock(side_effect=query_side_effect)

    # Call read_once
    await client.telemetry.read_once()

    # Verify query was called (for Temperature only, not Motor State or Flow)
    # Should have 1 call for temperature
    assert client.transport.query.call_count == 1

    # Verify it was the temperature query
    call_args = client.transport.query.call_args[0][0]
    assert call_args[6:9] == bytes.fromhex("5D012C"), "Should query temperature"


@pytest.mark.asyncio
async def test_read_once_polls_when_no_stream(client):
    """Test that read_once polls all registers when Class 10 stream is NOT active."""
    # Flags are False by default
    assert client.telemetry._has_motor_state_stream is False
    assert client.telemetry._has_flow_stream is False

    # Mock query to return minimal valid responses
    def query_side_effect(request, timeout=2.0, match_func=None):
        """Return minimal valid frames for all queries."""
        # Determine which query based on request bytes
        if len(request) >= 9:
            sub_obj = request[6:9]
            # Extract Sub ID from frame
            if sub_obj == bytes.fromhex("570045"):  # Motor State
                return bytes(
                    [
                        0x24,
                        0x0E,
                        0xF8,
                        0xE7,
                        0x0A,
                        0x90,
                        0x00,
                        0x45,
                        0x00,
                        0x57,  # Sub/Obj
                        0x00,
                        0x00,
                        0x00,
                        0x00,  # CRC
                    ]
                )
            elif sub_obj == bytes.fromhex("5D0122"):  # Flow/Pressure
                return bytes(
                    [
                        0x24,
                        0x0E,
                        0xF8,
                        0xE7,
                        0x0A,
                        0x90,
                        0x01,
                        0x22,
                        0x00,
                        0x5D,  # Sub/Obj
                        0x00,
                        0x00,
                        0x00,
                        0x00,  # CRC
                    ]
                )
            elif sub_obj == bytes.fromhex("5D012C"):  # Temperature
                return bytes(
                    [
                        0x24,
                        0x0E,
                        0xF8,
                        0xE7,
                        0x0A,
                        0x90,
                        0x01,
                        0x2C,
                        0x00,
                        0x5D,  # Sub/Obj
                        0x00,
                        0x00,
                        0x00,
                        0x00,  # CRC
                    ]
                )
        return b"\x00" * 7

    client.transport.query = AsyncMock(side_effect=query_side_effect)

    # Call read_once
    await client.telemetry.read_once()

    # Verify query was called for all three registers
    # Motor State (0x570045), Flow/Pressure (0x5D0122), Temperature (0x5D012C)
    assert client.transport.query.call_count == 3, (
        "Should poll all three registers"
    )
