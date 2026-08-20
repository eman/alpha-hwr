"""
Tests for response matching.

These pin the pump's observed firmware behaviour: which replies may be
attributed to a queued command and which must be left for the telemetry
path. The frames here are the shapes seen in real captures, so a change
that breaks one of these is a change to what the pump is believed to do.
"""

from __future__ import annotations

import pytest

from alpha_hwr.protocol.matcher import (
    Command,
    expected_reply,
    frame_identifiers,
    is_short_ack,
    matches,
    read_command,
    short_ack_accepted,
)


def frame(
    cls: int,
    opspec: int,
    *,
    a: int | None = None,
    b: int | None = None,
    payload: bytes = b"",
    start: int = 0x24,
) -> bytes:
    """Build a response frame; omit a/b for a short (unidentified) one."""
    body = bytearray([cls, opspec])
    if a is not None and b is not None:
        body += bytes([a >> 8, a & 0xFF, b >> 8, b & 0xFF])
    body += payload
    return bytes([start, len(body) + 2, 0xF8, 0xE7]) + bytes(body) + b"\x00\x00"


# ---------------------------------------------------------------------------
# Short Class 3/7 acknowledgements
# ---------------------------------------------------------------------------


def test_clean_class3_ack_is_recognised() -> None:
    """[03 00] - the pump executed the command."""
    ack = frame(0x03, 0x00)

    assert is_short_ack(ack)
    assert short_ack_accepted(ack) is True


def test_descriptor_only_class3_reply_is_a_rejection() -> None:
    """[03 01 AC] - the pump described the item instead of acting on it."""
    nack = frame(0x03, 0x01, payload=b"\xac")

    assert is_short_ack(nack)
    assert short_ack_accepted(nack) is False


def test_class3_ack_satisfies_a_class3_command() -> None:
    assert matches(Command(expect_class=0x03), frame(0x03, 0x00))


def test_class3_ack_does_not_satisfy_a_class10_command() -> None:
    """
    A queued Class 10 read must not be answered by an unrelated Class 3
    ack that happens to arrive first.
    """
    assert not matches(Command(expect_a=86, expect_b=7), frame(0x03, 0x00))


def test_class10_telemetry_does_not_satisfy_a_class3_command() -> None:
    telemetry = frame(0x0A, 0x0E, a=0x0001, b=0x2F01, payload=bytes(8))

    assert not matches(Command(expect_class=0x03), telemetry)


def test_a_full_length_frame_is_not_a_short_ack() -> None:
    assert not is_short_ack(frame(0x0A, 0x0E, a=1, b=2, payload=bytes(8)))
    assert short_ack_accepted(frame(0x0A, 0x0E, a=1, b=2)) is None


# ---------------------------------------------------------------------------
# Class 10 identifier matching
# ---------------------------------------------------------------------------


def test_identifiers_are_read_from_bytes_6_to_9() -> None:
    assert frame_identifiers(frame(0x0A, 0x0E, a=0x0001, b=0x2F01)) == (
        0x0001,
        0x2F01,
    )


def test_exact_identifier_match() -> None:
    cmd = Command(expect_a=0x0001, expect_b=0x2F01)

    assert matches(cmd, frame(0x0A, 0x0E, a=0x0001, b=0x2F01))


def test_swapped_type_fields_do_not_match() -> None:
    """
    Bytes 6-9 are one type field, so reversing them is not the same type.

    This used to be asserted the other way round, on the theory that the
    pump placed two identifiers inconsistently. It does not place
    identifiers at all - it names the object's type - and every reply
    measured against an ALPHA HWR matches in wire order, so nothing ever
    needed the reversal. Accepting it meant any two objects whose type
    bytes were transposes of each other could answer each other's reads.
    """
    cmd = Command(expect_a=0x2F01, expect_b=0x0001)

    assert not matches(cmd, frame(0x0A, 0x0E, a=0x0001, b=0x2F01))


def test_the_measured_mode_reply_matches_in_wire_order() -> None:
    """
    Object 86 Sub 7, captured 2026-08-20, against the table's expectation.

    Uses the real frame rather than a synthetic one so the table and the
    pump are checked against each other, not against the same assumption.
    """
    captured = bytes.fromhex("2412f8e70a0e00012f0100000701001b39678ac3f7dd")

    assert matches(read_command(86, 7), captured)


def test_a_sibling_of_the_same_type_answers_the_same_expectation() -> None:
    """
    Object 86 subs 13, 15, 17 and 39 are indistinguishable in a reply.

    All four are type 301 version 1, so the setpoint-range read of sub 13
    accepts sub 15's answer. That is not a defect in the matcher - the
    information is not on the wire - which is why the chain that reads them
    has to be sequential and stop at the first failure.
    """
    sub15_reply = bytes.fromhex(
        "2427f8e70a2300012d0100001c467a00004619300046bbb200"
        "461930003dcccccd3f7333333f8000006f88"
    )

    assert matches(read_command(86, 13), sub15_reply)
    assert read_command(86, 13) == read_command(86, 39)


def test_unrelated_identifiers_do_not_match() -> None:
    cmd = Command(expect_a=0x0056, expect_b=0x0027)

    assert not matches(cmd, frame(0x0A, 0x0E, a=0x2D01, b=0x0001))


def test_a_zeroed_identifier_is_not_treated_as_a_wildcard() -> None:
    """
    A zero in the first field is that object's real value, not a wildcard.
    Reading it as one made an event log entry (0x0000, 0xF402) a valid
    answer to a temperature-range read (0x0003, 0xF402), since they share
    a type code and differ only in the field a wildcard would discard.
    """
    temp_range = read_command(91, 430)
    event_entry = frame(0x0A, 0x14, a=0x0000, b=0xF402, payload=bytes(16))

    assert not matches(temp_range, event_entry)


def test_wildcard_command_takes_any_class10_response() -> None:
    cmd = Command()

    assert matches(cmd, frame(0x0A, 0x0E, a=0x1234, b=0x5678))


# ---------------------------------------------------------------------------
# Register-read filtering
# ---------------------------------------------------------------------------


def test_event_log_entries_are_matched_by_their_type_code() -> None:
    """
    An event log entry's reply is 20 bytes, which an inherited filter used
    to reject by length. It is matched by its type code instead.
    """
    cmd = read_command(88, 10200)

    assert matches(
        cmd, frame(0x0A, 0x14, a=0x0000, b=0xF402, payload=bytes(16))
    )


# ---------------------------------------------------------------------------
# Class 10 write acknowledgements
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("opspec", [0x01, 0x81])
def test_write_ack_only_satisfies_a_command_expecting_one(
    opspec: int,
) -> None:
    ack = frame(0x0A, opspec)

    assert matches(Command(expect_short_ack=True), ack)
    assert not matches(Command(), ack)


# ---------------------------------------------------------------------------
# Degenerate input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("packet", [b"", b"\x24", b"\x24\x05\xf8\xe7\x0a"])
def test_frames_too_short_to_classify_never_match(packet: bytes) -> None:
    assert not matches(Command(), packet)


# ---------------------------------------------------------------------------
# Operation-specifier filtering
# ---------------------------------------------------------------------------


def test_accept_opspecs_narrows_to_the_listed_specifiers() -> None:
    """The clock write is identified by its ack, not by any identifier."""
    cmd = Command(accept_opspecs=frozenset({0x01}))

    assert matches(cmd, frame(0x0A, 0x01, a=0, b=0, payload=bytes(8)))
    assert not matches(cmd, frame(0x0A, 0x0E, a=0, b=0, payload=bytes(8)))


def test_reject_opspecs_turns_away_the_notification_stream() -> None:
    """
    A telemetry register read shares its class with the pump's unsolicited
    stream, so the read has to turn the stream away explicitly.
    """
    cmd = Command(reject_opspecs=frozenset({0x0E}))

    assert matches(cmd, frame(0x0A, 0x30, a=0, b=0, payload=bytes(30)))
    assert not matches(cmd, frame(0x0A, 0x0E, a=0, b=0, payload=bytes(8)))


def test_reject_wins_over_accept() -> None:
    cmd = Command(
        accept_opspecs=frozenset({0x0E}), reject_opspecs=frozenset({0x0E})
    )

    assert not matches(cmd, frame(0x0A, 0x0E, a=0, b=0, payload=bytes(8)))


# ---------------------------------------------------------------------------
# Deriving the expected class from the request
# ---------------------------------------------------------------------------


def test_for_request_takes_the_class_from_the_frame_being_sent() -> None:
    """
    A Class 3 command must not be satisfied by a Class 10 notification, and
    deriving the class from the request is what makes that automatic.
    """
    class3_request = bytes([0x27, 0x05, 0xE7, 0xF8, 0x03, 0x81, 0x06, 0, 0])

    cmd = Command.for_request(class3_request, expect_short_ack=True)

    assert cmd.expect_class == 0x03
    assert matches(cmd, frame(0x03, 0x00))
    assert not matches(cmd, frame(0x0A, 0x0E, a=1, b=2, payload=bytes(8)))


def test_for_request_falls_back_to_class10_for_an_unreadable_frame() -> None:
    assert Command.for_request(b"").expect_class == 0x0A


# ---------------------------------------------------------------------------
# Measured reply identifiers
#
# Captured from an ALPHA HWR on 2026-08-04; identical across two runs. Each
# case is one real frame the pump sent in answer to that object's read.
# ---------------------------------------------------------------------------

MEASURED = [
    # (obj, sub, reply frame hex, what it is)
    (86, 6, "2412f8e70a0e00012f0100000700001b39678ac34fbc", "operation status"),
    (
        86,
        7,
        "2412f8e70a0e00012f0100000701001b39678ac3f7dd",
        "prioritized state",
    ),
    (86, 10, "2412f8e70a0e00012f0100000700061b7fffffff5ab3", "mode request"),
    (
        86,
        13,
        (
            "2427f8e70a2300012d0100001c452f000044ce400045657000c56570003f80"
            "00003f8000003f80000089a9"
        ),
        "speed limits",
    ),
    (
        91,
        421,
        "2411f8e70a0d0003d90100000638844f30050fe9cb",
        "cycle-time config",
    ),
    (
        91,
        430,
        "2419f8e70a150003f40200000e01420c0000421b999a0f3c020501977e",
        "temperature range",
    ),
    (
        84,
        1,
        "2415f8e70a110000da0100000a02050005010100000000dd89",
        "schedule overview",
    ),
    (
        84,
        900,
        "2415f8e70a110000dc0100000a01026a7200206a720188c982",
        "single event",
    ),
    (
        88,
        10199,
        "2412f8e70a0e0000f301000007023000140014003920",
        "event log metadata",
    ),
    (
        88,
        10200,
        "2418f8e70a140000f40200000d021d00480601016a4a3d8300002a92",
        "event log entry",
    ),
    (
        94,
        101,
        "2417f8e70a130001420100000c07ea08041019043100020101e229",
        "clock",
    ),
]


@pytest.mark.parametrize(("obj", "sub", "reply", "label"), MEASURED)
def test_read_command_matches_the_pump_s_actual_reply(
    obj: int, sub: int, reply: str, label: str
) -> None:
    assert matches(read_command(obj, sub), bytes.fromhex(reply)), label


@pytest.mark.parametrize(("obj", "sub", "reply", "label"), MEASURED)
def test_a_read_is_not_answered_by_another_object_s_reply(
    obj: int, sub: int, reply: str, label: str
) -> None:
    """
    Every measured reply must be rejected by the reads it does not belong
    to - otherwise matching by type code buys nothing over a wildcard.
    """
    frame_bytes = bytes.fromhex(reply)
    mine = expected_reply(obj, sub)

    for other_obj, other_sub, _, other_label in MEASURED:
        if expected_reply(other_obj, other_sub) == mine:
            continue  # same type code; genuinely indistinguishable
        assert not matches(read_command(other_obj, other_sub), frame_bytes), (
            f"{label} reply was accepted as an answer to {other_label}"
        )


def test_byte_5_of_a_response_is_a_length_field() -> None:
    """
    The operation bits are always 00 and the low six bits are the payload
    length. This is why the inherited "register-read operation specifier"
    filter was really filtering by payload size, and why it is gone.
    """
    for _obj, _sub, reply, label in MEASURED:
        f = bytes.fromhex(reply)
        payload_len = f[5] & 0x3F
        assert f[5] >> 6 == 0, f"{label}: operation bits set"
        assert len(f) == payload_len + 8, f"{label}: total length"
        assert f[1] == payload_len + 4, f"{label}: length field"


def test_unmeasured_objects_fall_back_to_a_class_match() -> None:
    """
    Guessing an identifier for an object nobody has measured would reject
    the real reply, which is worse than matching loosely.
    """
    assert expected_reply(999, 1) is None
    assert read_command(999, 1).is_wildcard
