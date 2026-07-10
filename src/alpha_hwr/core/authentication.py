"""
Authentication module for Grundfos ALPHA HWR pumps.

This module implements the multi-stage authentication handshake required
to establish a trusted connection with the pump. The handshake consists
of three stages:

1. Legacy Magic Packet (compatibility with nested proxies)
2. Class 10 Unlock Sequence (primary authentication)
3. Extension Packets (handshake completion)

Protocol Reference
------------------
The authentication uses the GENI protocol's Class 10 DataObject operations
and legacy Class 2/3 commands. All packets use CRC-16-CCITT for integrity.

For implementation in other languages, follow these steps:
1. Implement CRC-16-CCITT calculation (polynomial 0x1021, init 0xFFFF)
2. Build packets as shown in the constants below
3. Send in the specified sequence with timing delays
4. No response validation is needed - success is implicit

See Also
--------
docs/protocol/authentication.md : Detailed protocol documentation
docs/protocol/packet_traces/02_authentication.md : Packet capture examples
"""

import asyncio
import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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
    EXTEND_2 = bytes.fromhex("2705e7f80bc10fd0c3")

    # GENI characteristic UUID (where packets are written)
    GENI_CHAR_UUID = "859cffd1-036e-432a-aa28-1a0085b87ba9"

    def __init__(self, ble_writer: BLEWriter):
        """
        Initialize authentication handler.

        Parameters
        ----------
        ble_writer : BLEWriter
            BLE client capable of writing to GATT characteristics.
            Must implement write_gatt_char() method.

        Examples
        --------
        >>> from bleak import BleakClient
        >>> client = BleakClient("device_address")
        >>> await client.connect()
        >>> auth = AuthenticationHandler(client)
        >>> await auth.authenticate()
        """
        self.ble_writer = ble_writer

    async def authenticate(self, fast_mode: bool = False) -> bool:
        """
        Perform complete authentication handshake.

        This method executes the three-stage authentication sequence:
        1. Legacy magic burst (3x repeats, 50ms intervals)
        2. Class 10 unlock burst (5x repeats, 50ms intervals)
        3. Extension packets (EXTEND_1 then EXTEND_2, 50ms apart)

        Timing Considerations
        ---------------------
        - Inter-packet delay: 50ms (allows pump processing)
        - Stage delay: 100-200ms (allows stage completion)
        - Total sequence time: ~1 second

        Args:
            fast_mode: If True, skips all delays (inter-packet and
                inter-stage). Intended for unit tests only; do not use
                against real hardware as the pump requires the timing
                gaps to process each stage.

        Returns:
            bool
                True if authentication sequence completed without errors.
                Note: No explicit ACK is received, so True indicates the
                sequence was sent successfully, not that authentication
                was explicitly confirmed by the pump.
        """
        logger.info("Starting authentication handshake (3-stage sequence)...")

        try:
            # Stage 1: Legacy Magic Burst (backward compatibility)
            logger.debug("Stage 1: Sending legacy magic burst (3x repeats)...")
            await self.send_legacy_burst(repeats=3, delay=0 if fast_mode else 0.1)
            if fast_mode:
                # When resuming a session, usually only Stage 3 is strictly required
                # but we send all for robustness
                pass
            elif not fast_mode:
                await asyncio.sleep(0.1)  # Allow processing time

            # Stage 2: Class 10 Unlock (required for DataObjects)
            logger.debug("Stage 2: Sending Class 10 unlock burst (5x repeats)...")
            delay = 0 if fast_mode else 0.1
            for _ in range(5):
                await self.ble_writer.write_gatt_char(
                    self.GENI_CHAR_UUID, self.CLASS10_UNLOCK, response=False
                )
                if delay > 0:
                    await asyncio.sleep(delay)

            # Stage 3: Extension Packets (session establishment)
            logger.debug("Stage 3: Sending extension packets...")
            await self.send_extension_packets(delay=0 if fast_mode else 0.1)

            if not fast_mode:
                await asyncio.sleep(0.5)  # Final stabilization

            logger.info("Authentication handshake complete")
            return True

        except Exception as e:
            logger.error(f"Authentication handshake failed: {e}")
            return False

    async def send_legacy_burst(
        self, repeats: int = 7, delay: float = 0.05
    ) -> None:
        """
        Send legacy magic packet burst.

        Stage 1 of authentication. Sends legacy Class 2 unlock command
        multiple times to ensure compatibility with older firmware and
        nested proxy architectures.

        Parameters
        ----------
        repeats : int, default=3
            Number of times to send the packet. Default of 3 provides
            good reliability without excessive BLE traffic.
        delay : float, default=0.05
            Delay between packets in seconds.
        """
        async with asyncio.TaskGroup() as tg:
            for _ in range(repeats):
                tg.create_task(
                    self.ble_writer.write_gatt_char(
                        self.GENI_CHAR_UUID, self.LEGACY_MAGIC, response=False
                    )
                )
                if delay > 0:
                    await asyncio.sleep(delay)

    async def send_class10_burst(
        self, repeats: int = 5, delay: float = 0.05
    ) -> None:
        """
        Send Class 10 unlock burst.

        Stage 2 of authentication. Sends primary unlock command using
        modern Class 10 DataObject protocol. This is the critical
        authentication step.

        Parameters
        ----------
        repeats : int, default=5
            Number of times to send the packet. Default of 5 ensures
            reliable delivery even in noisy BLE environments.
        delay : float, default=0.05
            Delay between packets in seconds.
        """
        async with asyncio.TaskGroup() as tg:
            for _ in range(repeats):
                tg.create_task(
                    self.ble_writer.write_gatt_char(
                        self.GENI_CHAR_UUID, self.CLASS10_UNLOCK, response=False
                    )
                )
                if delay > 0:
                    await asyncio.sleep(delay)

    async def send_extension_packets(self, delay: float = 0.05) -> None:
        """
        Send authentication extension packets.

        Stage 3 of authentication. Sends two extension packets that
        complete the handshake and establish the session. These packets
        may negotiate capabilities or extend the authentication timeout.

        Parameters
        ----------
        delay : float, default=0.05
            Delay in seconds between EXTEND_1 and EXTEND_2. Required for
            the pump to process each packet before the next arrives.
            Pass 0 only in unit tests (via fast_mode=True on authenticate()).

        Notes
        -----
        - Packets MUST be sent sequentially: EXTEND_1 then EXTEND_2.
        - A 50ms gap between them is required for the pump to process
          EXTEND_1 before EXTEND_2 arrives. Sending them in parallel
          causes premature disconnection (issue #24).
        - Order is empirically established from packet captures; see
          docs/protocol/packet_traces/02_authentication.md.
        """
        await self.ble_writer.write_gatt_char(
            self.GENI_CHAR_UUID, self.EXTEND_1, response=False
        )
        if delay > 0:
            await asyncio.sleep(delay)
        await self.ble_writer.write_gatt_char(
            self.GENI_CHAR_UUID, self.EXTEND_2, response=False
        )


# ==========================================================================
# REFERENCE IMPLEMENTATION NOTES
# ==========================================================================
"""
For implementing authentication in other languages:

1. CRC-16-CCITT Implementation
   ------------------------------
   Polynomial: 0x1021
   Initial value: 0xFFFF
   Final XOR: 0x0000
   Input reflection: No
   Output reflection: No
   
   Python reference:
   ```python
   def calc_crc16(data: bytes) -> int:
       crc = 0xFFFF
       for byte in data:
           crc ^= byte << 8
           for _ in range(8):
               if crc & 0x8000:
                   crc = (crc << 1) ^ 0x1021
               else:
                   crc <<= 1
               crc &= 0xFFFF
       return crc
   ```

2. Packet Construction
   --------------------
   All packets are pre-computed with correct CRC. Simply send the
   hex bytes as-is:
   
   - LEGACY_MAGIC: 27 07 E7 F8 02 03 94 95 96 EB 47
   - CLASS10_UNLOCK: 27 07 E7 F8 0A 03 56 00 06 C5 5A
   - EXTEND_1: 27 05 E7 F8 05 C1 4B C3 82
   - EXTEND_2: 27 05 E7 F8 0B C1 0F D0 C3

3. Timing Requirements
   --------------------
   - Inter-packet delay: 50ms (within burst)
   - Inter-stage delay: 100-200ms (between stages)
   - No response timeout needed (fire-and-forget)

4. Error Handling
   ---------------
   - If BLE write fails, retry entire sequence
   - No way to verify success except attempting control commands
   - Re-authentication is safe and idempotent

5. Minimal Implementation
   ----------------------
   Simplest working implementation (Python-like pseudocode):
   
   ```
   # Stage 1: Legacy (3 times)
   for i in range(3):
       ble.write(GENI_UUID, LEGACY_MAGIC)
       sleep(50ms)
   sleep(100ms)
   
   # Stage 2: Class 10 (5 times)
   for i in range(5):
       ble.write(GENI_UUID, CLASS10_UNLOCK)
       sleep(50ms)
   sleep(200ms)
   
   # Stage 3: Extensions (sequential, EXTEND_1 before EXTEND_2)
   ble.write(GENI_UUID, EXTEND_1)
   sleep(50ms)
   ble.write(GENI_UUID, EXTEND_2)
   sleep(500ms)
   ```

6. Testing Authentication
   ------------------------
   After authentication, test by:
   - Waiting 2-3 seconds for telemetry stream
   - Attempting to read device info (Class 10, Sub 0x5100)
   - Attempting control mode switch
   
   If these succeed, authentication worked.

7. Common Pitfalls
   ----------------
   - Don't wait for responses - there are none
   - Don't skip timing delays - pump needs processing time
   - Don't reduce repeat counts - reliability matters
   - Don't reorder stages - sequence was empirically determined
   - BLE MTU must be >= 23 bytes for all packets
"""
