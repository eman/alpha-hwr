"""
One time base, because the pump only has one.

Every timestamp this pump stores or reports is **local wall-clock time**.
It has no notion of UTC at all, and that is a property of the device rather
than a convention we chose:

* Its clock is broken-down fields - year, month, day, hour, minute, second
  - not an epoch. ``DateTimeActual`` (type 322) also carries ``day_w``,
  ``hour_format`` and ``dst_status``, and ``dst_status`` on the bench unit
  reads ``SummerTime``. A device tracking whether it is currently in summer
  time is keeping local time; UTC has no summer.
* It applies daylight saving **itself**. ``DaylightSavingTime`` (type 323,
  Object 94 Sub 102) on the bench unit reads enabled, starting the second
  Sunday of March at 02:00, ending the first Sunday of November at 02:00,
  with a 60-minute offset - the US rule. So the pump shifts its own clock
  twice a year.
* **There is no timezone or UTC-offset field anywhere in the GENI profile.**
  Not in the datetime objects, not elsewhere. The pump therefore cannot
  convert between local time and UTC even in principle.

The last point is what settles the 32-bit timestamps in
``ClockProgramSingleEvent`` and in the event log. The pump compares those
against its own clock; since it has no offset to relate the two bases, they
must be in the same base, and its clock's base is local. So a stored epoch
is the local wall clock stamped as though it were UTC - which is exactly
what ``calendar.timegm`` on naive local fields produces, and what a bench
measurement independently found when an event started four seconds from its
intended wall clock.

**Why this matters beyond correctness.** More than one client talks to this
pump - the Grundfos GO app, the ESPHome component, this library - and they
all write the same clock. A client that wrote true UTC would set the pump's
clock wrong by the local offset, and every schedule already stored would
fire at the wrong hour. Two clients disagreeing here is worse than either
being wrong alone, because the pump has no way to say which base a value
arrived in.

The practical rule is short: **express local wall clock, never UTC.** A
naive :class:`~datetime.datetime` is the right type for a pump timestamp,
and attaching a timezone to one invents information the pump does not
carry.

A consequence worth knowing: because the pump shifts its own clock at a DST
transition, a stored event keeps its *wall clock* across the boundary - an
07:00 event stays at 07:00. That is almost certainly the intent, and it is
another thing true-UTC storage would break.
"""

from __future__ import annotations

import calendar
import time
from datetime import datetime

#: Widest value the wire field can carry. ``begin`` and ``end`` are
#: declared ``uint32_t`` in the GENI profile, so the range runs to 2106.
MAX_PUMP_TIME = 0xFFFFFFFF


def to_pump_time(when: datetime) -> int:
    """
    Encode a wall clock the way the pump stores it.

    Takes a naive datetime as local, which is the only reading that makes
    sense for a schedule, and stamps its fields as though they were UTC.

    Raises:
        ValueError: The instant is outside the uint32 range the wire field
            can carry.

    Examples:
        >>> to_pump_time(datetime(2026, 8, 20, 9, 30))
        1787218200
    """
    stamped = calendar.timegm(when.timetuple())
    if not 0 <= stamped <= MAX_PUMP_TIME:
        raise ValueError(
            f"{when} is outside the range the pump can store "
            f"(1970-01-01 to 2106-02-07); it encodes as {stamped}"
        )
    return stamped


def from_pump_time(value: int) -> datetime:
    """
    Decode a stored timestamp back to the wall clock it denotes.

    Naive by design, and the exact inverse of :func:`to_pump_time`. The
    pump stores no offset, so attaching one here would invent information
    - and a UTC-labelled value is worse than a naive one, because
    ``astimezone()`` will then shift it by the local offset and produce a
    time the pump never meant.

    Examples:
        >>> from_pump_time(1787218200)
        datetime.datetime(2026, 8, 20, 9, 30)
        >>> from_pump_time(to_pump_time(datetime(2026, 11, 1, 1, 30)))
        datetime.datetime(2026, 11, 1, 1, 30)
    """
    parts = time.gmtime(value)
    return datetime(*parts[:6])  # noqa: DTZ001 - wall clock, no offset
