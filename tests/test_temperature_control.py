"""
Tests for Temperature Range Control (Mode 27).
"""

from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError


@pytest.mark.asyncio
async def test_set_temperature_range_control_success(mock_client_simple):
    """Test successful temperature range control setting."""
    result = await mock_client_simple.control.set_temperature_range_control(
        35.0, 39.0, autoadapt=True
    )

    assert result is True
    # Verify transport calls (mode switch + setpoint write + config commit)
    assert mock_client_simple.transport.query.call_count >= 1
    assert mock_client_simple.transport.write.call_count >= 1


@pytest.mark.asyncio
async def test_set_temperature_range_control_no_autoadapt(mock_client_simple):
    """Test successful temperature range control setting without autoadapt."""
    result = await mock_client_simple.control.set_temperature_range_control(
        35.0, 39.0, autoadapt=False
    )

    assert result is True
    assert mock_client_simple.transport.query.call_count >= 1


@pytest.mark.asyncio
async def test_set_temperature_range_control_failure(mock_client_simple):
    """Test temperature range control setting failure."""
    # Mock transport failure
    mock_client_simple.transport.query = AsyncMock(
        side_effect=BleakError("Transport error")
    )

    result = await mock_client_simple.control.set_temperature_range_control(
        35.0, 39.0
    )
    assert result is False


@pytest.mark.asyncio
async def test_set_flow_limit_success(mock_client_simple):
    """Test successful flow limit setting."""
    result = await mock_client_simple.control.set_flow_limit(1.5)

    assert result is True
    # Verify transport calls (setpoint write + config commit)
    assert mock_client_simple.transport.query.call_count >= 1
    assert mock_client_simple.transport.write.call_count >= 1
