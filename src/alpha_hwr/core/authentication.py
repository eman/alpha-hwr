"""
Opening a session with the pump.

There is no authentication handshake, and this module no longer sends one.

Ten packets used to go out here, documented as a three-stage unlock: a
"Class 2 SET of unlock register 0x9495 carrying unlock code 0x96", a
"Class 10 unlock", and two "extension" packets. Decoded properly, the
``0x03`` in the first is an APDU head - a GET declaring three payload bytes
- so "register 0x9495, unlock code 0x96" was a misreading of a length
field. All four distinct packets are **reads**:

* a Class 2 GET of ``unit_family`` / ``unit_type`` / ``unit_version``,
  which this pump answers 52 / 7 / 2 - the same values it puts in its
  advertisement;
* a Class 10 GET of Object 86 Sub 6, the operation status the telemetry
  path already decodes;
* two INFO queries for scaling metadata, both answered "unscaled".

A read cannot change device state, so an unlock was never something these
bytes could do - and every reply was discarded unread in any case.

Measured 2026-08-20: with none of them sent, a bare connect-subscribe link
answered all five Class 7 string reads, every Class 10 object read this
client makes, and the telemetry registers. ``docs/protocol/connection.md``
reached the same conclusion from the captures; this is that conclusion
applied to the code.

The 750 ms of inter-stage delays went with them. They were transcribed
from an early version of this client's own ``sleep()`` calls and then
written up as pump timing requirements; nothing ever measured them.

What remains is the settle wait before the first command, which is about
the BLE link coming up rather than about GENI.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from ..exceptions import READ_ERRORS

logger = logging.getLogger(__name__)

#: How long to let the BLE link settle before the first command.
#:
#: This is the one wait that survived the handshake's removal, and it is
#: about the radio rather than about GENI. The 750 ms of inter-stage delays
#: that used to sit alongside it were transcribed from this client's own
#: sleep() calls and then documented as pump timing requirements; nothing
#: ever measured them.
STABILIZE_DELAY = 0.5


@runtime_checkable
class BLEWriter(Protocol):
    """Protocol for BLE characteristic write operations."""

    async def write_gatt_char(
        self,
        char_specifier: str,
        data: bytes,
        response: bool | None = None,
    ) -> None:
        """Write data to a GATT characteristic."""
        ...


class AuthenticationHandler:
    """
    Handles GENI authentication handshake for ALPHA HWR pumps.

    The authentication sequence follows the established protocol requirements
    for ALPHA HWR devices. It uses a combination of legacy (Class 2/3) and modern
    (Class 10) protocol operations to unlock the pump for remote control.

    Packet Breakdown
    ----------------
    All packets follow the GENI frame format:

    [Start] [Length] [ServiceID] [Source] [APDU...] [CRC-H] [CRC-L]

    Where:
    - Start: 0x27 (FRAME_START)
    - Length: Number of bytes following (excluding CRC)
    - ServiceID: 0xE7 (high byte), 0xF8 (low byte) - GENI service
    - Source: 0xF8 (default) or 0x0A (alternative addressing)
    - APDU: Application Protocol Data Unit (class, opspec, data)
    - CRC: CRC-16-CCITT over bytes from Length to end of APDU

    Example: Legacy Magic Packet
    -----------------------------
    Hex: 27 07 E7 F8 02 03 94 95 96 EB 47

    Breakdown:
    - 27        : Frame start byte (FRAME_START)
    - 07        : Length (7 bytes after this)
    - E7 F8     : Service ID (0xE7F8 = GENI)
    - 02        : Class 2 (legacy register-based)
    - 03        : OpSpec (SET operation, 3 data bytes)
    - 94 95     : Register address 0x9495 (unlock command)
    - 96        : Data byte (unlock value)
    - EB 47     : CRC-16-CCITT checksum

    CRC Calculation:
    Input bytes: 07 E7 F8 02 03 94 95 96
    CRC-16-CCITT (poly=0x1021, init=0xFFFF): 0xEB47

    Attributes
    ----------
    LEGACY_MAGIC : bytes
        Legacy authentication packet (Class 2, Sub 0x9495)
    CLASS10_UNLOCK : bytes
        Primary unlock packet (Class 10, Sub 0x5600, Obj 0x0006)
    EXTEND_1, EXTEND_2 : bytes
        Extension packets to complete handshake (sent in order)

    Notes
    -----
    - The burst sending (5x repeats) ensures packet delivery over BLE
    - Timing delays are critical for pump processing
    - No ACK/NACK responses are sent - success is assumed
    - Some pumps may work with just CLASS10_UNLOCK, but full sequence
      ensures compatibility with all firmware versions
    """

    # ==========================================================================
    # LEGACY MAGIC PACKET (Class 2, Register-based SET)
    # ==========================================================================
    # Frame: 27 07 E7 F8 02 03 94 95 96 EB 47
    #
    # Purpose: Compatibility with nested proxy architecture in older firmware
    #
    # Breakdown:
    #   27          - Frame start
    #   07          - Length (7 bytes)
    #   E7 F8       - Service ID (GENI)
    #   02          - Class 2 (Register-based operations)
    #   03          - OpSpec: SET operation, 3 data bytes
    #               OpSpec format: [Op:2bits][Length:6bits]
    #               0x03 = 0b00000011 = Op:0 (SET), Length:3
    #   94 95       - Register address (2 bytes): 0x9495 (unlock register)
    #   96          - Data value: 0x96 (unlock code)
    #   EB 47       - CRC-16-CCITT
    #
    # CRC Calculation:
    #   Input:  07 E7 F8 02 03 94 95 96
    #   Poly:   0x1021 (CRC-16-CCITT)
    #   Init:   0xFFFF
    #   Result: 0xEB47
    #: A Class 2 GET of unit_family / unit_type / unit_version.
    #:
    #: Kept as a captured frame, not as something to send. It was called a
    #: "legacy magic" unlock and read as a SET of register 0x9495 carrying
    #: unlock code 0x96; byte 5 is 0x03, an APDU head declaring a GET with
    #: three payload bytes, and 94 95 96 are the three item IDs. This pump
    #: answers 52 / 7 / 2 - the same family, type and version it puts in
    #: its advertisement.
    LEGACY_MAGIC = bytes.fromhex("2707e7f80203949596eb47")

    # ==========================================================================
    # CLASS 10 UNLOCK PACKET (DataObject SET)
    # ==========================================================================
    # Frame: 27 07 E7 F8 0A 03 56 00 06 C5 5A
    #
    # Purpose: Primary authentication command for Class 10 protocol
    #
    # Breakdown:
    #   27          - Frame start
    #   07          - Length (7 bytes)
    #   E7 F8       - Service ID (GENI)
    #   0A          - Class 10 (DataObject operations)
    #   03          - OpSpec: SET operation
    #               For Class 10: OpSpec bit 7 set = SET (0x80)
    #               Length bits: 0x03 = 3 bytes follow
    #   56 00       - Sub-ID: 0x5600 (control/unlock subsystem)
    #   06          - Object ID: 0x0006 (unlock object)
    #   C5 5A       - CRC-16-CCITT
    #
    # Note: No data payload after Obj ID means this is a "trigger" operation
    #
    # CRC Calculation:
    #   Input:  07 E7 F8 0A 03 56 00 06
    #   Result: 0xC55A
    #: A Class 10 GET of Object 86 Sub 6 - the operation status the
    #: telemetry path already decodes. Not an unlock; a read.
    CLASS10_UNLOCK = bytes.fromhex("2707e7f80a03560006c55a")

    # ==========================================================================
    # EXTENSION PACKET 1
    # ==========================================================================
    # Frame: 27 05 E7 F8 05 C1 4B C3 82
    #
    # Purpose: Extend authentication session (Part 1)
    #
    # Breakdown:
    #   27          - Frame start
    #   05          - Length (5 bytes)
    #   E7 F8       - Service ID
    #   05          - Class 5 (extension protocol)
    #   C1 4B       - Command/data sequence
    #   C3 82       - CRC-16-CCITT
    #
    # Note: Must be sent before EXTEND_2. Order documented in
    # docs/protocol/connection.md Step C, observed from Grundfos app.
    #: An INFO query for scaling metadata on Class 5 item 0x4B. Answered
    #: "unscaled". Byte 5 is 0xC1: operation 0b11 (INFO), one payload byte.
    EXTEND_1 = bytes.fromhex("2705e7f805c14bc382")

    # ==========================================================================
    # EXTENSION PACKET 2
    # ==========================================================================
    # Frame: 27 05 E7 F8 0B C1 0F D0 C3
    #
    # Purpose: Extend authentication session (Part 2)
    #
    # Breakdown:
    #   27          - Frame start
    #   05          - Length (5 bytes)
    #   E7 F8       - Service ID
    #   0B          - Class 11 (session extension)
    #   C1 0F       - Command/data sequence
    #   D0 C3       - CRC-16-CCITT
    #: The same INFO query for Class 11 item 0x0F. Also "unscaled".
    EXTEND_2 = bytes.fromhex("2705e7f80bc10fd0c3")

    # GENI characteristic UUID (where packets are written)
    GENI_CHAR_UUID = "859cffd1-036e-432a-aa28-1a0085b87ba9"

    def __init__(
        self,
        ble_writer: BLEWriter,
        transaction: asyncio.Lock | None = None,
    ):
        """
        Initialize authentication handler.

        Parameters
        ----------
        ble_writer : BLEWriter
            BLE client capable of writing to GATT characteristics.
            Must implement write_gatt_char() method.
        transaction : asyncio.Lock, optional
            The transport's transaction lock. When supplied, the whole
            handshake is held under it so no other traffic (a telemetry
            query, a keep-alive burst) can interleave with the packet
            sequence. The pump drops the link when the handshake is
            disturbed, so this is not merely tidiness - see issue #31.

        Examples
        --------
        >>> from bleak import BleakClient
        >>> client = BleakClient("device_address")
        >>> await client.connect()
        >>> auth = AuthenticationHandler(client)
        >>> await auth.authenticate()
        """
        self.ble_writer = ble_writer
        self._transaction = transaction

    @contextlib.asynccontextmanager
    async def _exclusive(self) -> AsyncIterator[None]:
        """Hold the transport transaction lock, if one was supplied."""
        if self._transaction is None:
            yield
            return
        async with self._transaction:
            yield

    async def authenticate(self, fast_mode: bool = False) -> bool:
        """
        Settle the link so the first command is not sent into a dead radio.

        Nothing is sent to the pump. The opening sequence this used to
        write was ten packets of reads whose replies were discarded - see
        the module docstring - and removing it took connect-to-first-answer
        down by the time those packets and their 750 ms of delays took.

        The name is kept because callers and `client.authenticate()` use
        it, and because the session still has a state to move through.

        Args:
            fast_mode: Skip the settle wait. For tests.

        Returns:
            True. There is no handshake to fail; a pump that will not
            answer shows up as an unanswered read, which is where it can
            actually be diagnosed.
        """
        logger.debug("Opening a session (no handshake is sent)")

        try:
            async with self._exclusive():
                if not fast_mode:
                    await asyncio.sleep(STABILIZE_DELAY)
        except READ_ERRORS as e:
            logger.error(f"Failed to settle the link: {e}")
            return False

        return True
