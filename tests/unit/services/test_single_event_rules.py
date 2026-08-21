"""
The rules a single-event write has to satisfy before it reaches the wire.

Three of these encode findings rather than preferences, and the comments
say which is which - a rule with a measurement behind it should not be
"simplified" by someone who reads it as taste.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr import pump_time
from alpha_hwr.pump_time import from_pump_time, to_pump_time
from alpha_hwr.services import single_event as se
from alpha_hwr.services.single_event import (
    ACTION_RUN,
    ACTION_STOP,
    SLOT_LIMIT,
    SUB_FIRST_SLOT,
    SingleEventService,
)


@pytest.fixture
def service() -> SingleEventService:
    session = MagicMock()
    session.is_connected.return_value = True
    session.ensure_authenticated.return_value = None
    s = SingleEventService(MagicMock(), session)
    s.slot_count = AsyncMock(return_value=5)  # type: ignore[method-assign]
    s._send_configuration_commit = AsyncMock()  # type: ignore[method-assign]
    return s


class TestTheApduHead:
    def test_it_declares_the_payload_it_carries(
        self, service: SingleEventService
    ) -> None:
        """
        0x93 is SET with 19 payload bytes, and 19 is what follows.

        It was 0xB3 - SET with 51 - borrowed from the schedule layer write,
        whose 53-byte APDU really does carry 51. Every one of the 29
        single-event writes in the capture corpus uses 0x93; the 8 layer
        writes use 0xB3.
        """
        apdu = service.build_apdu(
            0, datetime(2026, 8, 20, 9), datetime(2026, 8, 20, 10)
        )

        assert apdu[1] == 0x93
        assert apdu[1] & 0x3F == len(apdu) - 2
        assert (apdu[1] >> 6) == 0b10  # SET


class TestSlotBounds:
    @pytest.mark.asyncio
    async def test_an_out_of_envelope_slot_is_refused_without_reading(
        self, service: SingleEventService
    ) -> None:
        """
        Slot 100 is sub-id 1000, which is schedule layer 0.

        Checked before the pump is consulted, deliberately: deferring it
        makes an impossible slot on a broken link report "the overview
        could not be read", blaming the link for an argument that could
        never have been right.
        """
        service.slot_count = AsyncMock(side_effect=AssertionError("read!"))  # type: ignore[method-assign]

        assert not await service.write(
            SLOT_LIMIT, datetime(2126, 1, 1), datetime(2126, 1, 2)
        )

    @pytest.mark.asyncio
    async def test_a_slot_this_pump_lacks_is_refused_after_reading(
        self, service: SingleEventService
    ) -> None:
        service.slot_count = AsyncMock(return_value=5)  # type: ignore[method-assign]

        assert not await service.write(
            7, datetime(2126, 1, 1), datetime(2126, 1, 2)
        )
        service.slot_count.assert_awaited()


class TestWindows:
    @pytest.mark.asyncio
    async def test_a_window_that_already_closed_is_refused(
        self, service: SingleEventService
    ) -> None:
        """It would occupy one of five slots and never run."""
        past = datetime.now() - timedelta(days=2)

        assert not await service.write(0, past, past + timedelta(hours=1))

    @pytest.mark.asyncio
    async def test_a_window_already_underway_is_allowed(
        self, service: SingleEventService
    ) -> None:
        """Starting part-way through is legitimate; only the end matters."""
        now = datetime.now()
        service.transport.write = AsyncMock()
        service.confirm = AsyncMock(return_value=True)  # type: ignore[method-assign]

        assert await service.write(
            0, now - timedelta(hours=1), now + timedelta(hours=1)
        )


class TestTimestampEncoding:
    def test_it_round_trips_across_both_dst_transitions(self) -> None:
        """
        No timezone is consulted, so there is no offset to resolve wrongly.

        The ESPHome port had a real bug here, but it is a consequence of
        converting to UTC - which this encoding does not do. It stamps the
        wall-clock fields as though they were UTC and reads them back the
        same way, which is exactly how the pump stores them.

        Anyone "fixing" this by adding a UTC conversion reintroduces that
        bug; this test is here to stop them.
        """
        for base in (datetime(2026, 3, 8), datetime(2026, 11, 1)):
            when = base
            for _ in range(97):  # 24 h at 15-minute steps
                assert from_pump_time(to_pump_time(when)) == when
                when += timedelta(minutes=15)

    def test_a_time_the_pump_cannot_store_is_refused(self) -> None:
        """The wire field is uint32: 1970 to 2106."""
        with pytest.raises(ValueError, match="outside the range"):
            to_pump_time(datetime(1969, 1, 1))

        with pytest.raises(ValueError, match="outside the range"):
            to_pump_time(datetime(2107, 1, 1))

    def test_the_top_of_the_range_is_accepted(self) -> None:
        assert to_pump_time(datetime(2106, 2, 7)) <= pump_time.MAX_PUMP_TIME


class TestConfirm:
    @pytest.mark.asyncio
    async def test_a_stored_action_that_differs_is_not_accepted(
        self, service: SingleEventService
    ) -> None:
        """
        The ACTION byte is half the meaning of a single event.

        0x01 holds the pump off across the window - which is what a
        vacation is - and 0x02 runs it once. A confirm that compared only
        the window and the enabled flag would settle a vacation as written
        while the pump was scheduled to run for a week.
        """
        begin, end = datetime(2126, 1, 1), datetime(2126, 1, 2)
        service.read = AsyncMock(  # type: ignore[method-assign]
            return_value=se.SingleEvent(
                slot=0, enabled=True, action=ACTION_RUN, begin=begin, end=end
            )
        )

        assert not await service.confirm(0, begin, end, ACTION_STOP)
        assert await service.confirm(0, begin, end, ACTION_RUN)


class TestTheSlotCountIsBounded:
    """
    A number off the wire is not a loop bound.

    ``read_all()`` and ``find_free_slot()`` turn ``slot_count()`` straight
    into one Class 10 read per slot, so an overlarge count is minutes of
    link time spent on sub-ids that cannot hold a single event.

    The ceiling is not a judgement about what is reasonable. The sub-id is
    ``900 + slot`` and the weekly schedule's layers begin at 1000, so slot
    100 addresses layer 0 - anything past 99 is a different object however
    the pump counts. Same shape as esphome-alpha-hwr#284, which has two
    bytes behind it and can ask for 65,535 reads.
    """

    @pytest.mark.asyncio
    async def test_the_pump_s_own_count_is_used_when_it_is_sane(
        self, service: SingleEventService
    ) -> None:
        """5 on the bench unit, and nothing here should round that up."""
        service.slot_count = SingleEventService.slot_count.__get__(service)  # type: ignore[method-assign]
        service._read_class10_object = AsyncMock(  # type: ignore[method-assign]
            return_value=bytes([0, 0, 10, 2, 5, 0, 0, 0, 0, 0])
        )

        assert await service.slot_count() == 5

    @pytest.mark.asyncio
    async def test_a_count_past_the_addressable_range_is_clamped(
        self, service: SingleEventService
    ) -> None:
        service.slot_count = SingleEventService.slot_count.__get__(service)  # type: ignore[method-assign]
        service._read_class10_object = AsyncMock(  # type: ignore[method-assign]
            return_value=bytes([0, 0, 10, 2, 255, 0, 0, 0, 0, 0])
        )

        assert await service.slot_count() == SLOT_LIMIT

    @pytest.mark.asyncio
    async def test_the_clamp_bounds_how_many_slots_are_read(
        self, service: SingleEventService
    ) -> None:
        """
        The point of the clamp is the read loop, not the number.

        Without it a pump reporting 255 issues 255 Class 10 reads.
        """
        reads: list[int] = []

        async def read(obj: int, sub: int, *_a: object, **_kw: object):
            reads.append(sub)
            if (obj, sub) == (84, 1):
                return bytes([0, 0, 10, 2, 255, 0, 0, 0, 0, 0])
            return None  # every slot unreadable, so read_all bails

        service.slot_count = SingleEventService.slot_count.__get__(service)  # type: ignore[method-assign]
        service._read_class10_object = AsyncMock(side_effect=read)  # type: ignore[method-assign]

        await service.read_all()

        slot_reads = [s for s in reads if s >= SUB_FIRST_SLOT]
        assert all(s < SUB_FIRST_SLOT + SLOT_LIMIT for s in slot_reads), (
            "a slot read must never reach the schedule layers at "
            f"{SUB_FIRST_SLOT + SLOT_LIMIT}"
        )

    @pytest.mark.asyncio
    async def test_an_unreadable_overview_is_still_none(
        self, service: SingleEventService
    ) -> None:
        """Not zero: 'we do not know' is not 'the pump has no slots'."""
        service.slot_count = SingleEventService.slot_count.__get__(service)  # type: ignore[method-assign]
        service._read_class10_object = AsyncMock(return_value=None)  # type: ignore[method-assign]

        assert await service.slot_count() is None
