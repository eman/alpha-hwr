"""
A chain the link cut short is not a result.

Both of these services read a sequence of objects and assemble the answers.
Both had the same hole: a read that fails is *ordinarily* legitimate - an
event log with twelve entries reports the other eight as unreadable, and a
pump that keeps no head trend returns nothing for it - so a link that drops
part-way through produces something shaped exactly like a successful read
of less data.

"Retrieved 5/20 event log entries" is what a five-entry log looks like.
That is the whole problem: once the list is handed back, nothing
distinguishes it from a truncated one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.exceptions import ConnectionError
from alpha_hwr.services.event_log import EventLogService
from alpha_hwr.services.history import HistoryService


@pytest.fixture
def session() -> MagicMock:
    s = MagicMock()
    s.is_connected.return_value = True
    s.ensure_connected.return_value = None
    s.ensure_authenticated.return_value = None
    return s


def _drops_after(session: MagicMock, calls: int) -> AsyncMock:
    """A reader that answers `calls` times, then the link goes."""
    state = {"n": 0}

    async def read(*_args, **_kwargs):
        state["n"] += 1
        if state["n"] > calls:
            session.is_connected.return_value = False
            raise ConnectionError("Pump disconnected from BLE while reading")
        return b"\x00\x00\x10" + bytes(16)

    return AsyncMock(side_effect=read)


class TestEventLog:
    @pytest.mark.asyncio
    async def test_a_drop_part_way_through_is_raised_not_returned(
        self, session: MagicMock
    ) -> None:
        service = EventLogService(MagicMock(), session)
        service._read_class10_object = _drops_after(session, 5)  # type: ignore[method-assign]

        with pytest.raises(ConnectionError):
            await service.get_all_entries()

    @pytest.mark.asyncio
    async def test_an_unreadable_entry_on_a_live_link_is_still_skipped(
        self, session: MagicMock
    ) -> None:
        """
        The ordinary case must keep working.

        A log with fewer than twenty entries reports its empty slots as
        unreadable, so skipping them is right - what must not be skipped is
        a failure that means every later read will fail too.
        """
        service = EventLogService(MagicMock(), session)

        async def read(_obj, subid, *_a, **_kw):
            if subid >= 10205:
                return None
            return b"\x00\x00\x10" + bytes(16)

        service._read_class10_object = AsyncMock(side_effect=read)  # type: ignore[method-assign]

        entries = await service.get_all_entries()
        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_a_drop_with_no_exception_is_still_caught(
        self, session: MagicMock
    ) -> None:
        """
        The link can go without the chain noticing.

        A read already answered when the drop lands returns normally, so
        the loop can run to completion over a link that died half way. The
        session is checked at the end for exactly that.
        """
        service = EventLogService(MagicMock(), session)

        async def read(_obj, subid, *_a, **_kw):
            if subid >= 10210:
                session.is_connected.return_value = False
                return None
            return b"\x00\x00\x10" + bytes(16)

        service._read_class10_object = AsyncMock(side_effect=read)  # type: ignore[method-assign]

        with pytest.raises(ConnectionError, match="10 of 20"):
            await service.get_all_entries()


class TestHistory:
    @pytest.mark.asyncio
    async def test_a_drop_mid_chain_is_raised_not_a_half_built_collection(
        self, session: MagicMock
    ) -> None:
        """
        Three of the four trend series are legitimately None on some pumps,
        so a collection with one series filled in is not obviously wrong.
        """
        service = HistoryService(MagicMock(), session)
        service._read_class10_object = _drops_after(session, 3)  # type: ignore[method-assign]

        with pytest.raises(ConnectionError):
            await service.get_trend_data()

    @pytest.mark.asyncio
    async def test_a_pump_that_answers_nothing_is_not_a_disconnect(
        self, session: MagicMock
    ) -> None:
        """An unreadable object on a live link still degrades to None."""
        service = HistoryService(MagicMock(), session)
        service._read_class10_object = AsyncMock(return_value=None)  # type: ignore[method-assign]

        assert await service.get_trend_data() is None
