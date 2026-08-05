"""
One serialized path for every write to the pump.

A pump write is rarely one frame. Setting a setpoint means resolving the
run state, asserting the mode, writing the register, committing, and
reading back to see what the pump actually stored. When those steps from
different writes interleave, values from one fold into another's frames -
which is the shape of most of the control bugs this library has had.

So writes queue and run strictly one at a time, each builds its frames from
the arguments it was given rather than from a cache that may have moved
under it, and each ends in exactly one :class:`WriteResult` decided by
reading the pump back. The ACK is not the verdict: the pump commits some
writes only after its response window has closed, and it clamps values it
does not like rather than refusing them, so only a readback can say what
happened.

Every path out is terminal. Validation rejects before any wire write, a
per-command watchdog turns a stuck operation into a timeout, and a
disconnect settles everything pending - so awaiting a write cannot hang.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from ..constants import ControlMode
from ..exceptions import READ_ERRORS
from ..models import WriteCommand, WriteResult, WriteStatus

if TYPE_CHECKING:
    from .control import ControlService
    from .schedule import ScheduleService

logger = logging.getLogger(__name__)


#: How long each command may take before it settles as a timeout. These
#: bound the whole sequence, readbacks included, not a single frame.
WATCHDOG_SECONDS: dict[WriteCommand, float] = {
    WriteCommand.SET_ENABLED: 10.0,
    WriteCommand.SET_MODE: 15.0,
    WriteCommand.SET_SETPOINT: 10.0,
    WriteCommand.SET_TEMPERATURE_RANGE: 15.0,
    WriteCommand.SET_CYCLE_TIMES: 15.0,
    WriteCommand.SET_SCHEDULE_ENABLED: 12.0,
}

#: How long to let the pump apply a write before reading it back, and how
#: many times to re-read if the first look still shows the old value.
CONFIRM_DELAY = 1.2
CONFIRM_RETRY_DELAY = 1.5
CONFIRM_ATTEMPTS = 3

#: How close a stored value has to be to count as the requested one. The
#: pump stores floats it rounds itself, so exact equality is not usable.
EPSILON: dict[str, float] = {
    "rpm": 1.0,
    "m3h": 0.005,
    "meters": 0.01,
    "celsius": 0.1,
}


def _epsilon_for(mode: ControlMode | int) -> float:
    if mode == ControlMode.CONSTANT_SPEED:
        return EPSILON["rpm"]
    if mode == ControlMode.CONSTANT_FLOW:
        return EPSILON["m3h"]
    return EPSILON["meters"]


@dataclass
class _Operation:
    """One submitted write, and the future its caller is waiting on."""

    seq: int
    command: WriteCommand
    resource: str
    args: dict[str, Any]
    future: asyncio.Future[WriteResult]
    started: bool = False
    # What the pump held before the write, so a "kept its old value"
    # rejection can be told apart from a clamp to something else.
    previous: dict[str, Any] = field(default_factory=dict)

    def settle(
        self, status: WriteStatus, detail: str = "", **values: Any
    ) -> None:
        """
        Record the outcome, once.

        The guard is what makes the one-result contract structural rather
        than a thing every code path has to remember: a watchdog racing a
        confirm callback cannot produce two verdicts.
        """
        if self.future.done():
            return

        # Only echo arguments the result actually has a field for. A
        # command whose argument has no matching `requested_*` field is a
        # gap in the result type, not a reason to fail the write it is
        # trying to report on.
        fields = {f.name for f in dataclasses.fields(WriteResult)}
        requested = {}
        for key, value in self.args.items():
            if value is None:
                continue
            name = f"requested_{key}"
            if name in fields:
                requested[name] = value
            else:
                logger.debug(f"WriteResult has no {name} field; not echoing it")
        self.future.set_result(
            WriteResult(
                command=self.command,
                status=status,
                detail=detail,
                seq=self.seq,
                **requested,
                **values,
            )
        )


class WriteOperationService:
    """
    Serializes writes, confirms them, and reports one result each.

    Not constructed directly by callers - the client owns one and the
    service methods submit through it.
    """

    def __init__(
        self,
        control: ControlService,
        schedule: ScheduleService | None = None,
    ) -> None:
        self._control = control
        self._schedule = schedule
        self._queue: deque[_Operation] = deque()
        self._lock = asyncio.Lock()
        self._seq = 0

    # -- submission ------------------------------------------------------

    async def submit(
        self, command: WriteCommand, resource: str, **args: Any
    ) -> WriteResult:
        """
        Queue a write and wait for its settled result.

        A newer write to the same ``resource`` supersedes any still waiting
        to start - last write wins - but never interrupts one already on
        the wire, which would leave the pump half-written.
        """
        self._seq += 1
        loop = asyncio.get_running_loop()
        op = _Operation(
            seq=self._seq,
            command=command,
            resource=resource,
            args=args,
            future=loop.create_future(),
        )

        for queued in self._queue:
            if queued.resource == resource and not queued.started:
                queued.settle(
                    WriteStatus.SUPERSEDED,
                    f"replaced by a newer {command} (seq {op.seq})",
                )

        self._queue.append(op)
        try:
            async with self._lock:
                if op.future.done():  # superseded while it waited
                    return op.future.result()
                op.started = True
                await self._run_guarded(op)
        finally:
            with contextlib.suppress(ValueError):
                self._queue.remove(op)
            op.settle(
                WriteStatus.REJECTED,
                "the operation ended without reaching a verdict",
            )

        return op.future.result()

    async def on_disconnect(self) -> None:
        """
        Settle everything pending after the link drops.

        Must run before the transport tears its queue down, or the
        callbacks these operations are waiting on are discarded and their
        callers wait forever.
        """
        for op in list(self._queue):
            op.settle(WriteStatus.TIMEOUT, "disconnected")

    # -- execution -------------------------------------------------------

    #: Writes that carry fields the caller did not set, and so cannot be
    #: built at all without knowing what the pump currently holds. Running
    #: one on a cold cache is how a schedule gets zeroed or a temperature
    #: bound replaced by a plausible-looking guess.
    _NEEDS_CACHE: ClassVar[frozenset[WriteCommand]] = frozenset(
        {WriteCommand.SET_TEMPERATURE_RANGE, WriteCommand.SET_CYCLE_TIMES}
    )

    async def _run_guarded(self, op: _Operation) -> None:
        if op.command in self._NEEDS_CACHE and not self._control.is_cache_valid:
            op.settle(
                WriteStatus.REJECTED,
                "the pump's stored configuration has not been read yet; "
                "this write carries fields it would otherwise have to "
                "invent (wait for client.is_ready)",
            )
            return

        budget = WATCHDOG_SECONDS.get(op.command, 10.0)
        runner = {
            WriteCommand.SET_ENABLED: self._run_set_enabled,
            WriteCommand.SET_MODE: self._run_set_mode,
            WriteCommand.SET_SETPOINT: self._run_set_setpoint,
            WriteCommand.SET_TEMPERATURE_RANGE: self._run_set_temperature_range,
            WriteCommand.SET_CYCLE_TIMES: self._run_set_cycle_times,
            WriteCommand.SET_SCHEDULE_ENABLED: self._run_set_schedule_enabled,
        }[op.command]

        try:
            await asyncio.wait_for(runner(op), timeout=budget)
        except TimeoutError:
            op.settle(
                WriteStatus.TIMEOUT,
                f"no confirmation within {budget:.0f}s",
            )
        except ValueError as e:
            # Raised by validation that only the wire layer can perform,
            # such as an unmappable control mode.
            op.settle(WriteStatus.INVALID, str(e))
        except ConnectionError as e:
            op.settle(WriteStatus.TIMEOUT, f"disconnected: {e}")
        except READ_ERRORS as e:
            op.settle(WriteStatus.REJECTED, f"transport error: {e}")

    async def _confirm(
        self,
        op: _Operation,
        read: Callable[[], Awaitable[Any]],
        decide: Callable[[Any], bool],
    ) -> Any:
        """
        Read the pump back until it reflects the write, or give up.

        Returns the last value read, or None if it could never be read.
        ``decide`` says whether that value settles the question; a value
        that does not is re-read, because the pump takes a moment to apply
        a write and an immediate look often still shows the old one.
        """
        latest = None
        for attempt in range(CONFIRM_ATTEMPTS):
            await asyncio.sleep(
                CONFIRM_DELAY if attempt == 0 else CONFIRM_RETRY_DELAY
            )
            latest = await read()
            if latest is not None and decide(latest):
                return latest
        return latest

    # -- run state -------------------------------------------------------

    async def _run_set_enabled(self, op: _Operation) -> None:
        wanted = bool(op.args["enabled"])

        acked = await self._control._send_run_command(start=wanted)
        if not acked:
            op.settle(WriteStatus.REJECTED, "the pump did not acknowledge")
            return

        # Class 3 commands produce no notification, so the run state is
        # only knowable by asking.
        info = await self._confirm(
            op,
            self._control.get_mode,
            lambda i: i.is_running == wanted,
        )
        if info is None:
            op.settle(WriteStatus.TIMEOUT, "could not read the run state back")
            return

        op.settle(
            WriteStatus.ACCEPTED
            if info.is_running == wanted
            else WriteStatus.REJECTED,
            ""
            if info.is_running == wanted
            else f"pump still reports {'running' if info.is_running else 'stopped'}",
            enabled=info.is_running,
            mode=info.control_mode,
            value=info.setpoint,
        )

    # -- control mode ----------------------------------------------------

    async def _run_set_mode(self, op: _Operation) -> None:
        wanted = op.args["mode"]
        wanted_value = (
            wanted.value if isinstance(wanted, ControlMode) else wanted
        )

        if not await self._control.set_mode(wanted):
            op.settle(WriteStatus.REJECTED, "the pump did not acknowledge")
            return

        info = await self._confirm(
            op,
            self._control.get_mode,
            lambda i: int(i.control_mode) == wanted_value,
        )
        if info is None:
            op.settle(WriteStatus.TIMEOUT, "could not read the mode back")
            return

        applied = int(info.control_mode) == wanted_value
        op.settle(
            WriteStatus.ACCEPTED if applied else WriteStatus.REJECTED,
            "" if applied else f"pump still reports {info.control_mode!r}",
            mode=info.control_mode,
            value=info.setpoint,
            enabled=info.is_running,
        )

    # -- setpoints -------------------------------------------------------

    #: Which setter writes which mode's setpoint, and the range that
    #: setter accepts. The range is repeated here deliberately: the setters
    #: return a bare False for an out-of-range value *and* for a transport
    #: failure, and those are opposite answers to "should this be retried".
    #: Checking here lets an out-of-range request settle INVALID before
    #: anything reaches the wire, leaving a False from the setter to mean
    #: what it should - the pump or the link refused.
    _SETTERS: ClassVar[dict[ControlMode, tuple[str, float, float, str]]] = {
        ControlMode.CONSTANT_PRESSURE: (
            "set_constant_pressure",
            0.5,
            10.0,
            "m",
        ),
        ControlMode.PROPORTIONAL_PRESSURE: (
            "set_proportional_pressure",
            0.5,
            10.0,
            "m",
        ),
        ControlMode.CONSTANT_SPEED: (
            "set_constant_speed",
            500.0,
            4500.0,
            "RPM",
        ),
        ControlMode.CONSTANT_FLOW: ("set_constant_flow", 0.1, 10.0, "m3/h"),
    }

    async def _run_set_setpoint(self, op: _Operation) -> None:
        mode = op.args["mode"]
        value = float(op.args["value"])

        spec = self._SETTERS.get(mode)
        if spec is None:
            op.settle(
                WriteStatus.INVALID,
                f"{mode!r} has no scalar setpoint to write",
            )
            return
        setter_name, low, high, unit = spec

        if not low <= value <= high:
            op.settle(
                WriteStatus.INVALID,
                f"{value:g} {unit} is outside the {low:g}-{high:g} {unit} "
                f"this mode accepts",
                mode=mode,
            )
            return

        # What the pump held before, so "it kept its old value" can be told
        # apart from "it clamped to something else".
        before = await self._control.get_mode()
        op.previous["value"] = (
            before.setpoint
            if before is not None and int(before.control_mode) == int(mode)
            else None
        )

        # The request is known good by here, so a False can only mean the
        # write did not get through - which a caller may reasonably retry.
        if not await getattr(self._control, setter_name)(value):
            op.settle(
                WriteStatus.REJECTED,
                "the setpoint write was not acknowledged",
                mode=mode,
            )
            return

        eps = _epsilon_for(mode)
        previous = op.previous.get("value")

        def applied(i: Any) -> bool:
            """
            Has the pump finished with this write?

            Either it stored what was asked, or it stored something else -
            a clamp, which is just as final an answer. Only a reading that
            still shows the old value means it has not got there yet, and
            that is the one worth waiting on.
            """
            if int(i.control_mode) != int(mode) or i.setpoint is None:
                return False
            if abs(i.setpoint - value) <= eps:
                return True
            return previous is not None and abs(i.setpoint - previous) > eps

        info = await self._confirm(op, self._control.get_mode, applied)
        if info is None or info.setpoint is None:
            op.settle(WriteStatus.TIMEOUT, "could not read the setpoint back")
            return

        stored = info.setpoint
        if abs(stored - value) <= eps:
            status, detail = WriteStatus.ACCEPTED, ""
        elif previous is not None and abs(stored - previous) <= eps:
            status, detail = WriteStatus.REJECTED, f"pump kept {stored:g}"
        else:
            status, detail = WriteStatus.CLAMPED, f"pump stored {stored:g}"

        op.settle(
            status,
            detail,
            mode=info.control_mode,
            value=stored,
            enabled=info.is_running,
        )

    # -- temperature range -----------------------------------------------

    async def _run_set_temperature_range(self, op: _Operation) -> None:
        lo = float(op.args["temp_min"])
        hi = float(op.args["temp_max"])
        autoadapt = op.args.get("autoadapt")

        low = self._control.TEMP_RANGE_MIN_C
        high = self._control.TEMP_RANGE_MAX_C
        if not low <= lo <= high or not low <= hi <= high or lo >= hi:
            op.settle(
                WriteStatus.INVALID,
                f"{lo}-{hi} C is not a valid range "
                f"({low:g}-{high:g}, min below max)",
            )
            return

        if not await self._control.set_temperature_range_control(
            lo, hi, autoadapt=autoadapt
        ):
            op.settle(
                WriteStatus.REJECTED,
                "the write was not acknowledged, or a value it had to "
                "preserve could not be read",
            )
            return

        eps = EPSILON["celsius"]
        stored = await self._confirm(
            op,
            self._control.get_temperature_range,
            lambda r: abs(r[0] - lo) <= eps and abs(r[1] - hi) <= eps,
        )
        if stored is None:
            op.settle(WriteStatus.TIMEOUT, "could not read the range back")
            return

        got_lo, got_hi, got_aa = stored
        matched = abs(got_lo - lo) <= eps and abs(got_hi - hi) <= eps
        op.settle(
            WriteStatus.ACCEPTED if matched else WriteStatus.CLAMPED,
            "" if matched else f"pump stored {got_lo:g}-{got_hi:g}",
            temp_min=got_lo,
            temp_max=got_hi,
            autoadapt=got_aa,
        )

    # -- cycle times -----------------------------------------------------

    async def _run_set_cycle_times(self, op: _Operation) -> None:
        on = int(op.args["on_minutes"])
        off = int(op.args["off_minutes"])

        if not 1 <= on <= 60 or not 1 <= off <= 60:
            op.settle(
                WriteStatus.INVALID,
                f"{on}/{off} minutes is outside the 1-60 the pump accepts",
            )
            return

        if not await self._control.set_cycle_time_control(on, off):
            op.settle(
                WriteStatus.REJECTED,
                "the write was not acknowledged, or the stored flow "
                "setpoint could not be read to preserve it",
            )
            return

        stored = await self._confirm(
            op,
            self._control.get_cycle_time_config,
            lambda c: c == (on, off),
        )
        if stored is None:
            op.settle(WriteStatus.TIMEOUT, "could not read the periods back")
            return

        got_on, got_off = stored
        matched = (got_on, got_off) == (on, off)
        op.settle(
            WriteStatus.ACCEPTED if matched else WriteStatus.CLAMPED,
            "" if matched else f"pump stored {got_on}/{got_off}",
            on_minutes=got_on,
            off_minutes=got_off,
            flow=await self._control.get_cycle_flow(),
        )

    # -- schedule --------------------------------------------------------

    async def _run_set_schedule_enabled(self, op: _Operation) -> None:
        if self._schedule is None:
            op.settle(WriteStatus.INVALID, "no schedule service is available")
            return

        wanted = bool(op.args["schedule_enabled"])
        if wanted:
            await self._schedule.enable()
        else:
            await self._schedule.disable()

        state = await self._confirm(
            op,
            self._schedule.get_state,
            lambda s: s == wanted,
        )
        if state is None:
            op.settle(WriteStatus.TIMEOUT, "could not read the schedule back")
            return

        op.settle(
            WriteStatus.ACCEPTED if state == wanted else WriteStatus.REJECTED,
            "" if state == wanted else f"schedule still reports {state}",
            schedule_enabled=state,
        )
