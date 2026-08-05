"""
Deciding whether a notification answers an outstanding command.

GENIbus carries no transaction id, so a reply is matched positionally
against the command still in flight. What makes that non-trivial is the
pump's firmware: it answers with a different Sub-ID than was asked for,
puts the identifier fields in different places depending on the operation
specifier, and acknowledges some writes with a frame far shorter than a
normal response.

The rules below are the pump's observed behaviour rather than anything
the protocol promises. They mirror the C++ port's ``try_dispatch_response``
(``components/alpha_hwr/transport.cpp``), which is the version currently
validated against hardware.

Frame layout (see ``frame_parser``)::

    [0] start (0x24 response, 0x27 request/echo)
    [1] length
    [2] service id (0xE7)
    [3] source address (0xF8)
    [4] class
    [5] operation specifier
    [6:8] identifier field A
    [8:10] identifier field B

Whether field A holds the Object ID or the Sub-ID depends on the operation
specifier, and the pump is not consistent about it - so a command declares
which values it expects and a match is accepted with the two fields in
either order. Naming them A and B rather than guessing keeps the ambiguity
visible instead of encoding a claim the traffic does not support.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..constants import CLASS_10, RESPONSE_START

#: Classes whose acknowledgement is a bare frame with no identifier
#: fields: the pump replies ``[class, 0x00]`` for a command it executed
#: and ``[class, 0x01, ...]`` for one it only described (see the remote
#: mode opcode investigation, esphome #46). These are as short as 8 bytes,
#: below the length a normal response needs.
SHORT_ACK_CLASSES = (0x03, 0x07)

#: Shortest frame that can carry identifier fields at bytes 6-9.
MIN_IDENTIFIED_LENGTH = 12

#: Shortest frame worth looking at at all.
MIN_FRAME_LENGTH = 6

#: Type codes the pump answers with, per object it was asked for.
#:
#: Measured against an ALPHA HWR on 2026-08-04 by reading each object and
#: recording the reply's identifier fields; every object answered with one
#: frame and the values were identical across two runs. Ranges were checked
#: at both ends (schedule layers 0/1/4, event log entries 0/1/19, trends
#: 451-454) rather than extrapolated - which is how the power-on-time trend
#: turned out to use a different type from the other three.
#:
#: This is the reliable way to tell a solicited reply from the pump's
#: notification stream. Matching on the frame's second byte is not: see
#: RESPONSE_LENGTH_IS_BYTE_5 below.
RESPONSE_IDENTIFIERS: dict[tuple[int, range], tuple[int, int]] = {
    (86, range(5, 11)): (0x0001, 0x2F01),  # operation status request
    (86, range(13, 40)): (0x0001, 0x2D01),  # setpoint limits
    (91, range(421, 422)): (0x0003, 0xD901),  # DHW / cycle-time config
    (91, range(430, 431)): (0x0003, 0xF402),  # temperature range config
    (84, range(1, 2)): (0x0000, 0xDA01),  # schedule overview
    (84, range(900, 935)): (0x0000, 0xDC01),  # single events
    (84, range(1000, 1005)): (0x0000, 0xDE01),  # schedule layers
    (93, range(1, 2)): (0x0000, 0xF802),  # operating statistics
    (94, range(101, 102)): (0x0001, 0x4201),  # clock
    (88, range(10199, 10200)): (0x0000, 0xF301),  # event log metadata
    (88, range(10200, 10220)): (0x0000, 0xF402),  # event log entries
    (88, range(13300, 13302)): (0x0003, 0xE801),  # cycle timestamps
    (53, range(451, 454)): (0x0003, 0xB201),  # trends: flow, head, temp
    (53, range(454, 455)): (0x0003, 0xB301),  # trend: power-on time
}

#: In a *response*, byte 5 is a length field, not an operation specifier.
#:
#: Measured across 13 objects and 10 distinct values: the top two bits (the
#: operation code) are always 00, the low six bits equal the payload length
#: exactly, and both `len(frame) == (byte5 & 0x3F) + 8` and
#: `frame[1] == (byte5 & 0x3F) + 4` hold without exception.
#:
#: This matters because it invalidates an inherited filter. The set
#: `{0x30, 0x2B, 0x14, 0x2E, 0x2D, 0x09}`, carried over as "register-read
#: operation specifiers", is really the payload sizes 48, 43, 20, 46, 45
#: and 9 - so rejecting those replies rejected by *length*, which is why the
#: event log (a 20-byte payload) had to be exempted from it by hand. Match
#: on RESPONSE_IDENTIFIERS instead.
RESPONSE_LENGTH_IS_BYTE_5 = True

#: Operation specifiers a Class 10 *write* is acknowledged with. The ack
#: carries no identifiers, so it can only be attributed to the command in
#: flight - which is why a command has to opt in via
#: :attr:`Command.expect_short_ack`.
SHORT_ACK_OPSPECS = frozenset({0x01, 0x81})


@dataclass(frozen=True)
class Command:
    """
    What a caller is waiting for.

    Attributes
    ----------
    expect_a, expect_b:
        Identifier values expected at bytes 6-7 and 8-9. Both zero means
        "any response of the right class" - used where the pump answers
        with identifiers that match nothing that was sent.
    expect_class:
        GENI class of the request. A short acknowledgement is only ever
        attributed to a command of the same class, so an unrelated
        telemetry notification arriving first cannot be mistaken for it.
    expect_short_ack:
        Accept a Class 10 write acknowledgement (OpSpec 0x01/0x81), which
        carries no identifiers.
    quiet_timeout:
        This command is expected to go unanswered - the pump commits some
        writes only after the response window has closed. A timeout is
        normal operation, not a fault, and callers should not log it as
        one. Purely advisory; it does not affect matching.
    accept_opspecs:
        When set, only these operation specifiers may answer. Use where
        the reply is identified by what kind of message it is rather than
        by any identifier it carries - a write acknowledgement, say.
    reject_opspecs:
        Operation specifiers that never answer this command, whatever
        else matches. Telemetry reads use this to turn away the pump's
        unsolicited notification stream, which shares their class.
    """

    expect_a: int = 0
    expect_b: int = 0
    expect_class: int = CLASS_10
    expect_short_ack: bool = False
    quiet_timeout: bool = False
    accept_opspecs: frozenset[int] | None = None
    reject_opspecs: frozenset[int] = frozenset()
    description: str = field(default="", compare=False)

    @property
    def is_wildcard(self) -> bool:
        """True when any response of the right class will do."""
        return self.expect_a == 0 and self.expect_b == 0

    @classmethod
    def for_request(cls, request: bytes, **kwargs: object) -> Command:
        """
        Build a command whose expected class is taken from the request.

        A reply is only ever attributed to a request of the same class, so
        deriving it from the frame about to be sent removes the chance of
        the two disagreeing. Everything else is passed through.

        Parameters
        ----------
        request:
            The frame being sent.
        **kwargs:
            Any other :class:`Command` field.

        Examples
        --------
        >>> frame = bytes([0x27, 0x05, 0xE7, 0xF8, 0x03, 0x81, 0x06, 0, 0])
        >>> Command.for_request(frame).expect_class
        3
        """
        sent_class = frame_class(request)
        return cls(
            expect_class=CLASS_10 if sent_class is None else sent_class,
            **kwargs,  # type: ignore[arg-type]
        )


def frame_class(packet: bytes) -> int | None:
    """Class byte of a frame, or None if it is too short to have one."""
    if len(packet) < MIN_FRAME_LENGTH:
        return None
    return packet[4]


def frame_opspec(packet: bytes) -> int | None:
    """Operation specifier of a frame, or None if it is too short."""
    if len(packet) < MIN_FRAME_LENGTH:
        return None
    return packet[5]


def frame_identifiers(packet: bytes) -> tuple[int, int] | None:
    """
    Identifier fields at bytes 6-7 and 8-9, or None if absent.

    Returned in wire order. Which one is the Object ID and which the
    Sub-ID depends on the operation specifier - see the module docstring.
    """
    if len(packet) < MIN_IDENTIFIED_LENGTH:
        return None
    return (
        (packet[6] << 8) | packet[7],
        (packet[8] << 8) | packet[9],
    )


def is_short_ack(packet: bytes) -> bool:
    """
    True for a bare Class 3/7 acknowledgement.

    These are shorter than an identified response and carry only an
    outcome byte.
    """
    cls = frame_class(packet)
    return cls in SHORT_ACK_CLASSES and len(packet) < MIN_IDENTIFIED_LENGTH


def short_ack_accepted(packet: bytes) -> bool | None:
    """
    Whether a short acknowledgement reports success.

    ``[03 00]`` (no data bytes) is a clean execution ack; ``[03 01 xx]``
    is a descriptor-only reply, meaning the pump described the data item
    instead of acting on it. Returns None when the frame is not a short
    acknowledgement.
    """
    if not is_short_ack(packet) or len(packet) < MIN_FRAME_LENGTH:
        return None
    return packet[5] == 0x00


def matches(command: Command, packet: bytes) -> bool:
    """
    Decide whether ``packet`` answers ``command``.

    Parameters
    ----------
    command:
        What the caller is waiting for.
    packet:
        A fully reassembled frame.

    Returns
    -------
    bool
        True if the frame should be delivered to the waiting caller.
        False leaves it for the telemetry path.
    """
    cls = frame_class(packet)
    if cls is None:
        return False

    # A short Class 3/7 ack carries nothing to match on but its class, so
    # it is only ever attributed to a command sent as that same class.
    if is_short_ack(packet):
        return cls == command.expect_class

    if cls != command.expect_class:
        return False

    opspec = frame_opspec(packet)

    if opspec in command.reject_opspecs:
        return False

    if command.accept_opspecs is not None:
        return opspec in command.accept_opspecs

    # A Class 10 write ack has no identifiers either. Only a command that
    # said it was a write may claim one. The pump also answers a read of an
    # object that does not exist with this shape - an empty single-event
    # slot comes back as [0A 01 04] - so a read that accepted it would take
    # an error for data.
    if (
        cls == CLASS_10
        and opspec in SHORT_ACK_OPSPECS
        and len(packet) < MIN_IDENTIFIED_LENGTH
    ):
        return command.expect_short_ack

    if command.is_wildcard:
        return True

    identifiers = frame_identifiers(packet)
    if identifiers is None:
        return False

    a, b = identifiers
    if (a, b) == (command.expect_a, command.expect_b):
        return True

    # The pump does not place the two identifiers consistently, so accept
    # them the other way round as well. This is the only reason several
    # reads work at all - the Object 86 status read included, whose reply
    # is a passive notification carrying identifiers unrelated to the
    # request.
    # There is deliberately no "one field came back zero, so match on the
    # other" rule here. It was inherited as a firmware quirk, but the pump
    # never actually echoes the Sub-ID it was asked for - it answers with a
    # type code, and a zero in the first field is that object's real value
    # rather than a wildcard. Treating it as one is not merely redundant, it
    # is wrong: the temperature-range config (0x0003, 0xF402) and an event
    # log entry (0x0000, 0xF402) share a type code and differ only in the
    # field the rule discarded, so each would answer the other's read.
    return (b, a) == (command.expect_a, command.expect_b)


def is_response(packet: bytes) -> bool:
    """True for a frame the pump sent us (as opposed to an echo)."""
    return len(packet) > 0 and packet[0] == RESPONSE_START


def expected_reply(obj_id: int, sub_id: int) -> tuple[int, int] | None:
    """
    Identifiers the pump answers a read of this object with.

    Returns None for an object that has not been measured, in which case
    the caller should fall back to matching on the class alone rather than
    guessing - a wrong expectation rejects the real reply, which is worse
    than a loose one.

    Examples
    --------
    >>> expected_reply(86, 7)
    (1, 12033)
    >>> expected_reply(999, 1) is None
    True
    """
    for (obj, subs), identifiers in RESPONSE_IDENTIFIERS.items():
        if obj == obj_id and sub_id in subs:
            return identifiers
    return None


def read_command(obj_id: int, sub_id: int) -> Command:
    """
    Build the command for reading one Class 10 object.

    Uses the measured reply identifiers where they are known so the pump's
    notification stream cannot be mistaken for the answer, and falls back
    to a class-level match otherwise.
    """
    identifiers = expected_reply(obj_id, sub_id)
    a, b = identifiers if identifiers else (0, 0)
    return Command(
        expect_a=a,
        expect_b=b,
        description=f"read of Object {obj_id}/{sub_id}",
    )
