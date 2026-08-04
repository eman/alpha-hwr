"""
Unit tests for TimeService.
"""

import struct
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.core.session import Session
from alpha_hwr.core.transport import Transport
from alpha_hwr.services.time import TimeService

# Use built-in ConnectionError as TimeService uses it
# from alpha_hwr.exceptions import ConnectionError


@pytest.fixture
def mock_transport():
    transport = MagicMock(spec=Transport)
    transport.query = AsyncMock()
    transport.write = AsyncMock()
    return transport


@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    session.ensure_authenticated = MagicMock()
    session.is_connected = MagicMock(return_value=True)
    return session


@pytest.fixture
def time_service(mock_transport, mock_session):
    return TimeService(mock_transport, mock_session)


@pytest.mark.asyncio
async def test_get_clock_success(time_service, mock_transport):
    """Test reading pump clock successfully."""
    # [Start][Len]...[Class][OpSpec][SubH][SubL][ObjH][ObjL][Data...][CRC]
    # Data: [Status(2)][Length(1)][Year(2)][Month][Day][Hour][Minute][Second]

    # 2026-01-31 12:34:56
    clock_payload = (
        b"\x00\x00"  # Status OK
        + b"\x07"  # Length 7
        + struct.pack(">H", 2026)
        + b"\x01\x1f\x0c\x22\x38"  # Jan 31 12:34:56
    )

    # Wrap in Class 10 response frame (Obj 94 Sub 101)
    # [24][Len]...[0A][03][00][65][00][5E][Payload][CRC]
    # Sub 101 = 0x0065, Obj 94 = 0x005E
    response = (
        b"\x24\x15\xe7\xf8\x0a\x03\x00\x65\x00\x5e"
        + clock_payload
        + b"\xaa\xbb"
    )

    mock_transport.query.return_value = response

    dt = await time_service.get_clock()

    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.day == 31
    assert dt.hour == 12
    assert dt.minute == 34
    assert dt.second == 56


@pytest.mark.asyncio
async def test_get_clock_not_connected(time_service, mock_session):
    """Test get_clock raises error when not connected."""
    mock_session.is_connected.return_value = False

    # TimeService uses built-in ConnectionError
    with pytest.raises(ConnectionError, match="Not connected"):
        await time_service.get_clock()


@pytest.mark.asyncio
async def test_get_clock_unset(time_service, mock_transport):
    """Test reading unset/invalid clock."""
    # Year 0, Month 0
    clock_payload = (
        b"\xff\xff"  # Status Unset
        + b"\x07"
        + struct.pack(">H", 0)
        + b"\x00\x00\x00\x00\x00"
    )

    response = (
        b"\x24\x15\xe7\xf8\x0a\x03\x00\x65\x00\x5e"
        + clock_payload
        + b"\xaa\xbb"
    )

    mock_transport.query.return_value = response

    dt = await time_service.get_clock()

    # Should return Epoch
    assert dt is not None
    # Compare timestamps to avoid timezone issues
    assert dt.timestamp() == 0.0


@pytest.mark.asyncio
async def test_set_clock_success(time_service, mock_transport):
    """Test setting clock successfully.

    set_clock uses standard Class 10 SET via build_data_object_set(0x5E00,
    0x6401, data) with Type 322 payload, then verifies by reading back.
    """
    target_dt = datetime(2026, 2, 1, 10, 0, 0)  # noqa: DTZ001  # pump wall clock is naive

    # ACK response for the SET, then read-back for verification
    ack_response = b"\x24\x05\xf8\xe7\x0a\x01\x00\xae\xa2"

    clock_payload = (
        b"\x00\x00\x07" + struct.pack(">H", 2026) + b"\x02\x01\x0a\x00\x00"
    )
    read_response = (
        b"\x24\x15\xe7\xf8\x0a\x03\x00\x65\x00\x5e"
        + clock_payload
        + b"\xaa\xbb"
    )
    mock_transport.query.side_effect = [ack_response, read_response]

    success = await time_service.set_clock(target_dt)

    assert success is True

    # Verify query was called twice (SET + read-back verification)
    assert mock_transport.query.call_count == 2

    # First call is the SET frame built by build_data_object_set
    set_call = mock_transport.query.call_args_list[0]
    packet = set_call[0][0]

    # Frame starts with STX=0x27
    assert packet[0] == 0x27
    # Contains Class 10 (0x0A) at index 4
    assert packet[4] == 0x0A

    # Type 322 header (41 02 00 00 0B 01) in payload
    assert b"\x41\x02\x00\x00\x0b\x01" in packet

    # Year bytes in big-endian
    assert struct.pack(">H", 2026) in packet
