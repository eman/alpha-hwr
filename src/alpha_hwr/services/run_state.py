"""
What the pump's run state and schedule mean together.

The two flags are written independently, but the pump's behaviour couples
them, and one of the four combinations cannot do anything at all. Measured
with motor RPM as ground truth:

    the motor runs only when the run state is AUTO **and** the schedule is
    off (so it runs continuously) or a schedule window is currently open.

So a stopped pump with a schedule enabled is dead: every window opens and
closes with the motor at 0 RPM, and nothing ever reports a fault. That is
worth naming rather than leaving for a caller to rediscover - it looks
healthy from every angle except the water.

This module is pure logic: no I/O, no pump, so the rules can be read and
tested on their own.
"""

from __future__ import annotations

from enum import StrEnum


class RunState(StrEnum):
    """The states the run flag and schedule flag can express together."""

    OFF = "off"
    """Stopped, schedule off. The pump is idle and will stay that way."""

    ENGAGED = "engaged"
    """
    Running, schedule off: the pump follows its control mode continuously.

    Whether the motor actually spins is then a question for the mode -
    Temperature and Cycle-Time both idle between their own cycles.
    """

    SCHEDULED = "scheduled"
    """Running, schedule on: the pump runs inside its windows and idles between."""

    STALLED = "stalled"
    """
    Stopped, schedule on. Nothing will ever run.

    The schedule is armed and the pump ignores it, so every window passes
    with the motor idle. Reachable by setting the two flags independently,
    which is why it is worth detecting rather than assuming away.
    """


def run_state(enabled: bool, schedule_enabled: bool) -> RunState:
    """Name the state the two flags put the pump in."""
    if enabled:
        return RunState.SCHEDULED if schedule_enabled else RunState.ENGAGED
    return RunState.STALLED if schedule_enabled else RunState.OFF


def is_stalled(enabled: bool, schedule_enabled: bool) -> bool:
    """True for the combination that can never run."""
    return run_state(enabled, schedule_enabled) is RunState.STALLED


def flags_for(state: RunState) -> tuple[bool, bool]:
    """
    The ``(enabled, schedule_enabled)`` pair that reaches ``state``.

    :attr:`RunState.STALLED` has no entry: it is a state to detect and
    leave, not one to ask for.
    """
    targets = {
        RunState.OFF: (False, False),
        RunState.ENGAGED: (True, False),
        RunState.SCHEDULED: (True, True),
    }
    try:
        return targets[state]
    except KeyError:
        raise ValueError(
            f"{state} is a diagnosis, not a target: it describes a pump that "
            f"cannot run. Ask for 'scheduled' to arm the schedule, or 'off' "
            f"to stop the pump."
        ) from None


def write_order(
    current: tuple[bool, bool], target: RunState
) -> list[tuple[str, bool]]:
    """
    The flag writes that move the pump from ``current`` to ``target``.

    Only the flags that differ are written, and they are ordered so the
    sequence never passes through the stalled combination on its way -
    which it would, transiently, if the schedule went on before the run
    state did.

    Args:
        current: ``(enabled, schedule_enabled)`` as the pump reports them.
        target: The state to reach.

    Returns:
        ``(flag, value)`` pairs, in the order to write them. ``flag`` is
        ``"enabled"`` or ``"schedule_enabled"``. Empty when nothing differs.
    """
    want_enabled, want_schedule = flags_for(target)
    now_enabled, now_schedule = current

    writes: list[tuple[str, bool]] = []
    # Turning the run state on goes first, so arming a schedule never
    # leaves the pump momentarily stalled.
    if want_enabled and want_enabled != now_enabled:
        writes.append(("enabled", want_enabled))
    if want_schedule != now_schedule:
        writes.append(("schedule_enabled", want_schedule))
    if not want_enabled and want_enabled != now_enabled:
        writes.append(("enabled", want_enabled))
    return writes
