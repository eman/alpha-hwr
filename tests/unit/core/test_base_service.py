"""
Unit tests for BaseService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from alpha_hwr.services.base import BaseService
from alpha_hwr.core.transport import Transport
from alpha_hwr.core.session import Session


@pytest.fixture
def mock_transport():
    transport = MagicMock(spec=Transport)
    transport.query = AsyncMock()
    transport.write = AsyncMock()
    return transport


@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    return session


@pytest.fixture
def base_service(mock_transport, mock_session):
    return BaseService(mock_transport, mock_session)


@pytest.mark.asyncio
async def test_read_class10_object_success(base_service, mock_transport):
    """Test successful reading of Class 10 object."""
    # [STX][LEN][DST][SRC][Class][OpSpec][ObjH][ObjL][SubH][SubL][DATA...][CRC_H][CRC_L]
    # Data = b'\x01\x02\x03'
    # Length = 10 (header) + 3 (data) + 2 (crc) - 2 (stx/len?) = 13?
    # Actually payload extraction is response[10:-2]

    # Mock response:
    # 0-3: Header [27, Len, E7, F8]
    # 4: Class 0A
    # 5: OpSpec
    # 6-7: ObjID
    # 8-9: SubID
    # 10-12: Payload (01 02 03)
    # 13-14: CRC
    mock_response = bytes(
        [
            0x27,
            0x0E,
            0xE7,
            0xF8,  # Header
            0x0A,
            0x03,  # Class 10, OpSpec INFO
            0x00,
            0x54,  # ObjID 84
            0x03,
            0xE8,  # SubID 1000
            0x01,
            0x02,
            0x03,  # Data
            0xAA,
            0xBB,  # CRC
        ]
    )

    mock_transport.query.return_value = mock_response

    data = await base_service._read_class10_object(84, 1000)

    assert data == b"\x01\x02\x03"
    mock_transport.query.assert_called_once()


@pytest.mark.asyncio
async def test_read_class10_object_no_response(base_service, mock_transport):
    """Test reading Class 10 object with no response."""
    mock_transport.query.return_value = None

    data = await base_service._read_class10_object(84, 1000)

    assert data is None


@pytest.mark.asyncio
async def test_read_class10_object_short_response(base_service, mock_transport):
    """Test reading Class 10 object with invalid short response."""
    mock_transport.query.return_value = b"\x00\x01"

    data = await base_service._read_class10_object(84, 1000)

    assert data is None


@pytest.mark.asyncio
async def test_read_class7_string_success(base_service, mock_transport):
    """Test successful reading of Class 7 string."""
    # [STX][LEN][DST][SRC][Class][Cmd][ID][...STRING...][CRC_H][CRC_L]
    # String "TEST" = 54 45 53 54
    # Frame start at 0
    # Class at 4 (0x07)
    # Payload starts at 7
    mock_response = bytes(
        [
            0x27,
            0x0B,
            0xE7,
            0xF8,  # Header
            0x07,
            0x01,
            0x01,  # Class 7, Cmd 1, ID 1
            0x54,
            0x45,
            0x53,
            0x54,  # "TEST"
            0xAA,
            0xBB,  # CRC
        ]
    )

    mock_transport.query.return_value = mock_response

    string_val = await base_service._read_class7_string(1)

    assert string_val == "TEST"


@pytest.mark.asyncio
async def test_read_class7_string_null_terminated(base_service, mock_transport):
    """Test reading null-terminated Class 7 string."""
    # "ABC\x00"
    mock_response = bytes(
        [
            0x27,
            0x0A,
            0xE7,
            0xF8,
            0x07,
            0x01,
            0x01,
            0x41,
            0x42,
            0x43,
            0x00,
            0xAA,
            0xBB,
        ]
    )

    mock_transport.query.return_value = mock_response

    string_val = await base_service._read_class7_string(1)

    assert string_val == "ABC"


@pytest.mark.asyncio
async def test_build_geni_packet(base_service):
    """Test packet building helper."""
    # Simple APDU
    apdu = b"\x01\x02\x03"

    # Expected: [27][Len][E7][F8][01][02][03][CRC][CRC]
    # Len = 2 (Service) + 3 (APDU) = 5
    packet = base_service._build_geni_packet(0xF8, 0xE7, apdu)

    assert packet[0] == 0x27
    assert packet[1] == 5
    assert packet[2] == 0xE7
    assert packet[3] == 0xF8
    assert packet[4:7] == b"\x01\x02\x03"
    assert len(packet) == 9  # 4 header + 3 data + 2 crc
