"""
Unit tests for AuthenticationHandler.

Covers extension packet ordering and timing requirements introduced
to fix premature disconnection on BLE firmware V06.00.01 (issue #24),
and the whole-handshake serialization that followed it (issue #31).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from alpha_hwr.core.authentication import AuthenticationHandler


@pytest.fixture
def mock_writer() -> AsyncMock:
    """BLE writer mock that records all write_gatt_char calls."""
    writer = AsyncMock()
    writer.write_gatt_char = AsyncMock()
    return writer


@pytest.fixture
def handler(mock_writer: AsyncMock) -> AuthenticationHandler:
    return AuthenticationHandler(mock_writer)


# ---------------------------------------------------------------------------
# Extension packet ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extension_packets_extend1_before_extend2(
    handler: AuthenticationHandler, mock_writer: AsyncMock
) -> None:
    """EXTEND_1 must be written before EXTEND_2."""
    await handler.send_extension_packets(delay=0)

    calls = mock_writer.write_gatt_char.call_args_list
    assert len(calls) == 2

    first_data = calls[0][0][1]
    second_data = calls[1][0][1]

    assert first_data == AuthenticationHandler.EXTEND_1, (
        "EXTEND_1 must be sent first"
    )
    assert second_data == AuthenticationHandler.EXTEND_2, (
        "EXTEND_2 must be sent second"
    )


@pytest.mark.asyncio
async def test_extension_packets_sleep_between_packets(
    handler: AuthenticationHandler, mock_writer: AsyncMock
) -> None:
    """A sleep must occur between EXTEND_1 and EXTEND_2 when delay > 0."""
    all_calls: list[tuple[str, object]] = []

    async def recording_sleep(t: float) -> None:
        all_calls.append(("sleep", t))

    async def recording_write(uuid: str, data: bytes, **kw: object) -> None:
        all_calls.append(("write", data))

    mock_writer.write_gatt_char.side_effect = recording_write

    with patch("alpha_hwr.core.authentication.asyncio.sleep", recording_sleep):
        await handler.send_extension_packets(delay=0.05)

    kinds = [k for k, _ in all_calls]
    assert kinds == ["write", "sleep", "write"], (
        f"Expected [write, sleep, write] but got {kinds}"
    )
    assert all_calls[0][1] == AuthenticationHandler.EXTEND_1
    assert all_calls[2][1] == AuthenticationHandler.EXTEND_2


@pytest.mark.asyncio
async def test_extension_packets_no_sleep_when_delay_zero(
    handler: AuthenticationHandler, mock_writer: AsyncMock
) -> None:
    """No sleep should be issued when delay=0 (fast_mode / tests)."""
    with patch("alpha_hwr.core.authentication.asyncio.sleep") as mock_sleep:
        await handler.send_extension_packets(delay=0)

    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# authenticate() fast_mode passes delay=0 to send_extension_packets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_fast_mode_skips_extension_sleep(
    handler: AuthenticationHandler,
) -> None:
    """In fast_mode, no asyncio.sleep calls should be made at all."""
    with patch("alpha_hwr.core.authentication.asyncio.sleep") as mock_sleep:
        result = await handler.authenticate(fast_mode=True)

    assert result is True
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_authenticate_normal_mode_sleeps_between_extensions(
    handler: AuthenticationHandler,
) -> None:
    """In normal mode, authenticate() must sleep between extension packets."""
    sleep_calls: list[float] = []

    async def record_sleep(t: float) -> None:
        sleep_calls.append(t)

    with patch("alpha_hwr.core.authentication.asyncio.sleep", record_sleep):
        result = await handler.authenticate(fast_mode=False)

    assert result is True
    # Normal mode paces the handshake: every packet is followed by a
    # non-zero delay, and the sequence ends with the stabilization sleep.
    # The exact inter-packet delay is tuning, so assert the shape, not a
    # specific value (fast_mode skipping sleeps entirely is covered above).
    assert sleep_calls, "Expected pacing sleeps in normal mode"
    assert all(t > 0 for t in sleep_calls), (
        f"Expected only non-zero pacing sleeps, got: {sleep_calls}"
    )
    assert sleep_calls[-1] == 0.5, (
        f"Expected final stabilization sleep of 0.5s, got: {sleep_calls}"
    )


# ---------------------------------------------------------------------------
# Whole-handshake serialization (issue #31)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handshake_writes_are_strictly_sequential(
    handler: AuthenticationHandler, mock_writer: AsyncMock
) -> None:
    """
    No two handshake writes may ever be in flight at once.

    An earlier revision spawned the stage 1/2 bursts as concurrent tasks,
    which let packets reach the pump out of order and made it drop the
    link about a second later.
    """
    in_flight = 0
    max_in_flight = 0

    async def slow_write(uuid: str, data: bytes, **kw: object) -> None:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0)  # yield, so an overlapping write could show up
        in_flight -= 1

    mock_writer.write_gatt_char.side_effect = slow_write

    assert await handler.authenticate(fast_mode=True) is True
    assert max_in_flight == 1, (
        f"Handshake writes overlapped ({max_in_flight} concurrent)"
    )


@pytest.mark.asyncio
async def test_handshake_packet_order(
    handler: AuthenticationHandler, mock_writer: AsyncMock
) -> None:
    """The full 10-packet sequence goes out in the documented order."""
    await handler.authenticate(fast_mode=True)

    sent = [c[0][1] for c in mock_writer.write_gatt_char.call_args_list]
    expected = (
        [AuthenticationHandler.LEGACY_MAGIC] * 3
        + [AuthenticationHandler.CLASS10_UNLOCK] * 5
        + [AuthenticationHandler.EXTEND_1, AuthenticationHandler.EXTEND_2]
    )
    assert sent == expected


@pytest.mark.asyncio
async def test_handshake_holds_the_transaction_lock(
    mock_writer: AsyncMock,
) -> None:
    """
    The lock is held for the whole sequence, not per packet.

    Anything else lets a telemetry query or keep-alive burst land between
    two handshake packets.
    """
    lock = asyncio.Lock()
    handler = AuthenticationHandler(mock_writer, transaction=lock)
    held_during_writes: list[bool] = []

    async def check_lock(uuid: str, data: bytes, **kw: object) -> None:
        held_during_writes.append(lock.locked())

    mock_writer.write_gatt_char.side_effect = check_lock

    assert await handler.authenticate(fast_mode=True) is True
    assert held_during_writes and all(held_during_writes), (
        "Transaction lock was not held for every handshake write"
    )
    assert not lock.locked(), "Transaction lock was not released"


@pytest.mark.asyncio
async def test_handshake_without_transaction_lock_still_works(
    handler: AuthenticationHandler, mock_writer: AsyncMock
) -> None:
    """The lock is optional; a bare BLE writer still authenticates."""
    assert await handler.authenticate(fast_mode=True) is True
    assert mock_writer.write_gatt_char.await_count == 10
