"""
Unit tests for DeviceInfoService.
"""

import struct
from unittest.mock import AsyncMock, MagicMock

import pytest
from wire import frame

from alpha_hwr.core.session import Session
from alpha_hwr.core.transport import Transport
from alpha_hwr.services.device_info import DeviceInfoService


@pytest.fixture
def mock_transport():
    transport = MagicMock(spec=Transport)
    transport.send_command = AsyncMock()
    return transport


@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    session.ensure_authenticated = MagicMock()
    return session


@pytest.fixture
def device_info_service(mock_transport, mock_session):
    return DeviceInfoService(mock_transport, mock_session)


@pytest.mark.asyncio
async def test_read_detailed_info(device_info_service, mock_transport):
    """Test reading serial and versions via Class 7 strings."""

    # Requests are [27][Len][E7][F8][0x07][head][string_id], so the ID is
    # at index 6. Replies are built by tests.wire, which computes a real
    # length and CRC and puts the text at offset 6 - the shape the pump
    # actually sends. The fixture this replaced declared a length of 0,
    # used 0x81 as a constant "response opcode", and echoed the string ID
    # in front of the text.
    def mock_query(request, match_func=None, timeout=None):
        string_id = request[6]
        val = ""
        if string_id == 9:
            val = "SERIAL123"
        elif string_id == 50:
            val = "SW1.0"
        elif string_id == 52:
            val = "HW2.0"
        elif string_id == 58:
            val = "BLE3.0"

        return frame(0x07, val.encode() + b"\x00")

    mock_transport.send_command.side_effect = mock_query

    info = await device_info_service.read_detailed()

    assert info is not None
    # The serial arrives whole; nothing is prepended to it.
    assert info.serial_number == "SERIAL123"
    assert info.software_version == "SW1.0"
    assert info.hardware_version == "HW2.0"
    assert info.ble_version == "BLE3.0"


@pytest.mark.asyncio
async def test_read_statistics(device_info_service, mock_transport):
    """Test reading operating statistics."""
    # Obj 93 Sub 1
    # Format: [starts(4)][starts_1h(2)][starts_24h(2)][operating_time(4)]
    # Payload after 3-byte header
    payload = (
        b"\x00\x00\x00"  # Header
        + struct.pack(">I", 500)  # Starts
        + struct.pack(">H", 5)  # 1h
        + struct.pack(">H", 10)  # 24h
        + struct.pack(">I", 36000)  # 10 hours (36000s)
    )

    response = (
        b"\x24\x15\xe7\xf8\x0a\x03\x00\x5d\x00\x01" + payload + b"\xaa\xbb"
    )

    mock_transport.send_command.return_value = response

    stats = await device_info_service.read_statistics()

    assert stats is not None
    assert stats.start_count == 500
    assert stats.operating_hours == 10.0


@pytest.mark.asyncio
async def test_read_alarms(device_info_service, mock_transport):
    """Test reading active alarms."""
    # Obj 88 Sub 0 (Alarms) and Sub 11 (Warnings)
    # Payload is uint16 array

    alarm_resp = (
        b"\x24\x0c\xe7\xf8\x0a\x03\x00\x58\x00\x00"
        + b"\x00\x01\x00\x02"  # Codes 1 and 2
        + b"\xaa\xbb"
    )

    warning_resp = (
        b"\x24\x0a\xe7\xf8\x0a\x03\x00\x58\x00\x0b"
        + b"\x00\x03"  # Code 3
        + b"\xaa\xbb"
    )

    mock_transport.send_command.side_effect = [alarm_resp, warning_resp]

    alarms = await device_info_service.read_alarms()

    assert alarms is not None
    assert 1 in alarms.active_alarms
    assert 2 in alarms.active_alarms
    assert 3 in alarms.active_warnings
    # Codes 1 and 2 are known: "Leakage Current" and "Motor Phase Missing"
    assert alarms.alarm_description == "Leakage Current, Motor Phase Missing"
    # Code 3 is known: "External Alarm"
    assert alarms.warning_description == "External Alarm"


@pytest.mark.asyncio
async def test_read_alarms_unknown_code_fallback(
    device_info_service, mock_transport
):
    """Test that unmapped alarm codes fall back to 'Unknown (<code>)'."""
    # Use a code (e.g. 9999) that is not in ERROR_CODES
    alarm_resp = (
        b"\x24\x0c\xe7\xf8\x0a\x03\x00\x58\x00\x00"
        + b"\x27\x0f"  # Code 9999 (0x270F)
        + b"\xaa\xbb"
    )
    warning_resp = b"\x24\x0a\xe7\xf8\x0a\x03\x00\x58\x00\x0b" + b"\xaa\xbb"

    mock_transport.send_command.side_effect = [alarm_resp, warning_resp]

    alarms = await device_info_service.read_alarms()

    assert alarms is not None
    assert 9999 in alarms.active_alarms
    assert alarms.alarm_description == "Unknown (9999)"
    assert alarms.warning_description is None
