"""
Unit tests for Transport's BLE write path.

Covers MTU chunking and send pacing. An earlier revision split every
frame into exactly two chunks, so anything over 40 bytes was silently
truncated - including the 59-byte schedule-layer write, whose second
chunk still exceeded the 20-byte MTU.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from wire import CAPTURED

from alpha_hwr.constants import GENI_CHAR_UUID
from alpha_hwr.core import transport as tmod
from alpha_hwr.core.transport import (
    BLE_MTU_LIMIT,
    SEND_PACING,
    Transport,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

#: A Class 10 SET (the no-op ClockProgramOverview write-back) and a Class
#: 10 GET, as they go on the wire.
_SET = bytes.fromhex("2717e7f80a9354000100da0100000a02050005010100000000b44e")
_GET = bytes.fromhex("2707e7f80a03540001d5e8")


def notify(transport: Transport, data: bytes) -> None:
    """
    Feed one BLE notification in, the way bleak would.

    bleak passes the characteristic and the callback ignores it, so a test
    has nothing meaningful to supply; building a real
    BleakGATTCharacteristic to be discarded would be theatre. The cast says
    so rather than hiding it.
    """
    transport._notification_callback(
        cast("BleakGATTCharacteristic", None), bytearray(data)
    )


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Every sleep the transport asks for, in order."""
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(tmod.asyncio, "sleep", fake_sleep)
    return recorded


@pytest.fixture
def ble_client() -> MagicMock:
    client = MagicMock()
    client.write_gatt_char = AsyncMock()
    client.is_connected = True
    return client


@pytest.fixture
def transport(ble_client: MagicMock) -> Transport:
    return Transport(ble_client)


def written_chunks(ble_client: MagicMock) -> list[bytes]:
    return [bytes(c[0][1]) for c in ble_client.write_gatt_char.call_args_list]


# ---------------------------------------------------------------------------
# MTU chunking
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [1, 11, 20, 21, 40, 41, 59, 100])
@pytest.mark.asyncio
async def test_write_chunks_reassemble_to_the_original_frame(
    transport: Transport, ble_client: MagicMock, size: int
) -> None:
    """However a frame is split, the bytes on the link are the frame."""
    data = bytes((i % 256) for i in range(size))

    await transport.write(data)

    chunks = written_chunks(ble_client)
    assert b"".join(chunks) == data
    assert all(len(c) <= BLE_MTU_LIMIT for c in chunks), (
        f"A chunk exceeded the {BLE_MTU_LIMIT}-byte MTU: "
        f"{[len(c) for c in chunks]}"
    )


@pytest.mark.asyncio
async def test_write_splits_a_schedule_layer_frame_into_three_chunks(
    transport: Transport, ble_client: MagicMock
) -> None:
    """The 59-byte schedule write is the case two-chunk splitting broke."""
    await transport.write(bytes(59))

    assert [len(c) for c in written_chunks(ble_client)] == [20, 20, 19]


@pytest.mark.asyncio
async def test_write_uses_the_geni_characteristic(
    transport: Transport, ble_client: MagicMock
) -> None:
    await transport.write(bytes(30))

    for call in ble_client.write_gatt_char.call_args_list:
        assert call[0][0] == GENI_CHAR_UUID


# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consecutive_writes_are_paced(
    transport: Transport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Separate commands are held SEND_PACING apart, not just chunks."""
    slept: list[float] = []

    async def record_sleep(t: float) -> None:
        slept.append(t)

    monkeypatch.setattr("alpha_hwr.core.transport.asyncio.sleep", record_sleep)

    await transport.write(bytes(4))
    await transport.write(bytes(4))

    assert slept, "Second write was not paced"
    assert all(0 < t <= SEND_PACING for t in slept), slept


@pytest.mark.asyncio
async def test_first_write_is_not_delayed(
    transport: Transport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing has been sent yet, so there is no gap to wait out."""
    slept: list[float] = []

    async def record_sleep(t: float) -> None:
        slept.append(t)

    monkeypatch.setattr("alpha_hwr.core.transport.asyncio.sleep", record_sleep)

    await transport.write(bytes(4))

    assert slept == []


# ---------------------------------------------------------------------------
# Disconnect notification
# ---------------------------------------------------------------------------


def test_disconnect_handlers_run_in_registration_order(
    transport: Transport,
) -> None:
    calls: list[str] = []
    transport.add_disconnect_handler(lambda: calls.append("first"))
    transport.add_disconnect_handler(lambda: calls.append("second"))

    transport.notify_disconnected()

    assert calls == ["first", "second"]


def test_one_failing_disconnect_handler_does_not_block_the_others(
    transport: Transport,
) -> None:
    """A caller-supplied handler must not stop the rest from being told."""
    calls: list[str] = []

    def boom() -> None:
        raise RuntimeError("handler blew up")

    transport.add_disconnect_handler(boom)
    transport.add_disconnect_handler(lambda: calls.append("still ran"))

    transport.notify_disconnected()

    assert calls == ["still ran"]


@pytest.mark.asyncio
async def test_disconnect_clears_the_pacing_clock(
    transport: Transport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write on a fresh link must not wait out the old link's gap."""
    slept: list[float] = []

    async def record_sleep(t: float) -> None:
        slept.append(t)

    monkeypatch.setattr("alpha_hwr.core.transport.asyncio.sleep", record_sleep)

    await transport.write(bytes(4))
    transport.notify_disconnected()
    await transport.write(bytes(4))

    assert slept == []


class TestFramesAreChunkedForThePump:
    """
    This pump needs GENI frames split into 20-byte GATT writes.

    Not an optimisation, and not about the negotiated ATT MTU - which is 65
    on this link, easily enough for a 27-byte frame in one write. Measured:
    the Object 84 Sub 1 overview write sent as a single 27-byte
    write_gatt_char draws no reply at all, while the identical bytes
    chunked at 20 are acknowledged in 111 ms.

    An earlier reading of that silence was that Class 10 SETs are never
    acknowledged. They are, in 90-120 ms; the frames simply were not
    arriving.
    """

    @pytest.mark.asyncio
    async def test_a_frame_over_the_limit_is_split(
        self, transport: Transport, ble_client: MagicMock
    ) -> None:
        await transport.write(_SET)

        written = written_chunks(ble_client)
        assert len(written) > 1, "a 27-byte frame must not go out whole"
        assert all(len(chunk) <= BLE_MTU_LIMIT for chunk in written)
        assert b"".join(written) == _SET

    @pytest.mark.asyncio
    async def test_a_frame_within_the_limit_goes_in_one_write(
        self, transport: Transport, ble_client: MagicMock
    ) -> None:
        await transport.write(_GET)

        assert written_chunks(ble_client) == [_GET]

    @pytest.mark.asyncio
    async def test_chunks_are_paced(
        self, transport: Transport, slept: list[float]
    ) -> None:
        """The pump drops traffic that arrives faster than SEND_PACING."""
        await transport.write(_SET)

        assert slept, "chunks of one frame must be paced apart"


class TestFrameDropCounters:
    """
    A dropped frame leaves a trace.

    Dropping is the system working - a bad CRC caught is a corrupted frame
    that did not become a write verdict. What was missing is any way to
    know it happened: a link quietly shedding frames is otherwise
    indistinguishable from a client that occasionally times out for no
    reason. One counter per reason, because they mean different things.
    """

    @pytest.mark.asyncio
    async def test_a_bad_crc_is_counted(self, transport: Transport) -> None:
        delivered: list[bytes] = []
        transport._custom_handlers.append(delivered.append)

        corrupt = bytearray(CAPTURED["mode_read"])
        corrupt[-1] ^= 0xFF
        notify(transport, bytes(corrupt))

        assert delivered == []
        assert transport.frame_drops["crc_failures"] == 1

    @pytest.mark.asyncio
    async def test_an_impossible_length_is_counted_separately(
        self, transport: Transport
    ) -> None:
        """
        A runt length is a peer talking nonsense, not a corrupted link.

        Counting it as a CRC failure would make a framing bug look like
        radio interference.
        """
        notify(transport, bytes([0x24, 0x00, 0xF8, 0xE7, 0x0A, 0x00]))

        assert transport.frame_drops["runt_length_drops"] == 1
        assert transport.frame_drops["crc_failures"] == 0

    @pytest.mark.asyncio
    async def test_bytes_that_start_no_frame_are_counted(
        self, transport: Transport
    ) -> None:
        """Usually means sync was lost, not that the radio is bad."""
        notify(transport, b"\xde\xad\xbe\xef")

        assert transport.frame_drops["unsolicited_fragments"] == 1

    @pytest.mark.asyncio
    async def test_a_clean_frame_counts_nothing(
        self, transport: Transport
    ) -> None:
        delivered: list[bytes] = []
        transport._custom_handlers.append(delivered.append)

        notify(transport, CAPTURED["mode_read"])

        assert len(delivered) == 1
        assert not any(transport.frame_drops.values())
