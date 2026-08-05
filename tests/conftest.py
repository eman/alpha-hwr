"""
Shared pytest fixtures for all tests.

This module provides common fixtures that can be used across all test files.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from hypothesis import strategies as st

from alpha_hwr.client import AlphaHWRClient

# Explicitly load the benchmark plugin to ensure the fixture is available
pytest_plugins = ["pytest_benchmark"]


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
    apdu_length = 4 + len(
        payload
    )  # 4 bytes for ObjID (2) + SubID (2) plus payload
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
        "flow_m3h": draw(
            st.floats(
                min_value=0.0,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            )
        ),
        "head_m": draw(
            st.floats(
                min_value=0.0,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            )
        ),
        "power_w": draw(
            st.floats(
                min_value=0.0,
                max_value=500.0,
                allow_nan=False,
                allow_infinity=False,
            )
        ),
    }


@st.composite
def valid_pressure_values(draw):
    """Generate valid pressure control setpoints."""
    return draw(
        st.floats(
            min_value=0.1, max_value=6.0, allow_nan=False, allow_infinity=False
        )
    )


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
    with (
        patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak,
        patch(
            "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
            new_callable=AsyncMock,
        ),
        # This fixture does not model the pump's stored configuration - its
        # transport answers everything with filler - so the post-connect
        # read of it can only time out. Opting out keeps connect fast and
        # keeps the reads it would make out of the call counts these tests
        # assert on. Tests that care about readiness use the pump-backed
        # fixture, or drive sync_cache() themselves.
        patch(
            "alpha_hwr.client.AlphaHWRClient._sync_cache_best_effort",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
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
        # Stub the wake burst too. It is transport pacing - three writes
        # and 0.6s of real sleeps - and the filler responses above make
        # every read look unanswered, so the retry path would fire it on
        # each one and spend the suite's time sleeping.
        client.transport.send_wake_burst = AsyncMock()

        yield client

        # Cleanup - be aggressive about cleanup to prevent hangs
        try:
            if hasattr(client, "is_connected") and client.is_connected:
                await client.disconnect()
        except Exception:
            logging.getLogger(__name__).debug(
                "Ignoring error during test client cleanup", exc_info=True
            )

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

    with (
        patch("alpha_hwr.client.BleakClient", MockBleakClient),
        patch(
            "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
            new_callable=AsyncMock,
        ),
    ):
        client = AlphaHWRClient("MOCK")
        await client.connect()
        yield client

        # Cleanup
        if client.is_connected:
            await client.disconnect()

        # Give async tasks time to clean up
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Canned replies, captured from hardware
# ---------------------------------------------------------------------------

#: Real frames an ALPHA HWR sent in answer to each object read, captured
#: 2026-08-04. Keyed by (object, sub). Writes that have to read something
#: first - the temperature range's limits field, the cycle configuration's
#: stored flow - decline to run rather than fabricate it, so a mock that
#: answers everything with the same filler makes them abort. These let a
#: transport-level test answer those reads with what the pump really says.
PUMP_REPLIES: dict[tuple[int, int], bytes] = {
    (86, 6): bytes.fromhex("2412f8e70a0e00012f0100000700001b39678ac34fbc"),
    (86, 7): bytes.fromhex("2412f8e70a0e00012f0100000701001b39678ac3f7dd"),
    (91, 430): bytes.fromhex(
        "2419f8e70a150003f40200000e01420c0000421b999a0f3c020501977e"
    ),
    (91, 421): bytes.fromhex("2411f8e70a0d0003d90100000638844f30050fe9cb"),
    (84, 1): bytes.fromhex(
        "2415f8e70a110000da0100000a02050005010100000000dd89"
    ),
}

#: Bare Class 10 acknowledgement, for anything not in the table above.
GENERIC_ACK = bytes.fromhex("2406e7f80a01000000")


def pump_reply_for(request: bytes) -> bytes:
    """
    Answer a Class 10 object read the way the real pump would.

    Reads are ``[27][len][E7][F8][0A][03][obj][subH][subL][crc][crc]``;
    anything else gets a generic acknowledgement.
    """
    if len(request) >= 9 and request[4] == 0x0A and request[5] == 0x03:
        key = (request[6], (request[7] << 8) | request[8])
        if key in PUMP_REPLIES:
            return PUMP_REPLIES[key]
    return GENERIC_ACK


@pytest.fixture
def answering_transport():
    """
    Build a ``query`` side effect that replies like the real pump.

    Usage::

        mock_client_simple.transport.query = AsyncMock(
            side_effect=answering_transport
        )
    """

    async def _reply(packet: bytes, *_args: object, **_kwargs: object) -> bytes:
        return pump_reply_for(packet)

    return _reply
