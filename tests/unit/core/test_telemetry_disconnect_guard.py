"""
Unit tests for the disconnection guards in TelemetryService.read_once().

Verifies that read_once() returns partial telemetry immediately (without
attempting further queries) when the transport reports a disconnect between
the motor-state query and the flow/pressure or temperature queries.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alpha_hwr.core.session import Session
from alpha_hwr.core.transport import Transport
from alpha_hwr.models import TelemetryData
from alpha_hwr.services.telemetry import TelemetryService

_PATCH_SLEEP = "alpha_hwr.services.telemetry.asyncio.sleep"


def _make_service(
    *,
    connected_after_motor_state: bool = True,
    connected_after_flow_pressure: bool = True,
) -> tuple[TelemetryService, MagicMock]:
    """Build a TelemetryService with a scripted transport mock.

    Args:
        connected_after_motor_state: Value returned by is_connected() before
            the flow/pressure query.
        connected_after_flow_pressure: Value returned by is_connected() before
            the temperature query.

    Returns:
        (service, transport_mock) tuple.
    """
    transport = MagicMock(spec=Transport)
    transport.query = AsyncMock(return_value=None)
    # Return connected=True for the initial ensure_connected check, then
    # the scripted values for the two guards.
    transport.is_connected = MagicMock(
        side_effect=[
            connected_after_motor_state,
            connected_after_flow_pressure,
        ]
    )

    session = MagicMock(spec=Session)
    session.ensure_connected = MagicMock()

    service = TelemetryService(transport, session)
    # Disable stream flags so the polling branches are exercised
    service._has_motor_state_stream = False
    service._has_flow_stream = False
    return service, transport


# ---------------------------------------------------------------------------
# Disconnect after motor-state query (before flow/pressure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_after_motor_state_skips_flow_query() -> None:
    """If disconnected after motor state, flow/pressure query must not run."""
    service, transport = _make_service(connected_after_motor_state=False)

    with patch(_PATCH_SLEEP):
        result = await service.read_once()

    assert isinstance(result, TelemetryData)
    # query() is called once (motor state) then the guard returns early;
    # it must NOT be called for flow/pressure or temperature
    assert transport.query.call_count == 1, (
        f"Expected 1 query (motor state only), got {transport.query.call_count}"
    )


@pytest.mark.asyncio
async def test_disconnect_after_motor_state_returns_partial_telemetry() -> None:
    """Partial telemetry (with None fields) is returned rather than raising."""
    service, _ = _make_service(connected_after_motor_state=False)

    with patch(_PATCH_SLEEP):
        result = await service.read_once()

    # flow_m3h and head_m must still be None (not populated) but the call
    # must succeed without raising.
    assert result.flow_m3h is None
    assert result.head_m is None


# ---------------------------------------------------------------------------
# Disconnect after flow/pressure query (before temperature)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_before_temperature_skips_temp_query() -> None:
    """If disconnected before temperature query, that query must not run."""
    service, transport = _make_service(
        connected_after_motor_state=True,
        connected_after_flow_pressure=False,
    )

    with patch(_PATCH_SLEEP):
        result = await service.read_once()

    assert isinstance(result, TelemetryData)
    # motor-state + flow/pressure = 2 calls; temperature must be skipped
    assert transport.query.call_count == 2, (
        f"Expected 2 query calls, got {transport.query.call_count}"
    )


@pytest.mark.asyncio
async def test_disconnect_before_temperature_returns_partial_telemetry() -> (
    None
):
    """Returns without raising when disconnected before temperature query."""
    service, _ = _make_service(
        connected_after_motor_state=True,
        connected_after_flow_pressure=False,
    )

    with patch(_PATCH_SLEEP):
        result = await service.read_once()

    assert result.media_temperature_c is None


# ---------------------------------------------------------------------------
# Happy path: all queries succeed when transport stays connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_connected_runs_all_three_queries() -> None:
    """When connected throughout, all three register queries execute."""
    transport = MagicMock(spec=Transport)
    transport.query = AsyncMock(return_value=None)
    transport.is_connected = MagicMock(return_value=True)

    session = MagicMock(spec=Session)
    session.ensure_connected = MagicMock()

    service = TelemetryService(transport, session)
    service._has_motor_state_stream = False
    service._has_flow_stream = False

    with patch(_PATCH_SLEEP):
        await service.read_once()

    assert transport.query.call_count == 3, (
        f"Expected 3 query calls, got {transport.query.call_count}"
    )
