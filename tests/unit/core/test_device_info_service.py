"""
Unit tests for DeviceInfoService.
"""

import pytest
import struct
from unittest.mock import AsyncMock, MagicMock, patch
from alpha_hwr.services.device_info import DeviceInfoService
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
    session.ensure_authenticated = MagicMock()
    return session

@pytest.fixture
def device_info_service(mock_transport, mock_session):
    return DeviceInfoService(mock_transport, mock_session)

@pytest.mark.asyncio
async def test_read_detailed_info(device_info_service, mock_transport):
    """Test reading serial and versions via Class 7 strings."""
    # Side effect for multiple string reads (ID 9, 50, 52, 58)
    # APDU: [0x07, 0x01, string_id]
    # Header: [27, Len, E7, F8]
    # string_id is at index 6
    def mock_query(frame, match_func=None, timeout=None):
        string_id = frame[6]
        val = ""
        if string_id == 9: val = "SERIAL123"
        elif string_id == 50: val = "SW1.0"
        elif string_id == 52: val = "HW2.0"
        elif string_id == 58: val = "BLE3.0"
        
        # Response: [24][Len][Dst][Src][Class][Cmd][ID][Data][CRC]
        resp = bytes([0x24, 0x00, 0xE7, 0xF8, 0x07, 0x81, string_id]) + val.encode() + b'\x00\x00\x00'
        return resp

    mock_transport.query.side_effect = mock_query
    
    info = await device_info_service.read_detailed()
    
    assert info is not None
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
        b'\x00\x00\x00' + # Header
        struct.pack('>I', 500) + # Starts
        struct.pack('>H', 5) + # 1h
        struct.pack('>H', 10) + # 24h
        struct.pack('>I', 36000) # 10 hours (36000s)
    )
    
    response = (
        b'\x24\x15\xE7\xF8\x0A\x03\x00\x5D\x00\x01' + 
        payload + 
        b'\xAA\xBB'
    )
    
    mock_transport.query.return_value = response
    
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
        b'\x24\x0C\xE7\xF8\x0A\x03\x00\x58\x00\x00' + 
        b'\x00\x01\x00\x02' + # Codes 1 and 2
        b'\xAA\xBB'
    )
    
    warning_resp = (
        b'\x24\x0A\xE7\xF8\x0A\x03\x00\x58\x00\x0B' + 
        b'\x00\x03' + # Code 3
        b'\xAA\xBB'
    )
    
    mock_transport.query.side_effect = [alarm_resp, warning_resp]
    
    alarms = await device_info_service.read_alarms()
    
    assert alarms is not None
    assert 1 in alarms.active_alarms
    assert 2 in alarms.active_alarms
    assert 3 in alarms.active_warnings
