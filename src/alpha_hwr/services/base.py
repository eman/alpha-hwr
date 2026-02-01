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

import logging
from typing import TYPE_CHECKING, Optional

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
        self, obj_id: int, sub_id: int
    ) -> Optional[bytes]:
        """
        Read a Class 10 (Configuration) object with SubID.

        This is the standard method for reading configuration and status data
        from the pump using the Class 10 DataObject protocol.

        Args:
            obj_id: Object ID (0-255)
            sub_id: Sub-ID (0-65535)

        Returns:
            Data bytes (payload only, without frame header/CRC), or None if read failed

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
            from ..utils import calc_crc16_read

            # Build APDU: [Class][OpSpec][ObjID][SubID_H][SubID_L]
            apdu = bytes(
                [
                    0x0A,  # Class 10 (Configuration/DataObject)
                    0x03,  # OpSpec INFO (read)
                    obj_id & 0xFF,  # Object ID (1 byte)
                    (sub_id >> 8) & 0xFF,  # Sub-ID high byte
                    sub_id & 0xFF,  # Sub-ID low byte
                ]
            )

            # Build full GENI frame with CRC
            length = 1 + 1 + len(apdu)  # Dst + Src + APDU
            frame_without_crc = bytes([0x27, length, 0xE7, 0xF8]) + apdu
            crc = calc_crc16_read(frame_without_crc[1:])
            frame = frame_without_crc + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

            logger.debug(f"Reading Class 10 Object {obj_id} SubID {sub_id}")

            def match_class10_response(p: bytes) -> bool:
                """Match Class 10 response packet."""
                return len(p) > 6 and p[4] == 0x0A

            response = await self.transport.query(
                frame,
                match_func=match_class10_response,
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

            logger.debug(f"No response for Object {obj_id}/{sub_id}")
            return None

        except Exception as e:
            logger.debug(f"Error reading Object {obj_id} SubID {sub_id}: {e}")
            return None

    async def _read_class7_string(self, string_id: int) -> Optional[str]:
        """
        Read a Class 7 string (device info strings).

        Class 7 is used for reading device identification strings like
        serial numbers, software versions, hardware versions, etc.

        Args:
            string_id: String ID to read

        Returns:
            String value, or None if read failed

        Example:
            >>> serial = await self._read_class7_string(1)  # Serial number
            >>> sw_ver = await self._read_class7_string(2)  # Software version

        Implementation Notes:
            - APDU: [0x07][0x01][StringID]
            - Response: [STX][LEN][DST][SRC][0x07][Cmd][ID][...STRING...][CRC]
            - String is UTF-8 encoded with null terminators
        """
        try:

            # Build APDU: [Class][Cmd][StringID]
            apdu = bytes([0x07, 0x01, string_id])  # Class 7, ReadString

            # Build GENI frame
            frame = self._build_geni_packet(0xF8, 0xE7, apdu)

            def match_class7(p: bytes) -> bool:
                """Match Class 7 response."""
                return len(p) > 6 and p[4] == 0x07

            response = await self.transport.query(
                frame,
                match_func=match_class7,
                timeout=3.0,
            )

            if response and len(response) > 9:
                # Extract string data: skip frame header (7 bytes) and CRC (2 bytes)
                # Frame: [STX][LEN][DST][SRC][Class][Cmd][ID][...STRING...][CRC_H][CRC_L]
                string_data = response[7:-2]
                logger.debug(f"Raw string data for ID {string_id}: {string_data.hex()}")
                # Decode as UTF-8, strip null terminators and whitespace
                string_value = (
                    string_data.decode("utf-8", errors="ignore")
                    .rstrip("\x00")
                    .strip()
                )
                return string_value if string_value else None

            return None

        except Exception as e:
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
        from ..utils import calc_crc16_read

        length = 1 + 1 + len(apdu)  # ServiceID + Source + APDU
        frame_without_crc = bytes([0x27, length, service_id, source]) + apdu
        crc = calc_crc16_read(frame_without_crc[1:])
        frame = frame_without_crc + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

        return frame
