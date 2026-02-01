"""
Unit tests for ControlService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from alpha_hwr.services.control import ControlService
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
    session.ensure_authenticated = MagicMock()
    return session

@pytest.fixture
def control_service(mock_transport, mock_session):
    return ControlService(mock_transport, mock_session)

@pytest.mark.asyncio
async def test_start_success(control_service, mock_transport):
    """Test start command."""
    # query returns matching response (ACK)
    mock_transport.query.return_value = b'\x24\x06\xE7\xF8\x0A\x01' 
    
    success = await control_service.start()
    
    assert success is True
    # Verify packet structure sent
    # Should be Class 10 SET (0x90) to Sub 0x5600 Obj 0x0601
    call_args = mock_transport.query.call_args
    sent_packet = call_args[0][0]
    
    # [27][Len][Dst][Src][Class][OpSpec][SubH][SubL][ObjH][ObjL]...
    assert sent_packet[4] == 0x0A
    assert sent_packet[5] == 0x90
    assert sent_packet[6:8] == b'\x56\x00'
    assert sent_packet[8:10] == b'\x06\x01'

@pytest.mark.asyncio
async def test_stop_success(control_service, mock_transport):
    """Test stop command."""
    mock_transport.query.return_value = b'\x24\x06\xE7\xF8\x0A\x01'
    
    success = await control_service.stop()
    
    assert success is True
    call_args = mock_transport.query.call_args
    sent_packet = call_args[0][0]
    
    # Verify Stop Flag (0x01) in payload
    # Payload starts at index 10
    # [Header 6 bytes][Flag][Mode]
    # Header: 2F 01 00 00 07 00
    assert sent_packet[10+6] == 0x01

@pytest.mark.asyncio
async def test_set_constant_pressure(control_service, mock_transport):
    """Test setting constant pressure."""
    mock_transport.query.return_value = b'\x24\x06\xE7\xF8\x03\x01'
    
    # 1.5m -> 14710 Pa
    success = await control_service.set_constant_pressure(1.5)
    
    assert success is True
    # Verify set mode called first (Class 10)
    # Then set value (Class 3)
    assert mock_transport.query.call_count >= 2

@pytest.mark.asyncio
async def test_get_mode(control_service, mock_transport):
    """Test reading control mode."""
    from alpha_hwr.protocol.codec import encode_float_be
    
    # Mock response for Object 86, Sub 6
    # [Start][Len]...[Class][OpSpec][SubH][SubL][ObjH][ObjL][Payload][CRC]
    # Payload: [00 00 00][Source][OpMode][ControlMode][Setpoint(4)]
    
    setpoint_bytes = encode_float_be(14710.0)
    
    payload = (
        b'\x00\x00\x00' + # Header
        b'\x01' + # Source
        b'\x01' + # OpMode
        b'\x00' + # ControlMode 0 (Const Pressure)
        setpoint_bytes
    )
    
    response = (
        b'\x24\x1A\xE7\xF8\x0A\x03\x00\x56\x00\x06' + 
        payload + 
        b'\xAA\xBB'
    )
    
    mock_transport.query.return_value = response
    
    info = await control_service.get_mode()
    
    assert info is not None
    assert info.control_mode == 0
    assert abs(info.setpoint - 14710.0) < 0.1
