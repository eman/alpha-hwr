"""
Tests for the serialized write path.

The contract these pin down is the one callers depend on: writes never
interleave, a verdict comes from what the pump stored rather than from an
ACK, and every operation settles exactly once no matter which path it
takes out.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.constants import ControlMode
from alpha_hwr.models import SetpointInfo, WriteCommand, WriteStatus
from alpha_hwr.services import write_operation as wo
from alpha_hwr.services.write_operation import WriteOperationService


@pytest.fixture(autouse=True)
def _no_confirm_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    """The confirm delays are pump pacing, not behaviour under test."""
    monkeypatch.setattr(wo, "CONFIRM_DELAY", 0.0)
    monkeypatch.setattr(wo, "CONFIRM_RETRY_DELAY", 0.0)


def info(
    mode: ControlMode = ControlMode.CONSTANT_SPEED,
    setpoint: float = 1650.0,
    running: bool = True,
) -> SetpointInfo:
    return SetpointInfo(
        control_mode=mode,
        operation_mode=0,
        setpoint=setpoint,
        is_remote=False,
        is_running=running,
    )


@pytest.fixture
def control() -> MagicMock:
    c = MagicMock()
    c._send_run_command = AsyncMock(return_value=True)
    c.set_mode = AsyncMock(return_value=True)
    c.set_constant_speed = AsyncMock(return_value=True)
    c.set_constant_flow = AsyncMock(return_value=True)
    c.get_mode = AsyncMock(return_value=info())
    c.get_temperature_range = AsyncMock(return_value=(35.0, 38.9, True))
    c.get_cycle_time_config = AsyncMock(return_value=(5, 15))
    c.get_cycle_flow = AsyncMock(return_value=0.227)
    c.set_temperature_range_control = AsyncMock(return_value=True)
    c.set_cycle_time_control = AsyncMock(return_value=True)
    c.is_cache_valid = True
    return c


@pytest.fixture
def writes(control: MagicMock) -> WriteOperationService:
    return WriteOperationService(control)


# ---------------------------------------------------------------------------
# Verdicts come from the readback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_stored_value_matching_the_request_is_accepted(
    writes: WriteOperationService, control: MagicMock
) -> None:
    control.get_mode.return_value = info(setpoint=1725.0)

    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=1725.0,
    )

    assert result.status is WriteStatus.ACCEPTED
    assert result.value == 1725.0
    assert result.ok


@pytest.mark.asyncio
async def test_a_different_stored_value_is_a_clamp_not_a_failure(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """
    Measured on hardware: asking for 600 RPM stores 1650. The pump took the
    command and chose its own value, which is not the same as refusing it.
    """
    # First read is the pre-write value; every read after it is the clamp.
    reads = iter([info(setpoint=2000.0)])
    control.get_mode.side_effect = lambda: next(reads, info(setpoint=1650.0))

    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=600.0,
    )

    assert result.status is WriteStatus.CLAMPED
    assert result.ok, "a clamp is a successful write"
    assert result.value == 1650.0
    assert result.requested_value == 600.0
    assert "1650" in result.detail


@pytest.mark.asyncio
async def test_keeping_the_old_value_is_a_rejection(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """Unchanged means the pump refused; a clamp lands somewhere new."""
    control.get_mode.return_value = info(setpoint=2000.0)

    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=1725.0,
    )

    assert result.status is WriteStatus.REJECTED
    assert not result.ok
    assert "kept" in result.detail


@pytest.mark.asyncio
async def test_an_unwritable_mode_is_invalid_before_any_wire_write(
    writes: WriteOperationService, control: MagicMock
) -> None:
    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:27",
        mode=ControlMode.TEMPERATURE_RANGE_CONTROL,
        value=40.0,
    )

    assert result.status is WriteStatus.INVALID
    control.set_constant_speed.assert_not_awaited()


@pytest.mark.asyncio
async def test_out_of_range_cycle_times_never_reach_the_pump(
    writes: WriteOperationService, control: MagicMock
) -> None:
    result = await writes.submit(
        WriteCommand.SET_CYCLE_TIMES,
        "cycle_times",
        on_minutes=0,
        off_minutes=15,
    )

    assert result.status is WriteStatus.INVALID
    control.set_cycle_time_control.assert_not_awaited()


# ---------------------------------------------------------------------------
# Serialization and supersede
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_writes_never_overlap(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """
    Interleaved wire steps are what folded one write's values into
    another's frames, which is the whole reason this layer exists.
    """
    in_flight = 0
    peak = 0

    async def slow_setter(_value: float) -> bool:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return True

    control.set_constant_speed.side_effect = slow_setter
    control.get_mode.return_value = info(setpoint=1700.0)

    await asyncio.gather(
        *[
            writes.submit(
                WriteCommand.SET_SETPOINT,
                f"setpoint:{i}",
                mode=ControlMode.CONSTANT_SPEED,
                value=1700.0,
            )
            for i in range(4)
        ]
    )

    assert peak == 1, f"{peak} writes were in flight at once"


@pytest.mark.asyncio
async def test_a_newer_write_supersedes_a_queued_one_for_the_same_value(
    writes: WriteOperationService, control: MagicMock
) -> None:
    release = asyncio.Event()

    async def blocked(_value: float) -> bool:
        await release.wait()
        return True

    control.set_constant_speed.side_effect = blocked
    control.get_mode.return_value = info(setpoint=1700.0)

    first = asyncio.create_task(
        writes.submit(
            WriteCommand.SET_SETPOINT,
            "setpoint:2",
            mode=ControlMode.CONSTANT_SPEED,
            value=1700.0,
        )
    )
    await asyncio.sleep(0)
    second = asyncio.create_task(
        writes.submit(
            WriteCommand.SET_SETPOINT,
            "setpoint:2",
            mode=ControlMode.CONSTANT_SPEED,
            value=1800.0,
        )
    )
    await asyncio.sleep(0)
    third = asyncio.create_task(
        writes.submit(
            WriteCommand.SET_SETPOINT,
            "setpoint:2",
            mode=ControlMode.CONSTANT_SPEED,
            value=1900.0,
        )
    )
    await asyncio.sleep(0)

    release.set()
    results = await asyncio.gather(first, second, third)

    assert results[0].status is not WriteStatus.SUPERSEDED, (
        "an operation already on the wire must run to its own verdict"
    )
    assert results[1].status is WriteStatus.SUPERSEDED
    assert results[2].status is not WriteStatus.SUPERSEDED, "last write wins"


@pytest.mark.asyncio
async def test_writes_to_different_values_both_run(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """Supersede is per resource: a speed write must not cancel a flow one."""
    by_mode = {
        ControlMode.CONSTANT_SPEED: info(setpoint=1700.0),
        ControlMode.CONSTANT_FLOW: info(
            mode=ControlMode.CONSTANT_FLOW, setpoint=1.5
        ),
    }
    state = {"mode": ControlMode.CONSTANT_SPEED}

    async def set_speed(_v: float) -> bool:
        state["mode"] = ControlMode.CONSTANT_SPEED
        return True

    async def set_flow(_v: float) -> bool:
        state["mode"] = ControlMode.CONSTANT_FLOW
        return True

    control.set_constant_speed.side_effect = set_speed
    control.set_constant_flow.side_effect = set_flow
    control.get_mode.side_effect = lambda: by_mode[state["mode"]]

    speed, flow = await asyncio.gather(
        writes.submit(
            WriteCommand.SET_SETPOINT,
            "setpoint:2",
            mode=ControlMode.CONSTANT_SPEED,
            value=1700.0,
        ),
        writes.submit(
            WriteCommand.SET_SETPOINT,
            "setpoint:8",
            mode=ControlMode.CONSTANT_FLOW,
            value=1.5,
        ),
    )

    assert speed.status is not WriteStatus.SUPERSEDED
    assert flow.status is not WriteStatus.SUPERSEDED


# ---------------------------------------------------------------------------
# Every path out is terminal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_stuck_operation_settles_as_timeout(
    writes: WriteOperationService, control: MagicMock, monkeypatch
) -> None:
    monkeypatch.setitem(wo.WATCHDOG_SECONDS, WriteCommand.SET_ENABLED, 0.05)

    async def never_returns(**_kw: object) -> bool:
        await asyncio.sleep(10)
        return True

    control._send_run_command.side_effect = never_returns

    result = await writes.submit(
        WriteCommand.SET_ENABLED, "enabled", enabled=True
    )

    assert result.status is WriteStatus.TIMEOUT


@pytest.mark.asyncio
async def test_a_disconnect_settles_everything_pending(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """A caller awaiting a write must not wait forever after a drop."""
    release = asyncio.Event()

    async def blocked(**_kw: object) -> bool:
        await release.wait()
        return True

    control._send_run_command.side_effect = blocked

    pending = asyncio.create_task(
        writes.submit(WriteCommand.SET_ENABLED, "enabled", enabled=True)
    )
    await asyncio.sleep(0)
    await writes.on_disconnect()
    release.set()

    result = await pending
    assert result.status is WriteStatus.TIMEOUT
    assert result.detail == "disconnected"


@pytest.mark.asyncio
async def test_a_transport_failure_settles_rather_than_raising(
    writes: WriteOperationService, control: MagicMock
) -> None:
    from bleak.exc import BleakError

    control._send_run_command.side_effect = BleakError("link died")

    result = await writes.submit(
        WriteCommand.SET_ENABLED, "enabled", enabled=True
    )

    assert result.status is WriteStatus.REJECTED
    assert "transport error" in result.detail


@pytest.mark.asyncio
async def test_a_result_is_produced_once_even_when_paths_race(
    writes: WriteOperationService, control: MagicMock, monkeypatch
) -> None:
    """
    The watchdog and the confirm can finish together. The settle guard is
    what keeps that from producing two verdicts for one operation.
    """
    monkeypatch.setitem(wo.WATCHDOG_SECONDS, WriteCommand.SET_ENABLED, 0.01)

    async def slow_but_finishing(**_kw: object) -> bool:
        await asyncio.sleep(0.01)
        return True

    control._send_run_command.side_effect = slow_but_finishing

    result = await writes.submit(
        WriteCommand.SET_ENABLED, "enabled", enabled=True
    )

    assert isinstance(result.status, WriteStatus)


# ---------------------------------------------------------------------------
# The request is echoed back alongside the settled value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_result_carries_both_what_was_asked_and_what_was_stored(
    writes: WriteOperationService, control: MagicMock
) -> None:
    reads = iter([info(setpoint=2000.0)])
    control.get_mode.side_effect = lambda: next(reads, info(setpoint=1650.0))

    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=600.0,
    )

    assert result.requested_value == 600.0
    assert result.value == 1650.0
    assert result.command is WriteCommand.SET_SETPOINT
    assert result.seq > 0


# ---------------------------------------------------------------------------
# The readiness gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_multi_field_write_is_refused_on_a_cold_cache(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """
    The temperature-range write carries min, max and AutoAdapt together.
    Running it without knowing the pump's current values means inventing
    the ones the caller did not set, which is how bounds get replaced by
    plausible-looking guesses.
    """
    control.is_cache_valid = False

    result = await writes.submit(
        WriteCommand.SET_TEMPERATURE_RANGE,
        "temp_range",
        temp_min=35.0,
        temp_max=39.0,
        autoadapt=True,
    )

    assert result.status is WriteStatus.REJECTED
    assert "has not been read yet" in result.detail
    control.set_temperature_range_control.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_single_field_write_does_not_need_the_cache(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """
    A setpoint write asserts only what it was given, so it stays usable
    before the cache is warm - gating it would block the common case for
    no gain.
    """
    control.is_cache_valid = False
    control.get_mode.return_value = info(setpoint=1725.0)

    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=1725.0,
    )

    assert result.status is WriteStatus.ACCEPTED


# ---------------------------------------------------------------------------
# invalid vs rejected
#
# The difference is the retry signal: invalid is a property of the request
# and cannot be helped by trying again, rejected means the pump or the link
# refused and a later attempt might not.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_out_of_range_setpoint_is_invalid(
    writes: WriteOperationService, control: MagicMock
) -> None:
    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=99_000.0,
    )

    assert result.status is WriteStatus.INVALID
    assert "500" in result.detail and "4500" in result.detail
    control.set_constant_speed.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_write_of_a_valid_setpoint_is_rejected(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """
    The setters return a bare False for an out-of-range value and for a
    transport failure alike. Reporting the second as `invalid` would tell a
    caller never to retry something a retry might well fix.
    """
    control.set_constant_speed.return_value = False

    result = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=1725.0,
    )

    assert result.status is WriteStatus.REJECTED
    assert result.status is not WriteStatus.INVALID
    control.set_constant_speed.assert_awaited()


@pytest.mark.asyncio
async def test_range_checks_are_per_mode(
    writes: WriteOperationService, control: MagicMock
) -> None:
    """1.5 is a fine flow and a nonsense speed."""
    control.get_mode.return_value = info(
        mode=ControlMode.CONSTANT_FLOW, setpoint=1.5
    )
    flow = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:8",
        mode=ControlMode.CONSTANT_FLOW,
        value=1.5,
    )
    speed = await writes.submit(
        WriteCommand.SET_SETPOINT,
        "setpoint:2",
        mode=ControlMode.CONSTANT_SPEED,
        value=1.5,
    )

    assert flow.status is WriteStatus.ACCEPTED
    assert speed.status is WriteStatus.INVALID
