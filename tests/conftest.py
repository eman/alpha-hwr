"""
Shared pytest fixtures for all tests.

This module provides common fixtures that can be used across all test files.
"""

import asyncio
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from hypothesis import strategies as st
from alpha_hwr.client import AlphaHWRClient


@st.composite
def valid_frame_bytes(draw):
    """Generate valid GENI frame bytes for protocol testing.
    
    Generates random but valid frame structures for edge case testing.
    Useful for hypothesis-based property testing of frame parsing.
    """
    # Frame header
    stx = bytes([0x27])
    dst = bytes([0xE7])
    src = bytes([0xF8])
    
    # Random payload (0-100 bytes)
    payload_len = draw(st.integers(min_value=0, max_value=100))
    payload = draw(st.binary(min_size=payload_len, max_size=payload_len))
    
    # Frame length = DST + SRC + rest of frame (excluding STX and CRC)
    apdu_length = 4 + len(payload)  # Class + OpSpec + ObjID + SubID + Payload
    length = 2 + apdu_length
    
    frame = stx + bytes([length]) + dst + src + bytes([0x0A]) + bytes([0x43])
    frame += bytes([0x00, 0x01, 0x00, 0x01])  # ObjectID and SubID
    frame += payload
    frame += bytes([0x00, 0x00])  # Dummy CRC
    
    return frame


@st.composite
def valid_telemetry_values(draw):
    """Generate realistic telemetry values for testing.
    
    Generates flow, head, power values within realistic pump operating ranges.
    """
    return {
        "flow_m3h": draw(st.floats(
            min_value=0.0, 
            max_value=10.0, 
            allow_nan=False, 
            allow_infinity=False
        )),
        "head_m": draw(st.floats(
            min_value=0.0, 
            max_value=10.0, 
            allow_nan=False, 
            allow_infinity=False
        )),
        "power_w": draw(st.floats(
            min_value=0.0, 
            max_value=500.0, 
            allow_nan=False, 
            allow_infinity=False
        )),
    }


@st.composite
def valid_pressure_values(draw):
    """Generate valid pressure control setpoints."""
    return draw(st.floats(
        min_value=0.1,
        max_value=6.0,
        allow_nan=False,
        allow_infinity=False
    ))


def build_class10_response(obj_id: int, sub_id: int, payload: bytes) -> bytes:
    """
    Build a complete GENI frame for Class 10 response.

    This helper constructs a valid GENI protocol frame that BaseService._read_class10_object
    expects. The frame structure is:
    [STX][LEN][DST][SRC][Class][OpSpec][ObjH][ObjL][SubH][SubL][...PAYLOAD...][CRC_H][CRC_L]

    Note: Response frames have a 2-byte Object ID (ObjH, ObjL), unlike request frames which
    use a 1-byte Object ID. This matches the protocol specification.

    Args:
        obj_id: Object ID (0-255)
        sub_id: Sub-ID (0-65535)
        payload: Data payload bytes

    Returns:
        Complete GENI frame ready for transport.query() mock response

    Example:
        >>> payload = bytes([0x00, 0x01, 0x02])
        >>> frame = build_class10_response(84, 1, payload)
        >>> mock_client.transport.query = AsyncMock(return_value=frame)
    """
    # Response APDU = Class + OpSpec + ObjH + ObjL + SubH + SubL + Payload (6 byte header)
    apdu_length = 6 + len(payload)
    # Length field = DST + SRC + APDU (everything except STX, LEN, and CRC)
    length = 2 + apdu_length

    frame = bytearray(
        [
            0x27,  # STX (start of transmission)
            length,  # Length (DST + SRC + APDU)
            0xE7,  # DST (destination address - host)
            0xF8,  # SRC (source address - pump)
            0x0A,  # Class 10 (Configuration/DataObject)
            0x43,  # OpSpec (response code)
            0x00,  # Object ID high byte (responses use 2 bytes)
            obj_id & 0xFF,  # Object ID low byte
            (sub_id >> 8) & 0xFF,  # Sub-ID high byte
            sub_id & 0xFF,  # Sub-ID low byte
        ]
    )
    frame.extend(payload)

    # Add dummy CRC (tests don't validate CRC)
    frame.extend([0x00, 0x00])

    return bytes(frame)


@pytest_asyncio.fixture
async def mock_client_simple():
    """
    Fixture providing a mocked AlphaHWRClient with AsyncMock transport.

    This fixture properly handles async cleanup to prevent test hangs.
    Use this for tests that mock at the transport level.

    Example:
        @pytest.mark.asyncio
        async def test_something(mock_client_simple):
            # Client is already connected
            result = await mock_client_simple.control.start()
            assert result
    """
    with patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak:
        # Set up mock BleakClient instance
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        mock_instance.start_notify = AsyncMock()
        mock_instance.write_gatt_char = AsyncMock()
        mock_instance.is_connected = True
        mock_bleak.return_value = mock_instance

        # Create client and connect
        client = AlphaHWRClient("AA:BB:CC:DD:EE:FF")
        await client.connect()

        # Mock transport methods to return minimal valid responses
        assert client.transport is not None, "Transport should be initialized"
        client.transport.write = AsyncMock()
        client.transport.read_response = AsyncMock(return_value=b"\x00" * 7)
        client.transport.send_with_response = AsyncMock(
            return_value=b"\x00" * 7
        )
        client.transport.query = AsyncMock(return_value=b"\x00" * 7)

        yield client

        # Cleanup - be aggressive about cleanup to prevent hangs
        try:
            if hasattr(client, "is_connected") and client.is_connected:
                await client.disconnect()
        except Exception:
            pass

        # Allow event loop to process any pending cleanup tasks
        await asyncio.sleep(0)


@pytest_asyncio.fixture
async def mock_client_with_pump():
    """
    Fixture providing a mocked AlphaHWRClient with full MockPump backend.

    This fixture uses the MockPump and MockBleakClient for realistic behavior.
    Use this for integration-style tests that need realistic pump responses.

    Example:
        @pytest.mark.asyncio
        async def test_control_flow(mock_client_with_pump):
            await mock_client_with_pump.control.start()
            telemetry = await mock_client_with_pump.telemetry.read_once()
            assert telemetry.speed_rpm > 0
    """
    import sys
    from pathlib import Path

    # Add tests directory to path for mocks import
    tests_dir = Path(__file__).parent
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))

    from mocks.mock_transport import MockBleakClient

    with patch("alpha_hwr.client.BleakClient", MockBleakClient):
        client = AlphaHWRClient("MOCK")
        await client.connect()
        yield client

        # Cleanup
        if client.is_connected:
            await client.disconnect()

        # Give async tasks time to clean up
        await asyncio.sleep(0.1)
