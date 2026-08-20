"""
Building frames the pump could actually have sent.

Tests across this suite used to hand-assemble Class 10 replies, and each
one encoded the same three mistakes: the destination and source addresses
in request order, an APDU head chosen as a constant rather than as the
payload's length, and the requested Object/Sub-ID in bytes 6-9 where the
pump puts an object *type*. A fixture that reproduces a bug cannot catch
it, and several of these frames were asserted against for a long time.

Build replies with :func:`class10_reply` instead, or - better where one
exists - assert against a frame in :data:`CAPTURED`, which are recordings
from an ALPHA HWR rather than constructions.
"""

from __future__ import annotations

from alpha_hwr.utils import calc_crc16_read

#: A reply is addressed to us and sourced from the pump. Requests carry
#: these the other way round.
REPLY_DEST = 0xF8
REPLY_SRC = 0xE7


def frame(class_byte: int, apdu_payload: bytes, start: int = 0x24) -> bytes:
    """
    Wrap an APDU payload in a frame, with a real length and a real CRC.

    The APDU head is ``0booLLLLLL``: the operation or acknowledgement, then
    the payload's byte count. Passing a payload longer than 63 bytes raises
    rather than silently truncating the count into the operation bits.
    """
    if len(apdu_payload) > 0x3F:
        raise ValueError(
            f"{len(apdu_payload)} payload bytes cannot be declared in six bits"
        )
    dest, src = (REPLY_DEST, REPLY_SRC) if start == 0x24 else (REPLY_SRC, REPLY_DEST)
    apdu = bytes([class_byte, len(apdu_payload)]) + apdu_payload
    body = bytes([len(apdu) + 2, dest, src]) + apdu
    crc = calc_crc16_read(body)
    return bytes([start]) + body + bytes([crc >> 8, crc & 0xFF])


def class10_reply(type_high: int, type_low_ver: int, body: bytes) -> bytes:
    """
    Build a Class 10 data reply for an object of the given type.

    ``body`` is the object's struct; the three-byte ``[00][00][size]``
    header every captured reply carries is added here.
    """
    payload = (
        bytes([(type_high >> 8) & 0xFF, type_high & 0xFF])
        + bytes([(type_low_ver >> 8) & 0xFF, type_low_ver & 0xFF])
        + bytes([0x00, 0x00, len(body)])
        + body
    )
    return frame(0x0A, payload)


def class10_ack(status: int = 0x00) -> bytes:
    """The nine-byte acknowledgement a Class 10 write draws."""
    return frame(0x0A, bytes([status]))


def class10_refusal(item_id: int = 0x00) -> bytes:
    """
    An Unknown Data Item refusal naming the item the pump did not know.

    Head ``0x81`` is ``10 000001``. The payload byte is the item's ID, not
    an error code - which is why reading it as one turned a refusal naming
    item 0 into a success.
    """
    apdu = bytes([0x0A, 0x81, item_id])
    body = bytes([len(apdu) + 2, REPLY_DEST, REPLY_SRC]) + apdu
    crc = calc_crc16_read(body)
    return bytes([0x24]) + body + bytes([crc >> 8, crc & 0xFF])


#: Frames recorded from an ALPHA HWR (family 52, type 7, version 2) on
#: 2026-08-20. Prefer these to anything built here.
CAPTURED = {
    "class7_product_name": bytes.fromhex(
        "240ef8e7070a414c5048412048575200838d"
    ),
    "class7_serial": bytes.fromhex("240df8e70709313030303034373900c347"),
    "motor_state": bytes.fromhex(
        "2434f8e70a300001000300002942e730d643237a000000000000000000"
        "00000000000000007fffffff7fffffff0000000000000000002385"
    ),
    "flow_pressure": bytes.fromhex(
        "242ff8e70a2b0002350200002400000000000000007fffffff7fffffff"
        "7fffffff7fffffff000000000000000000000000edbe"
    ),
    "temperature": bytes.fromhex(
        "2418f8e70a140002160200000d41e0f24d41e9654e41d60bac001c01"
    ),
    "mode_read": bytes.fromhex("2412f8e70a0e00012f0100000701001b39678ac3f7dd"),
    "setpoint_range_speed": bytes.fromhex(
        "2427f8e70a2300012d0100001c452f000044ce400045657000"
        "c56570003f8000003f8000003f80000089a9"
    ),
    "schedule_overview": bytes.fromhex(
        "2415f8e70a110000da0100000a02050005010100000000dd89"
    ),
    "clock": bytes.fromhex("2417f8e70a130001420100000c07ea08140a04155b000401017298"),
    "temp_range_config": bytes.fromhex(
        "2419f8e70a150003f40200000e00420c0000421b999a0f3c020501ec1f"
    ),
}
