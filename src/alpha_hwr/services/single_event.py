"""
One-off scheduled runs, and vacations.

A single event is a one-time window layered over the weekly schedule:
``Auto`` makes the pump run for it, ``Stop`` holds it off, which is how a
vacation is expressed. Both live in Object 84, Sub 900 upward, one per slot.

Two things about them are easy to get wrong and expensive to discover.

**The timestamps are local Unix time, not UTC.** The wire value is the wall
clock stamped as though it were UTC - ``timegm(local fields)`` - matching
the pump's own RTC, which reports bare wall-clock fields with no offset.
Getting this wrong is invisible to verification: the value round-trips
byte-identically, so the write settles as accepted and a readback agrees
with itself while the event opens hours from where it was meant to. It was
established here by writing an event under this encoding and watching the
motor start four seconds from the intended wall clock.

**The clock program has to be running for any of it to happen.** A stopped
pump ignores single events entirely, and disabling the weekly schedule
disables them too - they are the same program. Both were confirmed by
watching a window open with the motor at 0 RPM.
"""

from __future__ import annotations

import calendar
import logging
import time
from dataclasses import dataclass
from datetime import datetime

from ..exceptions import READ_ERRORS
from .base import BaseService

logger = logging.getLogger(__name__)


#: Object 84 sub-id of the first single-event slot.
SUB_FIRST_SLOT = 900

#: Wire actions. Note this is the opposite sense from the weekly schedule's
#: ``default_action``, where 0x01 means Stop.
ACTION_STOP = 0x01
ACTION_RUN = 0x02

#: Type 220, ``ClockProgramSingleEvent``.
TYPE_SINGLE_EVENT = 0xDC01

#: Bytes of the single-event structure.
STRUCT_LEN = 0x0A


def to_pump_time(when: datetime) -> int:
    """
    Encode a wall clock as the pump stores it.

    The pump keeps local Unix time: the wall-clock fields stamped as though
    they were UTC. A naive datetime is taken as local, which is the only
    reading that makes sense for a schedule.
    """
    return calendar.timegm(when.timetuple())


def from_pump_time(value: int) -> datetime:
    """
    Decode a stored timestamp back to the wall clock it denotes.

    Naive by design, and the inverse of :func:`to_pump_time`: the pump
    stores no offset, so attaching one here would invent information.
    """
    parts = time.gmtime(value)
    return datetime(*parts[:6])  # noqa: DTZ001 - wall clock, no offset


@dataclass(frozen=True)
class SingleEvent:
    """One scheduled one-off window."""

    slot: int
    enabled: bool
    action: int
    begin: datetime
    end: datetime

    @property
    def is_vacation(self) -> bool:
        """True when this event holds the pump off rather than running it."""
        return self.action == ACTION_STOP

    def __str__(self) -> str:
        kind = "off" if self.is_vacation else "run"
        return (
            f"slot {self.slot}: {self.begin:%Y-%m-%d %H:%M} -> "
            f"{self.end:%Y-%m-%d %H:%M} ({kind})"
        )


class SingleEventService(BaseService):
    """
    Reads and writes the pump's one-off schedule entries.

    The number of slots is taken from the schedule overview rather than
    assumed: the pump reports its own capacity, and it is not the 35 that
    the sub-id range would suggest - the unit this was written against
    exposes 5, and reading past them simply goes unanswered.
    """

    async def slot_count(self) -> int | None:
        """
        How many single-event slots this pump has.

        Read from ``ClockProgramOverview``, because it varies by model.
        """
        overview = await self._read_class10_object(84, 1)
        if not overview or len(overview) < 5:
            logger.warning("Could not read the schedule overview")
            return None
        return overview[4]

    async def read(self, slot: int) -> SingleEvent | None:
        """
        Read one slot.

        Returns None if the slot cannot be read - which includes slots past
        the pump's capacity, where it answers with a short error frame
        rather than data.
        """
        data = await self._read_class10_object(84, SUB_FIRST_SLOT + slot)
        if not data or len(data) < 13:
            return None

        return SingleEvent(
            slot=slot,
            enabled=bool(data[3]),
            action=data[4],
            begin=from_pump_time(int.from_bytes(data[5:9], "big")),
            end=from_pump_time(int.from_bytes(data[9:13], "big")),
        )

    async def read_all(self) -> list[SingleEvent] | None:
        """
        Read every slot the pump has.

        All-or-nothing: a partial read is not published, because an unread
        slot looks free, and handing one out would overwrite a live event
        that was simply never seen. Slots that read back empty are a
        legitimate result and not a failure - emptiness says nothing about
        whether the read worked.
        """
        count = await self.slot_count()
        if count is None:
            return None

        events: list[SingleEvent] = []
        for slot in range(count):
            event = await self.read(slot)
            if event is None:
                logger.warning(
                    f"Single-event slot {slot} could not be read; "
                    f"discarding the whole set rather than reporting a "
                    f"partial one as complete"
                )
                return None
            events.append(event)
        return events

    async def find_free_slot(self) -> int | None:
        """
        A slot that can be written without losing anything.

        Prefers a genuinely empty one, and only falls back to a slot whose
        event has already finished. Both are safe to take, but an expired
        event is still a record of something the owner scheduled, so it is
        not overwritten while an untouched slot exists. Without the
        fallback the pool would exhaust and never recover, since the pump
        does not clear events once they pass.

        Reads every slot first. Choosing without looking is how slot 0 gets
        handed out over a live event, since an unread slot looks empty.
        """
        events = await self.read_all()
        if events is None:
            return None

        for event in events:
            if not event.enabled:
                return event.slot

        now = datetime.now()  # noqa: DTZ005 - wall clock, to match the pump
        for event in events:
            if event.end < now:
                logger.info(
                    f"Reusing single-event slot {event.slot}, whose window "
                    f"ended {event.end:%Y-%m-%d %H:%M}"
                )
                return event.slot
        return None

    def build_apdu(
        self,
        slot: int,
        begin: datetime | None,
        end: datetime | None,
        action: int = ACTION_RUN,
        enabled: bool = True,
    ) -> bytes:
        """
        Build the write frame for one slot.

        ``[0A][B3][54][SubH][SubL][00][DC][01][00][00][0A][enabled][action]
        [begin u32 BE][end u32 BE]`` - the object is addressed first as a
        single byte here, then a 16-bit sub-id.
        """
        sub = SUB_FIRST_SLOT + slot
        apdu = bytearray(
            [
                0x0A,  # Class 10
                0xB3,  # OpSpec: long SET
                0x54,  # Object 84
                (sub >> 8) & 0xFF,
                sub & 0xFF,
                0x00,
                (TYPE_SINGLE_EVENT >> 8) & 0xFF,
                TYPE_SINGLE_EVENT & 0xFF,
                0x00,
                0x00,
                STRUCT_LEN,
                0x01 if enabled else 0x00,
                action if enabled else 0x00,
            ]
        )
        apdu.extend(
            to_pump_time(begin).to_bytes(4, "big") if begin else bytes(4)
        )
        apdu.extend(to_pump_time(end).to_bytes(4, "big") if end else bytes(4))
        return bytes(apdu)

    async def write(
        self,
        slot: int,
        begin: datetime,
        end: datetime,
        action: int = ACTION_RUN,
    ) -> bool:
        """
        Write one slot and commit it.

        Args:
            slot: Which slot to use.
            begin: Wall clock the window opens. Naive, and taken as local.
            end: Wall clock it closes.
            action: :data:`ACTION_RUN` for a one-off run,
                :data:`ACTION_STOP` for a vacation.

        Returns:
            True if the frame was sent and committed. Whether the pump
            kept it is a separate question - read it back.
        """
        if end <= begin:
            logger.error(f"A window must end after it starts: {begin} -> {end}")
            return False

        try:
            await self.transport.write(
                self._build_geni_packet(
                    0xF8, 0xE7, self.build_apdu(slot, begin, end, action)
                )
            )
            await self._send_configuration_commit()
        except READ_ERRORS as e:
            logger.error(f"Failed to write single event {slot}: {e}")
            return False

        logger.info(
            f"Wrote single event {slot}: {begin:%Y-%m-%d %H:%M} -> "
            f"{end:%Y-%m-%d %H:%M} "
            f"({'off' if action == ACTION_STOP else 'run'})"
        )
        return True

    async def clear(self, slot: int) -> bool:
        """Empty one slot."""
        try:
            await self.transport.write(
                self._build_geni_packet(
                    0xF8,
                    0xE7,
                    self.build_apdu(slot, None, None, enabled=False),
                )
            )
            await self._send_configuration_commit()
        except READ_ERRORS as e:
            logger.error(f"Failed to clear single event {slot}: {e}")
            return False

        logger.info(f"Cleared single event {slot}")
        return True

    async def set_vacation(self, begin: datetime, end: datetime) -> bool:
        """
        Hold the pump off across a date range.

        A vacation is a ``Stop`` single event: it overrides the weekly
        schedule for its window.
        """
        slot = await self.find_free_slot()
        if slot is None:
            logger.error("No free single-event slot for a vacation")
            return False
        return await self.write(slot, begin, end, action=ACTION_STOP)

    async def clear_vacation(self) -> bool:
        """Clear the first enabled ``Stop`` event."""
        events = await self.read_all()
        if events is None:
            return False
        for event in events:
            if event.enabled and event.is_vacation:
                return await self.clear(event.slot)
        logger.info("No vacation to clear")
        return True
