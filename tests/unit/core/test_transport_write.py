"""
Unit tests for Transport's BLE write path.

Covers MTU chunking and send pacing. An earlier revision split every
frame into exactly two chunks, so anything over 40 bytes was silently
truncated - including the 59-byte schedule-layer write, whose second
chunk still exceeded the 20-byte MTU.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.constants import GENI_CHAR_UUID
from alpha_hwr.core.transport import BLE_MTU_LIMIT, SEND_PACING, Transport


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
