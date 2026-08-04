import logging

import pytest

from alpha_hwr.constants import OperationMode

# Configure logging to show all messages during tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_active_control")

# Note: mock_client fixture is now provided by conftest.py as mock_client_simple


@pytest.mark.asyncio
async def test_enable_remote_mode(mock_client_simple):
    """Test enabling remote mode."""
    success = await mock_client_simple.control.enable_remote_mode()
    assert success
    # Verify transport was called
    assert (
        mock_client_simple.transport.query.called
        or mock_client_simple.transport.send_with_response.called
    )


@pytest.mark.asyncio
async def test_disable_remote_mode(mock_client_simple):
    """Test disabling remote mode."""
    success = await mock_client_simple.control.disable_remote_mode()
    assert success
    assert (
        mock_client_simple.transport.query.called
        or mock_client_simple.transport.send_with_response.called
    )


@pytest.mark.asyncio
async def test_start_pump(mock_client_simple):
    """Test starting the pump."""
    success = await mock_client_simple.control.start()
    assert success
    # Verify commands were sent (start + configuration commit)
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count >= 2


@pytest.mark.asyncio
async def test_stop_pump(mock_client_simple):
    """Test stopping the pump."""
    success = await mock_client_simple.control.stop()
    assert success
    # Verify commands were sent (stop + configuration commit)
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count >= 2


@pytest.mark.asyncio
async def test_set_constant_flow(mock_client_simple):
    """Test setting constant flow mode and setpoint."""
    flow_value = 2.5
    success = await mock_client_simple.control.set_constant_flow(flow_value)
    assert success
    # Verify commands were sent (mode changes, setpoint writes, commits)
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count >= 2


@pytest.mark.asyncio
async def test_set_constant_pressure(mock_client_simple):
    """Test setting constant pressure mode and setpoint."""
    pressure_value = 1.5  # Valid range: 0.5-10.0 m
    success = await mock_client_simple.control.set_constant_pressure(
        pressure_value
    )
    assert success
    # Verify commands were sent (mode changes, setpoint writes, commits)
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count >= 2


@pytest.mark.asyncio
async def test_set_control_mode(mock_client_simple):
    """Test setting a generic control mode."""
    success = await mock_client_simple.control.set_mode(OperationMode.AUTO)
    assert success
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count >= 1
