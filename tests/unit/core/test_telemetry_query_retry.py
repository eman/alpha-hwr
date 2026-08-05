"""
Unit tests for the query retry / wake-burst behaviour in read_once().

A GENI controller that has dozed off answers nothing at all, so an
unanswered register read is retried after a wake burst rather than being
reported as "no data". Covers:

- an unanswered query is retried (with a wake burst between attempts)
- retries stop immediately once the transport reports a disconnect
- the pre-emptive wake burst is sent once per session, not per read
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from alpha_hwr.core.session import Session
from alpha_hwr.core.transport import Transport
from alpha_hwr.services.telemetry import TelemetryService

_PATCH_SLEEP = "alpha_hwr.services.telemetry.asyncio.sleep"

_MAX_ATTEMPTS = 3
_REGISTERS_POLLED = 3  # motor state, flow/pressure, temperature


def _make_service(
    *, response: bytes | None, connected: bool = True
) -> tuple[TelemetryService, MagicMock]:
    """Build a TelemetryService whose every query returns `response`."""
    transport = MagicMock(spec=Transport)
    transport.send_command = AsyncMock(return_value=response)
    transport.send_wake_burst = AsyncMock()
    transport.is_connected = MagicMock(return_value=connected)

    session = MagicMock(spec=Session)
    session.ensure_connected = MagicMock()

    service = TelemetryService(transport, session)
    service._has_motor_state_stream = False
    service._has_flow_stream = False
    return service, transport


@pytest.mark.asyncio
async def test_unanswered_query_is_retried_with_wake_burst() -> None:
    """An unanswered read is retried up to 3 times, waking the pump first."""
    service, transport = _make_service(response=None)

    with patch(_PATCH_SLEEP):
        await service.read_once()

    assert (
        transport.send_command.call_count == _MAX_ATTEMPTS * _REGISTERS_POLLED
    ), (
        f"Expected {_MAX_ATTEMPTS} attempts per register, "
        f"got {transport.send_command.call_count} calls total"
    )
    # One pre-emptive burst for the session plus one before each retry
    # (2 retries per register).
    assert transport.send_wake_burst.call_count == 1 + 2 * _REGISTERS_POLLED


@pytest.mark.asyncio
async def test_retries_stop_when_transport_disconnects() -> None:
    """A disconnect aborts the retry loop instead of burning all attempts."""
    service, transport = _make_service(response=None, connected=False)

    with patch(_PATCH_SLEEP):
        await service.read_once()

    # Motor state is attempted once, the disconnect is noticed, and the
    # guard before flow/pressure ends the read.
    assert transport.send_command.call_count == 1, (
        f"Expected 1 query before bailing out, got {transport.send_command.call_count}"
    )


@pytest.mark.asyncio
async def test_wake_burst_sent_once_per_session() -> None:
    """The pre-read wake burst is not paid again on subsequent reads."""
    service, transport = _make_service(
        response=bytes.fromhex("2707e7f80a0300000000")
    )

    with patch(_PATCH_SLEEP):
        await service.read_once()
        await service.read_once()
        await service.read_once()

    assert transport.send_wake_burst.call_count == 1, (
        "Expected a single wake burst for the session, got "
        f"{transport.send_wake_burst.call_count}"
    )


@pytest.mark.asyncio
async def test_wake_burst_resent_after_disconnect() -> None:
    """A disconnect re-arms the wake burst for the next session."""
    service, transport = _make_service(response=None, connected=False)

    with patch(_PATCH_SLEEP):
        await service.read_once()
        await service.read_once()

    assert transport.send_wake_burst.call_count == 2, (
        "Expected the wake burst to be re-armed after a disconnect, got "
        f"{transport.send_wake_burst.call_count}"
    )


@pytest.mark.asyncio
async def test_failed_wake_burst_does_not_abort_read() -> None:
    """A wake burst that raises must not take down the whole read."""
    service, transport = _make_service(
        response=bytes.fromhex("2707e7f80a0300000000")
    )
    transport.send_wake_burst = AsyncMock(side_effect=BleakError("link down"))

    with patch(_PATCH_SLEEP):
        result = await service.read_once()

    # The read proceeds despite the failed burst...
    assert result is not None
    assert transport.send_command.call_count == _REGISTERS_POLLED
    # ...and the burst stays armed for the next attempt.
    assert service._needs_wake is True


@pytest.mark.asyncio
async def test_wake_burst_holds_transaction_lock() -> None:
    """The burst must not interleave with an in-flight query()."""
    transport = Transport(MagicMock())
    transport.write = AsyncMock()

    async with transport._transaction_lock:
        burst = asyncio.create_task(
            transport.send_wake_burst(repeats=1, packet_delay=0, wake_delay=0)
        )
        await asyncio.sleep(0)
        # The lock is held, so the burst must not have written anything.
        assert transport.write.call_count == 0

    await burst
    assert transport.write.call_count == 1
