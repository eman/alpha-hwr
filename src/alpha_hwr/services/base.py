"""
Base service class with shared protocol helpers.

All services should inherit from BaseService to avoid code duplication.
Provides common methods for:
- Reading Class 10 objects
- Reading Class 7 strings
- Building GENI packets
- CRC calculation
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..exceptions import READ_ERRORS, ConnectionError
from ..protocol.frame_builder import FrameBuilder
from ..protocol.matcher import Command, read_command

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport

logger = logging.getLogger(__name__)


class BaseService:
    """
    Base class for all pump services.

    Provides shared protocol helpers to avoid code duplication across services.
    All service classes should inherit from this base class.

    Attributes:
        transport: BLE transport layer for packet I/O
        session: Session manager for authentication state
    """

    def __init__(self, transport: Transport, session: Session):
        """
        Initialize base service.

        Args:
            transport: BLE transport layer
            session: Session manager
        """
        self.transport = transport
        self.session = session

    async def _read_class10_object(
        self,
        obj_id: int,
        sub_id: int,
        retries: int = 1,
        retry_delay: float = 0.2,
    ) -> bytes | None:
        """
        Read a Class 10 (Configuration) object with SubID.

        This is the standard method for reading configuration and status data
        from the pump using the Class 10 DataObject protocol.

        Args:
            obj_id: Object ID (0-255)
            sub_id: Sub-ID (0-65535)
            retries: Number of attempts before giving up (default 1, i.e.
                no retry). Some object/sub-ID pairs are read in bulk over a
                known range where a missing response legitimately means "no
                data" (e.g. an empty event-log slot or an unsupported trend
                series), so retries must stay opt-in rather than automatic.
                Pass a higher value for one-off status reads (such as the
                control mode query right after authentication) where the
                pump may briefly be unresponsive while it finishes settling
                and a missing response really does mean "try again".
            retry_delay: Delay in seconds between attempts.

        Returns:
            Data bytes (payload only, without frame header/CRC), or None if read failed

        Raises:
            ConnectionError: If the BLE connection to the pump is found to
                have dropped while waiting for a response. This is
                distinct from a plain timeout (which returns None) because
                a lost connection means every subsequent read will fail
                the same way, so callers should stop and surface a clear
                error instead of reporting "no data".

        Example:
            >>> data = await self._read_class10_object(93, 1)  # Read statistics
            >>> data = await self._read_class10_object(86, 6)  # Read control mode

        Implementation Notes:
            - Builds APDU: [0x0A][0x03][ObjID][SubID_H][SubID_L]
            - OpSpec 0x03 = INFO (read operation)
            - Response format: [STX][LEN][DST][SRC][0x0A][OpSpec][Obj][SubH][SubL][...DATA...][CRC]
            - Returns DATA portion only (bytes 10 to -2)
        """
        try:
            frame = FrameBuilder.build_class10_object_read(obj_id, sub_id)

            # The pump does not echo the identifiers it was asked for; it
            # answers with a type code that depends on the object. Those
            # were measured per object, so the reply can be matched exactly
            # where the object is known and by class alone where it is not.
            command = read_command(obj_id, sub_id)

            for attempt in range(1, retries + 1):
                logger.debug(
                    f"Reading Class 10 Object {obj_id} SubID {sub_id} "
                    f"(attempt {attempt}/{retries})"
                )

                response = await self.transport.send_command(
                    frame,
                    command,
                    timeout=3.0,
                )

                if response and len(response) > 12:
                    # Extract data: skip frame header (10 bytes) and CRC (2 bytes)
                    # Frame structure: [STX][LEN][DST][SRC][Class][OpSpec][ObjH][ObjL][SubH][SubL][DATA...][CRC_H][CRC_L]
                    payload = response[10:-2]
                    logger.debug(
                        f"Read Object {obj_id}/{sub_id}: {len(payload)} bytes"
                    )
                    return payload

                logger.debug(
                    f"No response for Object {obj_id}/{sub_id} "
                    f"(attempt {attempt}/{retries})"
                )

                if not self.transport.is_connected():
                    # The connection dropped out from under us. Every
                    # further attempt (and every other read on this
                    # session) will fail identically, so raise instead of
                    # quietly returning None - the caller needs to know
                    # this isn't "no data", it's a lost BLE link.
                    raise ConnectionError(
                        f"Pump disconnected from BLE while reading "
                        f"Object {obj_id}/{sub_id}"
                    )

                if attempt < retries:
                    # The pump's GENI controller may be asleep (common right
                    # after authentication or after an idle period). Wake it
                    # with a keep-alive burst before retrying instead of
                    # just re-sending the same request, since a bare retry
                    # can otherwise trip a full BLE disconnect on some
                    # platforms. See docs/protocol/ble_architecture.md.
                    await self.transport.send_wake_burst()
                    if retry_delay > 0:
                        await asyncio.sleep(retry_delay)

            return None

        except ConnectionError:
            # Let disconnect errors propagate - see docstring above.
            raise

        except READ_ERRORS as e:
            # A dropped link can also surface as a transport error rather
            # than an unanswered read (e.g. BleakError out of
            # write_gatt_char). That is still a disconnect, not "no data",
            # so it gets the same treatment as the branch above.
            if not self.transport.is_connected():
                raise ConnectionError(
                    f"Pump disconnected from BLE while reading "
                    f"Object {obj_id}/{sub_id}"
                ) from e
            logger.debug(f"Error reading Object {obj_id} SubID {sub_id}: {e}")
            return None

    async def _read_class7_string(
        self,
        string_id: int,
        retries: int = 1,
        retry_delay: float = 0.2,
    ) -> str | None:
        """
        Read a Class 7 string (device info strings).

        Class 7 is used for reading device identification strings like
        serial numbers, software versions, hardware versions, etc.

        Args:
            string_id: String ID to read
            retries: Number of attempts before giving up (default 1, i.e.
                no retry). Pass a higher value for critical reads where a
                missing response likely means the pump hasn't finished
                settling yet rather than "this string does not exist".
            retry_delay: Delay in seconds between attempts.

        Returns:
            String value, or None if read failed

        Example:
            >>> serial = await self._read_class7_string(1)  # Serial number
            >>> sw_ver = await self._read_class7_string(2)  # Software version

        Implementation Notes:
            - APDU: [0x07][0x01][StringID]
            - Response: [STX][LEN][DST][SRC][0x07][Count][...STRING...][CRC]
            - ``Count`` is the string's byte length, and the first
              character is at offset 6. The reply does not echo the
              string ID that was requested.
            - String is UTF-8 encoded with null terminators
        """
        try:
            # Build APDU: [Class][Cmd][StringID]
            apdu = bytes([0x07, 0x01, string_id])  # Class 7, ReadString

            # Build GENI frame
            frame = self._build_geni_packet(0xF8, 0xE7, apdu)

            # Class 7 replies carry no Object/Sub identifiers, so the class
            # byte is all there is to match on. Gating on the class keeps a
            # Class 10 telemetry notification arriving first from being
            # mistaken for the string.
            command = Command(
                expect_class=0x07,
                description=f"read of string {string_id}",
            )

            for attempt in range(1, retries + 1):
                response = await self.transport.send_command(
                    frame,
                    command,
                    timeout=3.0,
                )

                if response and len(response) > 8:
                    # The header is six bytes, not seven. Byte 5 is the
                    # string's byte count - an APDU head like any other -
                    # and the text starts at offset 6.
                    #
                    # Reading from offset 7 dropped the first character of
                    # every string this pump returns. It was invisible
                    # because the two most-read strings were patched up
                    # afterwards: "LPHA HWR" had an "A" prepended, and a
                    # serial reading "0000479" had a "1" prepended. The
                    # second is a coincidence - correct for a serial
                    # beginning "10", corrupting one beginning "20" - and
                    # the version strings, which had no such patch, shipped
                    # a character short. Verified 2026-08-20: the pump
                    # answers 24 0E F8 E7 07 0A 41 4C 50 48 41 ... where
                    # 0x0A is the ten bytes of "ALPHA HWR\0" and 0x41 is
                    # the "A".
                    declared = response[5]
                    string_data = response[6:-2]
                    if declared != len(string_data):
                        # Do not trust the count to bound the read - it is
                        # radio-supplied, and believing it would let a
                        # corrupt byte walk off the end. Just say so.
                        logger.debug(
                            f"String {string_id} declares {declared} bytes "
                            f"but the frame carries {len(string_data)}"
                        )
                    logger.debug(
                        f"Raw string data for ID {string_id}: {string_data.hex()}"
                    )
                    # Decode as UTF-8, strip null terminators and whitespace
                    string_value = (
                        string_data.decode("utf-8", errors="ignore")
                        .rstrip("\x00")
                        .strip()
                    )
                    return string_value if string_value else None

                logger.debug(
                    f"No response for string {string_id} "
                    f"(attempt {attempt}/{retries})"
                )
                if attempt < retries:
                    # See _read_class10_object for why we wake the GENI
                    # controller before retrying instead of just resending.
                    await self.transport.send_wake_burst()
                    if retry_delay > 0:
                        await asyncio.sleep(retry_delay)

            return None

        except READ_ERRORS as e:
            logger.debug(f"Failed to read Class 7 string {string_id}: {e}")
            return None

    def _build_geni_packet(
        self, source: int, service_id: int, apdu: bytes
    ) -> bytes:
        """
        Build a GENI protocol packet with CRC.

        Constructs a complete GENI frame with proper header and CRC trailer.

        Args:
            source: Source address (typically 0xF8)
            service_id: Service ID (typically 0xE7 for commands)
            apdu: Application Protocol Data Unit (command payload)

        Returns:
            Complete GENI packet with CRC

        Example:
            >>> apdu = bytes([0x0A, 0x03, 93, 0x00, 0x01])  # Class 10 read
            >>> packet = self._build_geni_packet(0xF8, 0xE7, apdu)

        Implementation Notes:
            - Frame format: [STX][LEN][ServiceID][Source][APDU][CRC_H][CRC_L]
            - STX = 0x27 (start of frame marker)
            - LEN = length of ServiceID + Source + APDU
            - CRC-16-CCITT over [LEN][ServiceID][Source][APDU]
        """
        return FrameBuilder.build_geni_frame(
            apdu, source=source, service_id=service_id
        )

    #: Byte 5 of ClockProgramOverview: what the pump does outside every
    #: scheduled window. The Grundfos app always writes Stop here.
    DEFAULT_ACTION_STOP = 0x01

    #: Length of the ClockProgramOverview structure.
    OVERVIEW_LEN = 10

    async def _send_configuration_commit(self) -> bool:
        """
        Flush pending configuration to the pump's non-volatile memory.

        The commit carries the whole ClockProgramOverview - the schedule's
        enabled flag among it - so it can only be built from what the pump
        currently holds. It used to send a fixed constant whose
        ``clock_program_enabled`` byte was ``0x00``, and because a commit
        follows every setpoint write and control request, changing any
        setpoint silently switched the user's schedule off.

        If the overview cannot be read, no commit is sent: skipping a flush
        is recoverable, writing a fabricated schedule state over the real
        one is not.

        Returns:
            True if the commit was sent.
        """
        overview = await self._read_class10_object(84, 1)
        if not overview or len(overview) < 3 + self.OVERVIEW_LEN:
            logger.warning(
                "Skipping configuration commit: the schedule overview could "
                "not be read, and committing without it would overwrite the "
                "pump's schedule state"
            )
            return False

        # Skip the 3-byte header to get the structure itself.
        structure = bytearray(overview[3 : 3 + self.OVERVIEW_LEN])
        structure[5] = self.DEFAULT_ACTION_STOP

        apdu = bytearray(
            [
                0x0A,  # Class 10
                0x93,  # OpSpec: SET + 19 bytes
                0x54,  # Object 84
                0x00,
                0x01,  # Sub-ID 1
                0x00,
                0xDA,
                0x01,  # Type 218 (ClockProgramOverview)
                0x00,
                0x00,
                self.OVERVIEW_LEN,
            ]
        )
        apdu.extend(structure)

        await self.transport.write(
            self._build_geni_packet(0xF8, 0xE7, bytes(apdu))
        )
        return True
