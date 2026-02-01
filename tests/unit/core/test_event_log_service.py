"""
Unit tests for EventLogService.
"""

import pytest
import struct
from unittest.mock import AsyncMock, MagicMock
from alpha_hwr.services.event_log import EventLogService
from alpha_hwr.core.transport import Transport
from alpha_hwr.core.session import Session


@pytest.fixture
def mock_transport():
    transport = MagicMock(spec=Transport)
    transport.query = AsyncMock()
    return transport


@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    session.is_connected = MagicMock(return_value=True)
    return session


@pytest.fixture
def event_log_service(mock_transport, mock_session):
    return EventLogService(mock_transport, mock_session)


@pytest.mark.asyncio
async def test_get_metadata(event_log_service, mock_transport):
    """Test reading event log metadata."""
    # Obj 88 Sub 10199
    # Payload: [cycle(2)][avail(2)][max(2)][res(1)] = 7 bytes
    payload = struct.pack(">HHHB", 150, 5, 20, 0)

    # [24][Len]...[0A][03][00][58][27][D7][Payload][CRC]
    # Sub 10199 = 0x27D7, Obj 88 = 0x0058
    response = (
        b"\x24\x11\xe7\xf8\x0a\x03\x00\x58\x27\xd7" + payload + b"\xaa\xbb"
    )

    mock_transport.query.return_value = response

    meta = await event_log_service.get_metadata()

    assert meta is not None
    assert meta.current_cycle == 150
    assert meta.available_entries == 5
    assert meta.max_buffer_size == 20


@pytest.mark.asyncio
async def test_get_entry(event_log_service, mock_transport):
    """Test reading a single event log entry."""
    # Obj 88 Sub 10200
    # Entry: 16 bytes. Cycle at offset 4, Mode at 6, Type at 9, TS at 10-13
    entry_payload = bytearray(16)
    entry_payload[4] = 140  # Cycle
    entry_payload[6] = 0x48  # Mode
    entry_payload[9] = 0x01  # Type
    # Timestamp: 1769860800
    entry_payload[10:14] = struct.pack(">I", 1769860800)

    response = (
        b"\x24\x1a\xe7\xf8\x0a\x03\x00\x58\x27\xd8"
        + entry_payload
        + b"\xaa\xbb"
    )

    mock_transport.query.return_value = response

    entry = await event_log_service.get_entry(0)

    assert entry is not None
    assert entry.cycle_counter == 140
    assert entry.mode_byte == 0x48
    assert entry.event_type_flag == 0x01
    assert entry.timestamp.year == 2026


@pytest.mark.asyncio
async def test_get_all_entries(event_log_service, mock_transport):
    """Test reading all entries loop."""
    # Return 2 valid entries then None
    payload = bytearray(16)
    resp = b"\x24\x1a\xe7\xf8\x0a\x03\x00\x58\x27\xd8" + payload + b"\xaa\xbb"

    # Side effect: return resp for first 2 calls, then None
    # Service calls get_entry(0...19)
    mock_transport.query.side_effect = [resp, resp] + [None] * 18

    entries = await event_log_service.get_all_entries()

    assert len(entries) == 2
    assert mock_transport.query.call_count == 20
