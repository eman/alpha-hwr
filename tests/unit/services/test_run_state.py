"""
Tests for the run-state / schedule coupling.

The rule these encode was measured with motor RPM as ground truth: the
motor runs only when the run state is AUTO and the schedule is off or a
window is open. The consequence worth pinning is the fourth combination -
stopped with a schedule armed - which never runs and never complains.
"""

from __future__ import annotations

import pytest

from alpha_hwr.services.run_state import (
    RunState,
    flags_for,
    is_stalled,
    run_state,
    write_order,
)


@pytest.mark.parametrize(
    ("enabled", "schedule", "expected"),
    [
        (False, False, RunState.OFF),
        (True, False, RunState.ENGAGED),
        (True, True, RunState.SCHEDULED),
        (False, True, RunState.STALLED),
    ],
)
def test_the_four_combinations(
    enabled: bool, schedule: bool, expected: RunState
) -> None:
    assert run_state(enabled, schedule) is expected


def test_a_stopped_pump_with_a_schedule_is_the_dead_one() -> None:
    """
    Every window opens with the motor idle and nothing reports a fault, so
    this is the combination worth naming rather than leaving to be
    rediscovered from the water going cold.
    """
    assert is_stalled(enabled=False, schedule_enabled=True)
    assert not is_stalled(enabled=True, schedule_enabled=True)
    assert not is_stalled(enabled=False, schedule_enabled=False)


@pytest.mark.parametrize(
    ("state", "flags"),
    [
        (RunState.OFF, (False, False)),
        (RunState.ENGAGED, (True, False)),
        (RunState.SCHEDULED, (True, True)),
    ],
)
def test_reachable_states_map_to_flags(
    state: RunState, flags: tuple[bool, bool]
) -> None:
    assert flags_for(state) == flags


def test_stalled_is_not_a_thing_you_can_ask_for() -> None:
    """It describes a pump that cannot run; offering it as a target invites
    callers to set it deliberately."""
    with pytest.raises(ValueError, match="diagnosis, not a target"):
        flags_for(RunState.STALLED)


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_only_the_flags_that_differ_are_written() -> None:
    assert write_order((True, True), RunState.SCHEDULED) == []
    assert write_order((True, False), RunState.SCHEDULED) == [
        ("schedule_enabled", True)
    ]


def test_arming_a_schedule_starts_the_pump_first() -> None:
    """
    Writing the schedule flag first would leave the pump stalled in between
    - briefly, but through a window boundary that is a missed run.
    """
    assert write_order((False, False), RunState.SCHEDULED) == [
        ("enabled", True),
        ("schedule_enabled", True),
    ]


def test_stopping_clears_the_schedule_first() -> None:
    """Same reasoning in reverse: never leave the schedule armed over a
    stopped pump, even transiently."""
    assert write_order((True, True), RunState.OFF) == [
        ("schedule_enabled", False),
        ("enabled", False),
    ]


def test_no_ordering_passes_through_the_stalled_state() -> None:
    """Exhaustive over every start and every reachable target."""
    reachable = [RunState.OFF, RunState.ENGAGED, RunState.SCHEDULED]
    for start_enabled in (False, True):
        for start_schedule in (False, True):
            for target in reachable:
                flags = {
                    "enabled": start_enabled,
                    "schedule_enabled": start_schedule,
                }
                for flag, value in write_order(
                    (start_enabled, start_schedule), target
                ):
                    flags[flag] = value
                    assert not is_stalled(
                        flags["enabled"], flags["schedule_enabled"]
                    ), (
                        f"{start_enabled}/{start_schedule} -> {target} "
                        f"passed through stalled after writing {flag}={value}"
                    )
                assert (
                    flags["enabled"],
                    flags["schedule_enabled"],
                ) == flags_for(target)
