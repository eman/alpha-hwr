"""
Unit tests for ControlService.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.core.session import Session
from alpha_hwr.core.transport import Transport
from alpha_hwr.services.control import ControlService


@pytest.fixture
def mock_transport():
    transport = MagicMock(spec=Transport)
    transport.send_command = AsyncMock()
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
async def test_start_uses_the_class3_run_command(
    control_service, mock_transport
):
    """
    Starting the pump changes the run state and nothing else.

    It used to go through the fused control object, which carries a mode
    and a setpoint in the same frame - so every start also asserted both.
    """
    mock_transport.send_command.return_value = b"\x24\x02\xe7\xf8\x03\x00"

    success = await control_service.start()

    assert success is True
    sent_packet = mock_transport.send_command.call_args[0][0]

    # [27][Len][Svc][Src][Class 3][SET][cmd][CRC][CRC]
    assert sent_packet[4] == 0x03, "class 3"
    assert sent_packet[5] == 0x81, "SET, not INFO"
    assert sent_packet[6] == 0x06, "START"
    assert len(sent_packet) == 9, "no room for a mode or a setpoint"


@pytest.mark.asyncio
async def test_stop_uses_the_class3_run_command(
    control_service, mock_transport
):
    mock_transport.send_command.return_value = b"\x24\x02\xe7\xf8\x03\x00"

    success = await control_service.stop()

    assert success is True
    sent_packet = mock_transport.send_command.call_args[0][0]

    assert sent_packet[4] == 0x03
    assert sent_packet[5] == 0x81
    assert sent_packet[6] == 0x05, "STOP"
    assert len(sent_packet) == 9


@pytest.mark.asyncio
async def test_run_command_is_matched_only_on_its_own_class(
    control_service, mock_transport
):
    """A Class 10 notification must not be read as the start ack."""
    mock_transport.send_command.return_value = b"\x24\x02\xe7\xf8\x03\x00"

    await control_service.start()

    command = mock_transport.send_command.call_args[0][1]
    assert command.expect_class == 0x03


@pytest.mark.asyncio
async def test_set_constant_pressure(control_service, mock_transport):
    """Test setting constant pressure."""
    mock_transport.send_command.return_value = b"\x24\x06\xe7\xf8\x0a\x01"

    # 1.5m -> ~14710 Pa
    success = await control_service.set_constant_pressure(1.5)

    assert success is True

    # The fused control request is a Class 10 SET, and a Class 10 SET is
    # never acknowledged - so it goes out through transport.write() rather
    # than through send_command(), which would otherwise sit waiting a full
    # second for a frame the pump does not send.
    from alpha_hwr.core.transport import is_class10_set

    sent = [c[0][0] for c in mock_transport.write.call_args_list]
    sets = [f for f in sent if is_class10_set(f)]
    assert sets, "the control request should have been written"

    # Check conversion
    from alpha_hwr.protocol.codec import decode_float_be

    # Setpoint is at offset 10 (APDU) + 8 (Header) = 18
    actual_pa = decode_float_be(sets[0], 18)
    assert actual_pa is not None
    expected_pa = 1.5 * 9806.65
    assert abs(actual_pa - expected_pa) < 1.0


@pytest.mark.asyncio
async def test_get_mode(control_service, mock_transport):
    """Test reading control mode."""
    from alpha_hwr.protocol.codec import encode_float_be

    # Mock response for Object 86, Sub 6
    # [Start][Len]...[Class][OpSpec][SubH][SubL][ObjH][ObjL][Payload][CRC]
    # Payload: [00 00 00][Source][OpMode][ControlMode][Setpoint(4)]

    setpoint_bytes = encode_float_be(14710.0)

    payload = (
        b"\x00\x00\x00"  # Header
        + b"\x01"  # Source
        + b"\x01"  # OpMode
        + b"\x00"  # ControlMode 0 (Const Pressure)
        + setpoint_bytes
    )

    response = (
        b"\x24\x1a\xe7\xf8\x0a\x03\x00\x56\x00\x06" + payload + b"\xaa\xbb"
    )

    mock_transport.send_command.return_value = response

    info = await control_service.get_mode()

    assert info is not None
    assert info.control_mode == 0
    assert abs(info.setpoint - 1.5) < 0.1
