"""
The flow-limiter write, at the wire.

Type 895 is one struct, so setting the cap rewrites all eighteen bytes,
twelve of which are the PID terms of the pump's limiter loop. What these
pin down is that those are echoed, never invented. Bench-verified through
esphome-alpha-hwr#299.
"""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock

import pytest
from wire import CAPTURED, class10_reply

from alpha_hwr.constants import FACTOR_M3H_TO_GPM
from alpha_hwr.protocol.matcher import matches, read_command

#: kp, ti, td as the bench pump holds them, from its 86/600 record (see
#: docs/protocol/bench_findings.md). Three distinct values, so an echo that
#: reorders or zeroes them cannot pass by accident.
PID = bytes.fromhex("3f19999a3fcccccd3ecccccd")

#: That record whole, size header included: MaxFlow, disabled, 1.50 gpm.
BENCH_600 = bytes.fromhex("000012010038c676f1") + PID


def record(name: int = 1, enabled: bool = False, gpm: float = 1.5) -> bytes:
    """A limiter_user_config reply body, with its three-byte size header."""
    m3s = gpm * FACTOR_M3H_TO_GPM / 3600.0
    return (
        b"\x00\x00\x12"
        + bytes([name, 0x01 if enabled else 0x00])
        + struct.pack(">f", m3s)
        + PID
    )


def apdu_of(packet: bytes) -> bytes:
    """``[27][len][E7][F8][APDU...][crc][crc]`` -> the APDU."""
    return packet[4:-2]


@pytest.fixture
def control(mock_client_simple):
    c = mock_client_simple.control
    c._send_with_retry = AsyncMock(return_value=True)
    return c


@pytest.mark.asyncio
async def test_the_frame_is_object_first_type_895_and_sized(control) -> None:
    control._read_class10_object = AsyncMock(return_value=record())

    assert await control.write_limiter_config("MaxFlow", True, 0.5)

    apdu = apdu_of(control._send_with_retry.await_args.args[0])
    assert apdu[:11] == bytes(
        [0x0A, 0x9B, 86, 0x02, 0x58, 0x03, 0x7F, 0x01, 0x00, 0x00, 0x12]
    )
    assert apdu[1] & 0x3F == len(apdu) - 2, "OpSpec declares what follows"
    assert (apdu[1] >> 6) == 0b10  # SET
    assert len(apdu) == 29


@pytest.mark.asyncio
async def test_the_pid_terms_and_the_name_are_echoed_verbatim(control) -> None:
    control._read_class10_object = AsyncMock(return_value=record(name=1))

    await control.write_limiter_config("MaxFlow", True, 0.5)

    body = apdu_of(control._send_with_retry.await_args.args[0])[11:]
    assert body[0] == 1, "the name byte comes from the pump"
    assert body[1] == 0x01
    assert struct.unpack(">f", body[2:6])[0] == pytest.approx(0.5 / 3600.0)
    assert body[6:] == PID


@pytest.mark.asyncio
async def test_no_record_means_no_write(control) -> None:
    """With nothing to echo, writing would zero the PID terms."""
    control._read_class10_object = AsyncMock(return_value=None)

    assert not await control.write_limiter_config("MaxFlow", True, 0.5)
    control._send_with_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_short_record_means_no_write(control) -> None:
    control._read_class10_object = AsyncMock(return_value=record()[:12])

    assert not await control.write_limiter_config("MaxFlow", True, 0.5)
    control._send_with_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_cap_keeps_the_stored_one_byte_for_byte(control) -> None:
    stored = record(gpm=1.6)
    control._read_class10_object = AsyncMock(return_value=stored)

    await control.write_limiter_config("MaxFlow", True, None)

    body = apdu_of(control._send_with_retry.await_args.args[0])[11:]
    assert body[2:6] == stored[5:9]


@pytest.mark.asyncio
async def test_minflow_is_sub_601(control) -> None:
    control._read_class10_object = AsyncMock(return_value=record(name=2))

    await control.write_limiter_config("minflow", False, 0.3)

    control._read_class10_object.assert_awaited_with(86, 601)
    apdu = apdu_of(control._send_with_retry.await_args.args[0])
    assert apdu[3:5] == b"\x02\x59"


@pytest.mark.asyncio
async def test_a_limiter_that_does_not_exist_is_refused(control) -> None:
    """A sweep found two and only two (esphome-alpha-hwr#274)."""
    with pytest.raises(ValueError, match="not a flow limiter"):
        await control.write_limiter_config("ReturnFlow", True, 0.5)


@pytest.mark.asyncio
async def test_the_read_reports_gpm_exact_caps_in_m3h(control) -> None:
    control._read_class10_object = AsyncMock(
        return_value=record(enabled=True, gpm=1.6)
    )

    stored = await control.read_limiter_config("MaxFlow")

    assert stored is not None
    enabled, m3h, raw = stored
    assert enabled is True
    assert m3h / FACTOR_M3H_TO_GPM == pytest.approx(1.6, abs=1e-4)
    assert len(raw) == 18


@pytest.mark.asyncio
async def test_the_bench_record_decodes_as_recorded(control) -> None:
    """MaxFlow disabled at 0.341 m3/h, which is 1.50 gpm."""
    control._read_class10_object = AsyncMock(return_value=BENCH_600)

    stored = await control.read_limiter_config("MaxFlow")

    assert stored is not None
    enabled, m3h, raw = stored
    assert enabled is False
    assert m3h / FACTOR_M3H_TO_GPM == pytest.approx(1.50, abs=1e-3)
    assert raw == BENCH_600[3:]


# ---------------------------------------------------------------------------
# Matching: a limiter read takes only a limiter reply
# ---------------------------------------------------------------------------

#: The bench 86/600 record as the pump would send it: type 895 version 1.
BENCH_600_REPLY = class10_reply(0x0003, 0x7F01, BENCH_600[3:])


@pytest.mark.parametrize("sub", [600, 601])
def test_a_limiter_reply_answers_a_limiter_read(sub: int) -> None:
    assert matches(read_command(86, sub), BENCH_600_REPLY)


@pytest.mark.parametrize("name", sorted(CAPTURED))
def test_no_recorded_frame_answers_a_limiter_read(name: str) -> None:
    """
    Before 86/600-601 had a type expectation, any Class 10 frame did.

    The recorded motor-state notification passes every length check a
    limiter read makes, which is the case that mattered.
    """
    assert not matches(read_command(86, 600), CAPTURED[name]), name


@pytest.mark.asyncio
async def test_telemetry_arriving_first_is_not_written_back(control) -> None:
    """
    The write echoes what the read returned, so the read must not take
    the first Class 10 frame that turns up.

    Delivers the recorded motor-state frame ahead of the limiter reply and
    lets the real matcher choose, the way the transport does.
    """
    arriving = [CAPTURED["motor_state"], BENCH_600_REPLY]

    async def send_command(_packet, command, timeout=3.0):
        return next((f for f in arriving if matches(command, f)), None)

    control.transport.send_command = AsyncMock(side_effect=send_command)

    assert await control.write_limiter_config("MaxFlow", True, 0.5)

    body = apdu_of(control._send_with_retry.await_args.args[0])[11:]
    assert body[0] == 1, "MaxFlow's name byte, not telemetry"
    assert body[6:] == PID, "the limiter's PID terms, not telemetry"


# ---------------------------------------------------------------------------
# What a read may hand the write as its template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_maxflow_record_answering_a_minflow_read_is_refused(
    control,
) -> None:
    """
    Both config records answer with type 895, so the matcher cannot tell a
    late MaxFlow reply from the MinFlow one. Echoed, it would copy MaxFlow's
    name and PID terms into MinFlow.
    """
    control._read_class10_object = AsyncMock(return_value=record(name=1))

    assert await control.read_limiter_config("MinFlow") is None
    assert not await control.write_limiter_config("MinFlow", True, 0.3)
    control._send_with_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_wrong_limiter_s_status_is_not_reported(control) -> None:
    """The diagnostic read shares the reader, and the same hazard."""
    control._read_class10_object = AsyncMock(return_value=record(name=2))

    limiters = await control.read_limiters()

    assert "MaxFlow" not in limiters
    assert "MinFlow" in limiters


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["7fffffff", "7f800000", "ff800000"])
async def test_a_cap_that_is_not_a_number_is_not_a_template(
    control, raw: str
) -> None:
    """
    NaN and infinity decode as floats. A NaN readback would compare
    unequal to everything and settle as a clamp; a write keeping the
    stored cap would echo it.
    """
    stored = b"\x00\x00\x12" + b"\x01\x01" + bytes.fromhex(raw) + PID
    control._read_class10_object = AsyncMock(return_value=stored)

    assert await control.read_limiter_config("MaxFlow") is None
    assert not await control.write_limiter_config("MaxFlow", True, None)
    control._send_with_retry.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("cap", [float("nan"), float("inf"), float("-inf")])
async def test_a_direct_write_of_a_non_finite_cap_is_refused(
    control, cap: float
) -> None:
    """The public primitive skips the verified write's checks; not this one."""
    control._read_class10_object = AsyncMock(return_value=record())

    assert not await control.write_limiter_config("MaxFlow", True, cap)
    control._send_with_retry.assert_not_awaited()
