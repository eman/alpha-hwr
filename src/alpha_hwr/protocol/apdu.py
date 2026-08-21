"""
The APDU head: one byte carrying an operation and a length.

Byte 5 of a GENI frame is ``0booLLLLLL``. The top two bits are the
operation in a request and the acknowledgement in a reply; the low six are
the number of payload bytes that follow. There is no opcode field, and
nothing in this protocol is identified by an "OpSpec".

That matters because this package spent a long time treating byte 5 as an
opcode. Two of the resulting mistakes were live until the ESPHome port
decoded the byte properly:

* ``{0x30, 0x2B, 0x14, 0x2E, 0x2D, 0x09}`` was carried as a set of
  "register-read operation specifiers" and used to *discard* frames. Those
  are the payload lengths 48, 43, 20, 46, 45 and 9, so a reply carrying
  exactly the type its command asked for was thrown away because its
  *length* collided with a telemetry register's.
* ``0x81`` was read as "acknowledgement, error code follows". It is
  ``10 000001``: Unknown Data Item, one payload byte - and that byte is the
  **ID of the item the pump did not recognise**, not an error code. A
  refused write therefore read as accepted whenever the offending ID
  happened to be ``0x00``, which is exactly the case this pump produces.

The relation ``byte5 == len(frame) - 8`` holds for every one of the 26,898
CRC-valid inbound frames in the capture corpus, which is what settled it.

See ``docs/protocol/wire_format.md``.
"""

from __future__ import annotations

from enum import IntEnum

#: Mask selecting the payload-length bits of an APDU head.
APDU_LEN_MASK = 0x3F

#: Bytes of frame overhead around an APDU's payload: start, length,
#: destination, source, class, APDU head, and the two CRC bytes.
FRAME_OVERHEAD = 8


class ApduOp(IntEnum):
    """
    The operation a *request* asks for.

    There is deliberately no ``0b01``. It was long documented as one - the
    frame builder called ``0b00`` INFO and had no name for ``0b11`` - and
    issue #46 in the ESPHome port is what confusing the two costs.
    """

    GET = 0b00
    SET = 0b10
    INFO = 0b11


class ApduAck(IntEnum):
    """
    The acknowledgement a *reply* carries.

    Only :attr:`OK` means the pump acted. The three refusals each name a
    different reason the request could not be honoured, and the two item
    errors carry the offending Data Item's ID as their single payload byte.
    """

    OK = 0b00
    UNKNOWN_CLASS = 0b01
    UNKNOWN_DATA_ITEM = 0b10
    ILLEGAL_OPERATION = 0b11


def apdu_payload_len(head: int) -> int:
    """
    Payload byte count declared by an APDU head.

    Examples
    --------
    >>> apdu_payload_len(0x0A)
    10
    >>> apdu_payload_len(0x81)
    1
    >>> apdu_payload_len(0x40)
    0
    """
    return head & APDU_LEN_MASK


def apdu_op(head: int) -> int:
    """Operation bits of a *request* APDU head."""
    return (head >> 6) & 0b11


def apdu_ack(head: int) -> int:
    """Acknowledgement bits of a *reply* APDU head."""
    return (head >> 6) & 0b11


def apdu_ack_is_ok(head: int) -> bool:
    """
    True when a reply's APDU head reports success.

    Examples
    --------
    >>> apdu_ack_is_ok(0x0A)
    True
    >>> apdu_ack_is_ok(0x81)
    False
    """
    return apdu_ack(head) == ApduAck.OK


def apdu_is_set(head: int) -> bool:
    """True when a request APDU head asks for a SET."""
    return apdu_op(head) == ApduOp.SET


def ack_name(head: int) -> str:
    """
    Human-readable name for a reply's acknowledgement bits.

    Used in log lines about refusals, where "the pump said no, and here is
    which no" is the whole diagnostic value.

    Examples
    --------
    >>> ack_name(0x81)
    'Unknown Data Item'
    """
    return {
        ApduAck.OK: "OK",
        ApduAck.UNKNOWN_CLASS: "Unknown Class",
        ApduAck.UNKNOWN_DATA_ITEM: "Unknown Data Item",
        ApduAck.ILLEGAL_OPERATION: "Illegal Operation",
    }[ApduAck(apdu_ack(head))]


class Class10Ack(IntEnum):
    """
    The *second* acknowledgement, carried inside a Class 10 reply's payload.

    The APDU head says whether the pump understood the request; this says
    whether it could carry it out. Both have to be right. The values come
    from ``GeniAPDU.CLASS10_ACK_*`` in the decompiled Grundfos GO app and
    appear in neither the GENIbus application manual nor the public
    ``christoph2/GENIBus`` reference.

    The capture corpus holds 222 short Class 10 replies: 195 OK, 18 BUSY
    and 9 OPERATION_FAILED, no fourth value, every one with the head ack
    OK. They are request-consistent - Object 202 Sub 100 answers BUSY every
    time, Sub 200 answers OPERATION_FAILED every time.
    """

    OK = 0
    BUSY = 2
    OPERATION_FAILED = 4


#: Shortest Class 10 reply that really carries the second acknowledgement:
#: ``24 05 F8 E7 0A 01 PL CRC CRC``.
#:
#: The bound is load-bearing rather than defensive. At ``len >= 7`` an
#: eight-byte CRC-valid frame declaring one payload byte puts the **CRC
#: high byte** at ``data[6]`` - and that byte would then decide a write's
#: verdict.
MIN_CLASS10_ACK_LENGTH = 9


def class10_reply_is_ok(frame: bytes) -> bool:
    """
    Whether a short Class 10 reply reports success on *both* acknowledgements.

    The payload byte is only a status when the head ack is OK. On a refusal
    that same byte is the offending Data Item's ID, so reading it as a
    status would turn "unknown item 0" into "operation succeeded".

    Examples
    --------
    >>> class10_reply_is_ok(bytes.fromhex("2405f8e70a0100aea2"))
    True
    >>> class10_reply_is_ok(bytes.fromhex("2405f8e70a0102aea2"))
    False
    """
    if len(frame) < 6:
        return False
    head = frame[5]
    if not apdu_ack_is_ok(head):
        return False
    if apdu_payload_len(head) == 0 or len(frame) < MIN_CLASS10_ACK_LENGTH:
        return True
    return frame[6] == Class10Ack.OK
