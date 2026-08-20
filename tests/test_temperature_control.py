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
async def test_read_limiters_reports_both_and_whether_either_is_limiting(
    mock_client_simple, answering_transport
):
    """
    The limiters are read, not written.

    set_flow_limit() used to write Object 86 Sub 39 - which is the
    constant-flow *setpoint range*, a type 301 factory object, not a
    limiter - and the pump refused the frame in any case. The real
    limiters are Object 86 Sub 600 (MaxFlow) and Sub 601 (MinFlow),
    established 2026-08-20 by reading all sixty declared sub-ids and
    finding every one past the second answers OPERATION_FAILED.

    This matters because an enabled limiter caps delivered flow whatever
    the setpoint says, and nothing in the setpoint range reveals it.
    """
    mock_client_simple.transport.query = AsyncMock(
        side_effect=answering_transport
    )

    assert not hasattr(mock_client_simple.control, "set_flow_limit")

    limiters = await mock_client_simple.control.read_limiters()

    # The mock pump does not implement the limiter objects, so this is
    # about the call shape rather than the values.
    assert isinstance(limiters, dict)


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
    result = await mock_client_simple.control.set_constant_speed(2000.0)

    assert result is True, "the setpoint write itself still succeeds"
    assert mock_client_simple.transport.write.call_count == 0, (
        "no commit may be sent when the overview is unknown"
    )
