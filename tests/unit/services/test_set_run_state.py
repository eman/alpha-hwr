"""
Tests for the coupled run-state write.

It composes two independent flag writes, so the thing worth pinning is
that the result describes the pump rather than whichever leg happened to
run last - and that a partial failure surfaces as one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.client import AlphaHWRClient
from alpha_hwr.constants import ControlMode
from alpha_hwr.models import (
    SetpointInfo,
    WriteCommand,
    WriteResult,
    WriteStatus,
)
from alpha_hwr.services.run_state import RunState


def info(running: bool) -> SetpointInfo:
    return SetpointInfo(
        control_mode=ControlMode.CONSTANT_SPEED,
        operation_mode=0 if running else 1,
        setpoint=1650.0,
        is_remote=False,
        is_running=running,
    )


def result(
    status: WriteStatus = WriteStatus.ACCEPTED, **kw: object
) -> WriteResult:
    return WriteResult(command=WriteCommand.SET_ENABLED, status=status, **kw)  # type: ignore[arg-type]


@pytest.fixture
def client() -> AlphaHWRClient:
    """A client whose pump state is driven by a mutable pair of flags."""
    c = AlphaHWRClient("AA:BB:CC:DD:EE:FF")
    state = {"enabled": False, "schedule": False}

    control = MagicMock()
    schedule = MagicMock()
    writes = MagicMock()

    control.get_mode = AsyncMock(side_effect=lambda: info(state["enabled"]))
    schedule.get_state = AsyncMock(side_effect=lambda: state["schedule"])

    async def set_enabled(value: bool) -> WriteResult:
        state["enabled"] = value
        return result(enabled=value)

    async def submit(command, resource, **args):
        state["schedule"] = args["schedule_enabled"]
        return result(
            WriteStatus.ACCEPTED, schedule_enabled=args["schedule_enabled"]
        )

    control.set_enabled = AsyncMock(side_effect=set_enabled)
    writes.submit = AsyncMock(side_effect=submit)

    c.control, c.schedule, c.writes = control, schedule, writes
    c._state = state  # type: ignore[attr-defined]
    return c


@pytest.mark.asyncio
async def test_both_flags_are_reported_whichever_leg_ran_last(
    client: AlphaHWRClient,
) -> None:
    """
    Each leg populates only the flag it wrote, and the order flips with the
    direction of travel - so reading them off one leg leaves the other None
    even when it was written correctly.
    """
    r = await client.set_run_state(RunState.SCHEDULED)

    assert r.status is WriteStatus.ACCEPTED
    assert r.enabled is True
    assert r.schedule_enabled is True


@pytest.mark.asyncio
async def test_both_flags_reported_when_stopping_too(
    client: AlphaHWRClient,
) -> None:
    """Stopping writes the flags in the opposite order to starting."""
    await client.set_run_state(RunState.SCHEDULED)

    r = await client.set_run_state(RunState.OFF)

    assert r.enabled is False
    assert r.schedule_enabled is False


@pytest.mark.asyncio
async def test_a_no_op_still_reports_the_flags(
    client: AlphaHWRClient,
) -> None:
    await client.set_run_state(RunState.ENGAGED)

    r = await client.set_run_state(RunState.ENGAGED)

    assert r.status is WriteStatus.ACCEPTED
    assert r.detail == "already in that state"
    assert r.enabled is True
    assert r.schedule_enabled is False


@pytest.mark.asyncio
async def test_a_leg_that_did_not_take_surfaces_as_a_failure(
    client: AlphaHWRClient,
) -> None:
    """
    Both legs can report success while the pump ends up somewhere else -
    so the verdict comes from reading the state back, not from the legs.
    """

    async def refuses(value: bool) -> WriteResult:
        return result(enabled=value)  # claims success, changes nothing

    client.control.set_enabled = AsyncMock(side_effect=refuses)  # type: ignore[union-attr]

    r = await client.set_run_state(RunState.SCHEDULED)

    assert r.status is WriteStatus.REJECTED
    assert "not scheduled" in r.detail


@pytest.mark.asyncio
async def test_asking_for_the_dead_state_is_invalid(
    client: AlphaHWRClient,
) -> None:
    r = await client.set_run_state(RunState.STALLED)

    assert r.status is WriteStatus.INVALID
    assert "diagnosis" in r.detail


@pytest.mark.asyncio
async def test_an_unreadable_state_is_not_reported_as_success(
    client: AlphaHWRClient,
) -> None:
    client.control.get_mode = AsyncMock(return_value=None)  # type: ignore[union-attr]

    r = await client.set_run_state(RunState.ENGAGED)

    assert r.status is not WriteStatus.ACCEPTED
