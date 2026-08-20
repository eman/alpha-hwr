"""
GENI protocol frame parser.

A frame is::

    [0]     start: 0x24 from the pump, 0x27 from us
    [1]     length: bytes from [2] through the last APDU byte
    [2]     destination address
    [3]     source address
    [4]     class
    [5]     APDU head: 0booLLLLLL - operation/ack, then payload length
    [6:]    APDU payload
    [-2:]   CRC-16-CCITT over frame[1:-2], final XOR 0xFFFF

Bytes 2 and 3 are addresses, not a "service ID". We send
``[0x27][len][0xE7][0xF8]`` - destination 0xE7 is the pump's unit address,
source 0xF8 is ours - and the pump answers ``[0x24][len][0xF8][0xE7]`` with
the two swapped. Frames in this package's history that show ``24 .. E7 F8``
were written by hand rather than captured; a real reply never looks like
that.

Two things follow from the APDU head (see :mod:`alpha_hwr.protocol.apdu`)
and both were wrong here until they were decoded properly:

**The payload is bounded by its declared length, not by the CRC.** A GENIbus
telegram may carry several APDUs - the application manual is explicit that
"errors in one APDU will in no way influence the reply to sound APDU's" - so
an error reply can substitute for one answer inside a telegram carrying
others. Slicing to ``[-2]`` therefore reports the *next* APDU, and its CRC,
as this one's payload. :attr:`ParsedFrame.multi_apdu` says when there was
more in the telegram than the frame reports.

**Byte 5 is not an opcode.** The set ``{0x30, 0x2B, 0x14, 0x2E, 0x2D, 0x09}``
was carried here as "register-read operation specifiers" and used to select a
different payload offset. They are the payload lengths 48, 43, 20, 46, 45 and
9. Nothing dispatches on them any more.

A Class 10 reply's bytes 6-9 are ``[00][TypeH][TypeL][Version]`` - the
object's *type*, not the Object ID and Sub-ID it was asked for. The pump
does not echo an address. Measured against an ALPHA HWR: reading Object 86
sub-ids 13, 15, 17 and 39 returns ``00 01 2d 01`` for all four, because they
are four instances of type 301 version 1. See
:mod:`alpha_hwr.protocol.matcher` for what that costs a caller.

For the full wire reference see ``docs/protocol/wire_format.md``.
"""

from dataclasses import dataclass
from typing import Literal

from ..constants import CLASS_10, FRAME_START, RESPONSE_START
from ..utils import calc_crc16_read
from .apdu import apdu_payload_len

#: Smallest legal frame: start, length, destination, source, class, APDU
#: head and two CRC bytes, with an empty payload.
MIN_FRAME_LENGTH = 8

#: Bytes 6-9 of a Class 10 reply carry ``[00][TypeH][TypeL][Version]``, so a
#: frame has to reach this length before it can be said to carry a type.
MIN_TYPED_LENGTH = 12

#: Offset of the first payload byte in a Class 10 reply, past the type and
#: version fields.
CLASS10_BODY_OFFSET = 10


@dataclass
class ParsedFrame:
    """
    Parsed GENI protocol frame.

    Attributes:
        valid: The frame is structurally sound - plausible start byte, and
            long enough for the length it declares.
        frame_type: 'request' (0x27) or 'response' (0x24).
        class_byte: GENI class byte (2, 3, 7, 10, ...).
        type_high: Bytes 6-7 of a Class 10 reply. None for other classes.
        type_low_ver: Bytes 8-9 of a Class 10 reply - the low byte of the
            object type and its version. None for other classes.
        payload: Payload of the *first* APDU, bounded by the length that
            APDU declares.
        multi_apdu: The telegram carried more after the first APDU. This
            describes the telegram, not the payload, so it can be true on a
            frame too short to extract any payload from.
        crc_valid: The trailing CRC matches the body.
        raw_data: Original frame bytes.

    Note:
        ``valid`` says the frame parses, not that it is trustworthy. Check
        ``crc_valid`` before believing a payload - or better, let
        :class:`~alpha_hwr.core.transport.Transport` drop bad frames before
        they reach here, which is what it now does.
    """

    valid: bool
    frame_type: Literal["request", "response"] | None
    class_byte: int | None
    type_high: int | None
    type_low_ver: int | None
    payload: bytes
    multi_apdu: bool
    crc_valid: bool
    raw_data: bytes

    @property
    def object_body(self) -> bytes:
        """
        Payload with the object's three-byte size header removed.

        A typed Class 10 object puts ``[00][00][size]`` in front of its
        struct. Measured on an ALPHA HWR: the motor register declares 48
        payload bytes, of which four are the type fields, leaving 44 from
        offset 10 - and the first three of those read ``00 00 29``, a size
        of 41, which is exactly the 44 that remain. The same holds for the
        flow (36 of 39), temperature (13 of 16) and schedule-overview
        (10 of 13) replies.

        Returns the payload unchanged when no such header is present, so a
        short acknowledgement is not mistaken for a truncated struct.
        """
        body = self.payload
        if (
            len(body) >= 3
            and body[0] == 0
            and body[1] == 0
            and body[2] == len(body) - 3
        ):
            return body[3:]
        return body

    @property
    def sub_id(self) -> int | None:
        """
        Deprecated alias for :attr:`type_high`.

        A response carries no Sub-ID; this name survives only so older
        callers keep working while they are moved over.
        """
        return self.type_high

    @property
    def obj_id(self) -> int | None:
        """
        Deprecated alias for :attr:`type_low_ver`.

        A response carries no Object ID - see the module docstring.
        """
        return self.type_low_ver


def frame_crc_valid(data: bytes) -> bool:
    """
    Whether a frame's trailing CRC matches its body.

    The CRC covers ``frame[1:-2]``: the start byte is excluded because it is
    a delimiter, and the CRC cannot cover itself.

    Examples:
        >>> frame_crc_valid(bytes.fromhex('240ef8e7070a414c5048412048575200838d'))
        True
        >>> frame_crc_valid(bytes.fromhex('240ef8e7070a414c5048412048575200ffff'))
        False
    """
    if len(data) < 4:
        return False
    return calc_crc16_read(data[1:-2]) == ((data[-2] << 8) | data[-1])


class FrameParser:
    """
    Parses GENI protocol frames.

    Stateless - each frame is parsed independently.
    """

    @staticmethod
    def parse_frame(data: bytes) -> ParsedFrame:
        """
        Parse a raw GENI frame into structured data.

        Args:
            data: One reassembled frame. Trailing bytes beyond the declared
                length are ignored rather than folded into the payload.

        Returns:
            ParsedFrame with fields extracted and validation flags set.

        Examples:
            >>> # Object 86 Sub 7, captured from an ALPHA HWR
            >>> f = FrameParser.parse_frame(
            ...     bytes.fromhex('2412f8e70a0e00012f0100000701001b39678ac3f7dd'))
            >>> f.valid, f.crc_valid, f.class_byte
            (True, True, 10)
            >>> hex(f.type_high), hex(f.type_low_ver)
            ('0x1', '0x2f01')
            >>> f.multi_apdu
            False

            >>> # A refusal: Unknown Data Item naming item 0x00
            >>> r = FrameParser.parse_frame(bytes.fromhex('2407f8e70a810040405ebf'))
            >>> r.class_byte, r.payload.hex()
            (10, '00')
            >>> r.multi_apdu
            True
        """
        result = ParsedFrame(
            valid=False,
            frame_type=None,
            class_byte=None,
            type_high=None,
            type_low_ver=None,
            payload=b"",
            multi_apdu=False,
            crc_valid=False,
            raw_data=data,
        )

        if len(data) < MIN_FRAME_LENGTH:
            return result

        start_byte = data[0]
        if start_byte == RESPONSE_START:
            result.frame_type = "response"
        elif start_byte == FRAME_START:
            result.frame_type = "request"
        else:
            return result

        # A frame promising fewer bytes than the protocol's minimum is not a
        # short frame, it is a broken one. Clamping instead would leave a
        # "valid" frame with no class byte.
        declared_total = data[1] + 4
        if declared_total < MIN_FRAME_LENGTH or declared_total > len(data):
            return result

        result.valid = True
        result.crc_valid = frame_crc_valid(data[:declared_total])
        result.class_byte = data[4]

        # Everything from here is bounded by what the first APDU declares.
        # body_limit is where the CRC starts; apdu1_end is where this APDU's
        # payload stops. They differ exactly when the telegram carries more.
        body_limit = declared_total - 2
        apdu1_end = min(6 + apdu_payload_len(data[5]), body_limit)
        result.multi_apdu = apdu1_end < body_limit

        if result.class_byte == CLASS_10:
            if len(data) >= MIN_TYPED_LENGTH:
                result.type_high = (data[6] << 8) | data[7]
                result.type_low_ver = (data[8] << 8) | data[9]
            if apdu1_end > CLASS10_BODY_OFFSET:
                result.payload = data[CLASS10_BODY_OFFSET:apdu1_end]
            elif apdu1_end > 6:
                # A short Class 10 reply - an acknowledgement or a refusal -
                # carries its one byte at offset 6, with no type fields.
                result.payload = data[6:apdu1_end]
        else:
            result.payload = data[6:apdu1_end]

        return result

    @staticmethod
    def is_telemetry_frame(frame: ParsedFrame) -> bool:
        """
        Check whether a frame is one of the known telemetry notifications.

        Args:
            frame: Parsed frame from parse_frame().

        Returns:
            True if the frame's type matches a known telemetry object.
        """
        if not frame.valid or frame.class_byte != CLASS_10:
            return False
        return (frame.type_low_ver, frame.type_high) in TELEMETRY_TYPES

    @staticmethod
    def validate_frame_integrity(frame: ParsedFrame) -> tuple[bool, str]:
        """
        Validate a parsed frame, with a reason when it fails.

        Args:
            frame: Parsed frame from parse_frame().

        Returns:
            ``(is_valid, error_message)``; the message is empty when valid.

        Examples:
            >>> f = FrameParser.parse_frame(
            ...     bytes.fromhex('240ef8e7070a414c5048412048575200838d'))
            >>> FrameParser.validate_frame_integrity(f)
            (True, '')
        """
        if not frame.valid:
            return False, "Invalid frame structure (bad start byte or length)"

        if not frame.crc_valid:
            return False, "CRC checksum mismatch"

        if frame.class_byte is None:
            return False, "Missing class byte"

        return True, ""


#: Response types the pump's telemetry stream uses, as
#: ``(type_low_ver, type_high)``.
TELEMETRY_TYPES = {
    (0x0003, 0x0001),  # motor state
    (0x3502, 0x0002),  # flow / pressure
    (0x1602, 0x0002),  # temperature
    (0x3A01, 0x0002),  # active alarms *and* active warnings
}


#: Frames captured from an ALPHA HWR (family 52, type 7, version 2) on
#: 2026-08-20, for validating a reimplementation.
#:
#: These are recordings, not constructions. An earlier table here was
#: hand-written and had the destination and source addresses the wrong way
#: round, which no reply from this pump ever has - so anything checked
#: against it was being checked against a frame the pump cannot send.
TEST_VECTORS = {
    "class7_product_name": {
        "hex": "240ef8e7070a414c5048412048575200838d",
        "expected": {
            "valid": True,
            "frame_type": "response",
            "class_byte": 7,
            "payload": "ALPHA HWR\x00",
            "crc_valid": True,
        },
    },
    "class10_mode_read": {
        "hex": "2412f8e70a0e00012f0100000701001b39678ac3f7dd",
        "expected": {
            "valid": True,
            "frame_type": "response",
            "class_byte": 10,
            "type_high": 0x0001,
            "type_low_ver": 0x2F01,
            "payload_len": 10,
            "crc_valid": True,
        },
    },
    "class10_setpoint_range": {
        "hex": (
            "2427f8e70a2300012d0100001c452f000044ce400045657000"
            "c56570003f8000003f8000003f80000089a9"
        ),
        "expected": {
            "valid": True,
            "frame_type": "response",
            "class_byte": 10,
            "type_high": 0x0001,
            "type_low_ver": 0x2D01,
            "payload_len": 31,
            "crc_valid": True,
        },
    },
    "class10_schedule_overview": {
        "hex": "2415f8e70a110000da0100000a02050005010100000000dd89",
        "expected": {
            "valid": True,
            "frame_type": "response",
            "class_byte": 10,
            "type_high": 0x0000,
            "type_low_ver": 0xDA01,
            "payload_len": 13,
            "crc_valid": True,
        },
    },
}
