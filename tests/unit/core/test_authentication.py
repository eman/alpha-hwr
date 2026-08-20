"""
Opening a session sends nothing.

These tests used to pin the ordering and pacing of a ten-packet "unlock
handshake". There is no handshake: all four distinct packets were reads,
their replies were discarded, and a link that sends none of them answers
every read this client makes. What is worth pinning now is the opposite
property - that nothing goes out - because the failure mode this replaces
was writing to the pump for no reason and calling it authentication.

See ``docs/protocol/connection.md`` and the module docstring of
``alpha_hwr.core.authentication``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.core.authentication import AuthenticationHandler
from alpha_hwr.protocol.apdu import ApduOp, apdu_op, apdu_payload_len


@pytest.fixture
def writer() -> MagicMock:
    w = MagicMock()
    w.write_gatt_char = AsyncMock()
    return w


@pytest.fixture
def handler(writer: MagicMock) -> AuthenticationHandler:
    return AuthenticationHandler(writer)


@pytest.mark.asyncio
async def test_authenticate_writes_nothing(
    handler: AuthenticationHandler, writer: MagicMock
) -> None:
    assert await handler.authenticate(fast_mode=True) is True
    assert writer.write_gatt_char.await_count == 0


@pytest.mark.asyncio
async def test_authenticate_succeeds(handler: AuthenticationHandler) -> None:
    """
    There is no handshake to fail.

    A pump that will not answer shows up as an unanswered read, which is
    where it can be diagnosed - not as a handshake that "failed" without
    anything having been asked of the pump.
    """
    assert await handler.authenticate(fast_mode=True) is True


@pytest.mark.asyncio
async def test_the_settle_wait_is_skippable(
    handler: AuthenticationHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(
        "alpha_hwr.core.authentication.asyncio.sleep", fake_sleep
    )

    await handler.authenticate(fast_mode=True)
    assert slept == []

    await handler.authenticate()
    assert slept == [0.5]


@pytest.mark.asyncio
async def test_the_transaction_lock_is_held_when_one_is_supplied(
    writer: MagicMock,
) -> None:
    """
    The lock is still taken, so nothing else talks while the link settles.
    """
    lock = MagicMock()
    lock.__aenter__ = AsyncMock()
    lock.__aexit__ = AsyncMock(return_value=False)

    handler = AuthenticationHandler(writer, transaction=lock)
    await handler.authenticate(fast_mode=True)

    lock.__aenter__.assert_awaited_once()
    lock.__aexit__.assert_awaited_once()


class TestTheOpeningPacketsAreReads:
    """
    The four captured packets, decoded.

    They are kept as constants because they are real captures and make
    good frame-assembly vectors, but every one of them is a read - which
    is why none of them could ever have unlocked anything.
    """

    @pytest.mark.parametrize(
        ("packet", "expected_op"),
        [
            (AuthenticationHandler.LEGACY_MAGIC, ApduOp.GET),
            (AuthenticationHandler.CLASS10_UNLOCK, ApduOp.GET),
            (AuthenticationHandler.EXTEND_1, ApduOp.INFO),
            (AuthenticationHandler.EXTEND_2, ApduOp.INFO),
        ],
    )
    def test_none_of_them_is_a_write(
        self, packet: bytes, expected_op: ApduOp
    ) -> None:
        assert apdu_op(packet[5]) == expected_op
        assert apdu_op(packet[5]) != ApduOp.SET

    def test_the_unlock_code_was_a_length_field(self) -> None:
        """
        ``0x03`` is an APDU head, not an opcode.

        Read as one it made ``94 95 96`` look like "register 0x9495,
        unlock code 0x96". It declares three payload bytes, and those
        bytes are three item IDs: unit_family, unit_type, unit_version.
        """
        head = AuthenticationHandler.LEGACY_MAGIC[5]

        assert head == 0x03
        assert apdu_payload_len(head) == 3
        assert AuthenticationHandler.LEGACY_MAGIC[6:9] == bytes(
            [0x94, 0x95, 0x96]
        )
