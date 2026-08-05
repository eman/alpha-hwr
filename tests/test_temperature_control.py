"""
Tests for Temperature Range Control (Mode 27).
"""

from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError


@pytest.mark.asyncio
async def test_set_temperature_range_control_success(
    mock_client_simple, answering_transport
):
    """Test successful temperature range control setting."""
    # The write echoes the pump's stored on/off-time limits back, so it
    # needs a transport that actually answers the read for them.
    mock_client_simple.transport.query = AsyncMock(
        side_effect=answering_transport
    )

    result = await mock_client_simple.control.set_temperature_range_control(
        35.0, 39.0, autoadapt=True
    )

    assert result is True
    # Verify transport calls (mode switch + setpoint write + config commit)
    assert mock_client_simple.transport.query.call_count >= 1
    assert mock_client_simple.transport.write.call_count >= 1


@pytest.mark.asyncio
async def test_set_temperature_range_control_no_autoadapt(
    mock_client_simple, answering_transport
):
    """Test successful temperature range control setting without autoadapt."""
    mock_client_simple.transport.query = AsyncMock(
        side_effect=answering_transport
    )

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
async def test_set_flow_limit_success(mock_client_simple, answering_transport):
    """Test successful flow limit setting."""
    # The configuration commit carries the whole schedule overview, so it
    # reads the pump's copy first and skips the commit entirely if it
    # cannot - writing a fabricated overview would switch the schedule off.
    mock_client_simple.transport.query = AsyncMock(
        side_effect=answering_transport
    )

    result = await mock_client_simple.control.set_flow_limit(1.5)

    assert result is True
    assert mock_client_simple.transport.query.call_count >= 1
    assert mock_client_simple.transport.write.call_count >= 1, (
        "the commit should have been sent once the overview was readable"
    )


@pytest.mark.asyncio
async def test_commit_is_skipped_when_the_overview_cannot_be_read(
    mock_client_simple,
):
    """
    An unreadable overview means no commit, not a fabricated one.

    The commit writes the entire ClockProgramOverview, so sending a
    constant in place of the pump's own copy overwrites the schedule's
    enabled flag. Skipping a flush is recoverable; that is not.
    """
    result = await mock_client_simple.control.set_flow_limit(1.5)

    assert result is True, "the setpoint write itself still succeeds"
    assert mock_client_simple.transport.write.call_count == 0, (
        "no commit may be sent when the overview is unknown"
    )
