"""
Unit tests for TimeService.
"""

import pytest
import struct
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from alpha_hwr.services.time import TimeService
from alpha_hwr.core.transport import Transport
from alpha_hwr.core.session import Session
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
        b'\x00\x00' + # Status OK
        b'\x07' + # Length 7
        struct.pack('>H', 2026) +
        b'\x01\x1F\x0C\x22\x38' # Jan 31 12:34:56
    )
    
    # Wrap in Class 10 response frame (Obj 94 Sub 101)
    # [24][Len]...[0A][03][00][65][00][5E][Payload][CRC]
    # Sub 101 = 0x0065, Obj 94 = 0x005E
    response = (
        b'\x24\x15\xE7\xF8\x0A\x03\x00\x65\x00\x5E' + 
        clock_payload + 
        b'\xAA\xBB'
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
        b'\xFF\xFF' + # Status Unset
        b'\x07' + 
        struct.pack('>H', 0) +
        b'\x00\x00\x00\x00\x00'
    )
    
    response = (
        b'\x24\x15\xE7\xF8\x0A\x03\x00\x65\x00\x5E' + 
        clock_payload + 
        b'\xAA\xBB'
    )
    
    mock_transport.query.return_value = response
    
    dt = await time_service.get_clock()
    
    # Should return Epoch
    assert dt is not None
    # Compare timestamps to avoid timezone issues
    assert dt.timestamp() == 0.0

@pytest.mark.asyncio
async def test_set_clock_success(time_service, mock_transport):
    """Test setting clock successfully."""
    # get_clock is called to verify success
    # First call to get_clock returns the set time
    
    target_dt = datetime(2026, 2, 1, 10, 0, 0)
    
    # Mock read back response
    clock_payload = (
        b'\x00\x00\x07' +
        struct.pack('>H', 2026) +
        b'\x02\x01\x0A\x00\x00'
    )
    read_response = (
        b'\x24\x15\xE7\xF8\x0A\x03\x00\x65\x00\x5E' + 
        clock_payload + 
        b'\xAA\xBB'
    )
    mock_transport.query.return_value = read_response
    
    success = await time_service.set_clock(target_dt)
    
    assert success is True
    
    # Verify write called with correct packet
    # set_clock uses non-standard format:
    # [27][Len][07][5E][64][70][Year...]
    mock_transport.write.assert_called_once()
    call_args = mock_transport.write.call_args
    packet = call_args[0][0]
    
    # Check [07][5E][64][70] at indices 2-6
    assert packet[2:6] == b'\x07\x5E\x64\x70'
    
    # Verify Year bytes at indices 6-8
    assert packet[6:8] == struct.pack('>H', 2026)
