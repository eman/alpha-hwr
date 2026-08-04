"""
GENI protocol frame builder.

This module constructs GENI protocol frames for all operations:
- Class 2/3: Register-based operations (legacy)
- Class 10: DataObject operations (modern)
- Command types: INFO, SET, READ, WRITE, EXECUTE

Frame Structure
---------------
All GENI frames follow this structure:

[Start] [Length] [ServiceID-H] [ServiceID-L/Source] [APDU...] [CRC-H] [CRC-L]

Where:
- Start: 0x27 (FRAME_START for requests)
- Length: Number of bytes from ServiceID to end of APDU (not including CRC)
- ServiceID-H: 0xE7 (GENI service)
- ServiceID-L/Source: 0xF8 (standard) or 0x0A (alternative)
- APDU: Application Protocol Data Unit (class, opspec, data)
- CRC: CRC-16-CCITT checksum

APDU Formats
------------

Class 2/3 (Register-based):
[Class] [OpSpec] [Register...] [Data...]

Class 10 (DataObject):
[0x0A] [OpSpec] [SubID-H] [SubID-L] [ObjID-H] [ObjID-L] [Data...]

OpSpec Encoding:
- Bits 7-6: Operation type (00=INFO, 01=SET, 10=WRITE, etc.)
- Bits 5-0: Data length

For complete protocol reference, see:
- docs/protocol/wire_format.md
- docs/protocol/ble_architecture.md
"""

from ..constants import (
    CLASS_10,
    FRAME_START,
    RESERVED_BYTE,
    SERVICE_ID_HIGH,
)
from ..utils import calc_crc16, calc_crc16_read


class FrameBuilder:
    """
    Builds GENI protocol frames with automatic CRC calculation.

    All methods are static and return complete frames ready to send
    over BLE. CRC is automatically calculated and appended.

    Examples
    --------
    >>> # Read temperature register
    >>> packet = FrameBuilder.build_command_info(0x03, 0x5D012C)
    >>> len(packet)
    9
    >>> packet[0] == 0x27  # FRAME_START
    True

    >>> # Set control mode
    >>> data = encode_float_be(14710.0)  # 1.5m in Pascals
    >>> packet = FrameBuilder.build_data_object_set(0x5600, 0x0601, data)

    Notes for Reimplementation
    --------------------------
    Frame building is straightforward:
    1. Build header [Start, Length, ServiceID, Source]
    2. Build APDU [Class, OpSpec, Address/IDs, Data]
    3. Calculate CRC over bytes from Length to end of APDU
    4. Append CRC (big-endian, 2 bytes)

    Key points:
    - CRC includes everything AFTER start byte
    - Use calc_crc16_read for INFO/READ/EXECUTE
    - Use calc_crc16 for WRITE operations
    - Length field does NOT include CRC bytes
    - OpSpec encodes both operation and data length
    """

    @staticmethod
    def build_command_info(
        class_byte: int, register: int, source: int = 0xF8
    ) -> bytes:
        """
        Build INFO command for reading register value.

        INFO commands are used to read register values. They're typically
        used for Class 2/3 operations (legacy telemetry reads).

        Frame Structure:
        [27] [Length] [E7] [F8] [Class] [OpSpec] [Register...] [CRC-H] [CRC-L]

        Parameters
        ----------
        class_byte : int
            Protocol class (2 or 3 for register operations)
        register : int
            Register address (1, 2, or 3 bytes depending on value)
        source : int, default=0xF8
            Source address (0xF8 standard, 0x0A alternative)

        Returns
        -------
        bytes
            Complete frame ready to send

        Examples
        --------
        >>> # Read 1-byte register
        >>> packet = FrameBuilder.build_command_info(0x02, 0x45)
        >>> packet.hex()
        '27050e7f8020345...'

        >>> # Read 2-byte register
        >>> packet = FrameBuilder.build_command_info(0x03, 0x5D01)
        >>> packet[0] == 0x27
        True

        >>> # Read 3-byte register (temperature)
        >>> packet = FrameBuilder.build_command_info(0x03, 0x5D012C)

        Notes
        -----
        Register length is auto-detected:
        - register <= 0xFF: 1 byte
        - register <= 0xFFFF: 2 bytes
        - register > 0xFFFF: 3 bytes
        """
        # Encode register address (variable length)
        reg_bytes = []
        if register > 0xFFFF:
            # 3-byte register
            reg_bytes = [
                (register >> 16) & 0xFF,
                (register >> 8) & 0xFF,
                register & 0xFF,
            ]
        elif register > 0xFF:
            # 2-byte register
            reg_bytes = [(register >> 8) & 0xFF, register & 0xFF]
        else:
            # 1-byte register
            reg_bytes = [register & 0xFF]

        # OpSpec: INFO operation (bits 7-6 = 00), length = register bytes
        OS_INFO = 0  # Operation code for INFO
        data_length = len(reg_bytes)
        op_length_byte = (OS_INFO << 6) | data_length

        # Build APDU
        apdu = bytearray([class_byte, op_length_byte])
        apdu.extend(reg_bytes)

        # Build complete frame (without CRC)
        length = 1 + 1 + len(apdu)  # ServiceID + Source + APDU
        packet = bytearray([FRAME_START, length, SERVICE_ID_HIGH, source])
        packet.extend(apdu)

        # Calculate and append CRC
        crc = calc_crc16_read(
            bytes(packet[1:])
        )  # CRC over everything after start
        packet.extend([(crc >> 8) & 0xFF, crc & 0xFF])

        return bytes(packet)

    @staticmethod
    def build_set_command(
        class_byte: int,
        op_spec: int,
        register: int,
        value: bytes | int,
        source: int = 0xF8,
    ) -> bytes:
        """
        Build SET command for writing to register.

        SET commands are used to write values to registers. Used for
        control operations and configuration changes.

        Frame Structure:
        [27] [Length] [E7] [F8] [Class] [OpSpec] [Register...] [Value...] [CRC]

        Parameters
        ----------
        class_byte : int
            Protocol class (2 or 3)
        op_spec : int
            Operation specifier (encodes operation + length)
        register : int
            Register address
        value : bytes | int
            Value to write (bytes for multi-byte, int for single byte)
        source : int, default=0xF8
            Source address

        Returns
        -------
        bytes
            Complete frame ready to send

        Examples
        --------
        >>> # Write single byte
        >>> packet = FrameBuilder.build_set_command(0x02, 0x01, 0x45, 0x01)

        >>> # Write float value
        >>> value = encode_float_be(100.0)
        >>> packet = FrameBuilder.build_set_command(0x03, 0x04, 0x5D01, value)
        """
        # Encode register address
        reg_bytes = []
        if register > 0xFFFF:
            reg_bytes = [
                (register >> 16) & 0xFF,
                (register >> 8) & 0xFF,
                register & 0xFF,
            ]
        elif register > 0xFF:
            reg_bytes = [(register >> 8) & 0xFF, register & 0xFF]
        else:
            reg_bytes = [register & 0xFF]

        # Encode value
        if isinstance(value, int):
            val_bytes = [value & 0xFF]
        else:
            val_bytes = list(value)

        # OpSpec encodes length
        data_length = len(reg_bytes) + len(val_bytes)
        op_length_byte = (op_spec << 6) | data_length

        # Build APDU
        apdu = bytearray([class_byte, op_length_byte])
        apdu.extend(reg_bytes)
        apdu.extend(val_bytes)

        # Build frame
        length = 1 + 1 + len(apdu)
        packet = bytearray([FRAME_START, length, SERVICE_ID_HIGH, source])
        packet.extend(apdu)

        # CRC
        crc = calc_crc16_read(bytes(packet[1:]))
        packet.extend([(crc >> 8) & 0xFF, crc & 0xFF])

        return bytes(packet)

    @staticmethod
    def build_data_object_set(
        sub_id: int,
        obj_id: int,
        data: bytes,
        source: int = 0xF8,
        override_op: int | None = None,
        override_len: int | None = None,
    ) -> bytes:
        """
        Build Class 10 DataObject SET operation.

        Class 10 operations are the modern GENI protocol used for:
        - Control mode changes (Sub 0x5600)
        - Schedule management
        - Configuration updates
        - Device information queries

        Frame Structure:
        [27] [Len] [E7] [F8] [0A] [OpSpec] [Sub-H] [Sub-L] [Obj-H] [Obj-L] [Data...] [CRC]

        Parameters
        ----------
        sub_id : int
            Sub-system ID (e.g., 0x5600 for control)
        obj_id : int
            Object ID within subsystem
        data : bytes
            Payload data (can be empty for trigger operations)
        source : int, default=0xF8
            Source address
        override_op : int | None
            Override OpSpec calculation (advanced use)
        override_len : int | None
            Override length calculation (advanced use)

        Returns
        -------
        bytes
            Complete frame ready to send

        Examples
        --------
        >>> # Set constant pressure mode to 1.5m (14710 Pa)
        >>> setpoint_data = encode_float_be(14710.0)
        >>> control_data = bytes([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00])
        >>> control_data += setpoint_data
        >>> packet = FrameBuilder.build_data_object_set(0x5600, 0x0601, control_data)

        >>> # Trigger operation (no data)
        >>> packet = FrameBuilder.build_data_object_set(0x5600, 0x0006, b'')

        Notes
        -----
        OpSpec for Class 10:
        - Bit 7: Always 1 for SET (0x80)
        - Bits 6-0: Length of SubID + ObjID + Data (minimum 4)

        Length field:
        - Includes ServiceID, Source, Class, OpSpec, SubID, ObjID, Data
        - Does NOT include Frame Start or CRC
        """
        # Calculate frame length
        standard_len = (
            1 + 1 + 1 + 1 + 4 + len(data)
        )  # ServiceID + Source + Class + OpSpec + IDs + Data
        length = override_len if override_len is not None else standard_len

        # Calculate OpSpec (bit 7 set = SET, bits 6-0 = data length)
        op_bits = length - 4  # Subtract ServiceID, Source, Class, OpSpec
        if override_op is None and op_bits > 0x3F:
            raise ValueError(
                f"Payload too large for OpSpec: {op_bits} "
                f"exceeds 6-bit max (63). Use override_op."
            )
        op_spec = (
            override_op
            if override_op is not None
            else (0x80 | (op_bits & 0x3F))
        )

        # Build APDU
        apdu = bytearray(
            [
                CLASS_10,
                op_spec,
                (sub_id >> 8) & 0xFF,
                sub_id & 0xFF,
                (obj_id >> 8) & 0xFF,
                obj_id & 0xFF,
            ]
        )
        apdu.extend(data)

        # Build frame
        packet = bytearray([FRAME_START, length, SERVICE_ID_HIGH, source])
        packet.extend(apdu)

        # CRC
        crc = calc_crc16_read(bytes(packet[1:]))
        packet.extend([(crc >> 8) & 0xFF, crc & 0xFF])

        return bytes(packet)

    @staticmethod
    def build_class10_read(register: int, source: int = 0xF8) -> bytes:
        """
        Build Class 10 register READ request for telemetry.

        This builds the format that the ALPHA HWR pump actually uses for
        telemetry queries: Class 10, OpSpec 0x03, with a 3-byte register address.

        Frame Structure:
        [27] [07] [E7] [F8] [0A] [03] [Reg-H] [Reg-M] [Reg-L] [CRC]

        Parameters
        ----------
        register : int
            3-byte register address (e.g., 0x570045 for motor state)
        source : int, default=0xF8
            Source address (client)

        Returns
        -------
        bytes
            Complete frame ready to send

        Examples
        --------
        >>> # Request motor state (0x570045)
        >>> packet = FrameBuilder.build_class10_read(0x570045)
        >>> # Sends: 2707e7f80a035700458acd

        >>> # Request temperatures (0x5D012C)
        >>> packet = FrameBuilder.build_class10_read(0x5D012C)

        Notes
        -----
        This is empirically determined from working captures.
        The register is encoded as 3 bytes in big-endian format.

        Common registers:
        - 0x570045: Motor state (voltage, current, power, RPM, temp)
        - 0x5D0122: Flow rate and head pressure
        - 0x5D012C: Temperatures (media, PCB, control box)
        """
        # Encode register as 3 bytes (big-endian)
        reg_bytes = [
            (register >> 16) & 0xFF,  # High byte
            (register >> 8) & 0xFF,  # Middle byte
            register & 0xFF,  # Low byte
        ]

        # Length = 7 (ServiceID + Source + Class + OpSpec + 3 register bytes)
        length = 7
        op_spec = 0x03

        # Build APDU
        apdu = bytearray([CLASS_10, op_spec] + reg_bytes)

        # Build frame
        packet = bytearray([FRAME_START, length, SERVICE_ID_HIGH, source])
        packet.extend(apdu)

        # CRC
        crc = calc_crc16_read(bytes(packet[1:]))
        packet.extend([(crc >> 8) & 0xFF, crc & 0xFF])

        return bytes(packet)

    # Alias for compatibility
    build_data_object_info = build_class10_read

    @staticmethod
    def build_read_request(register: int, source: int = 0xF8) -> bytes:
        """
        Build READ request for register.

        Parameters
        ----------
        register : int
            Register address to read
        source : int, default=0xF8
            Source address

        Returns
        -------
        bytes
            Complete frame ready to send
        """
        # Encode register
        reg_bytes = []
        if register > 0xFFFF:
            reg_bytes = [
                (register >> 16) & 0xFF,
                (register >> 8) & 0xFF,
                register & 0xFF,
            ]
        else:
            reg_bytes = [(register >> 8) & 0xFF, register & 0xFF]

        # Command opcode for READ
        from ..constants import CommandOpcode

        header = [
            FRAME_START,
            4 + len(reg_bytes),
            SERVICE_ID_HIGH,
            source,
            RESERVED_BYTE,
            CommandOpcode.READ,
        ]
        packet = bytearray(header + reg_bytes)

        crc = calc_crc16_read(bytes(packet[1:]))
        packet.extend([(crc >> 8) & 0xFF, crc & 0xFF])

        return bytes(packet)

    @staticmethod
    def build_write_request(
        register: int, value: int | bytes = 1, source: int = 0x0A
    ) -> bytes:
        """
        Build WRITE request for register.

        Parameters
        ----------
        register : int
            Register address to write
        value : int | bytes, default=1
            Value to write
        source : int, default=0x0A
            Source address (0x0A commonly used for writes)

        Returns
        -------
        bytes
            Complete frame ready to send

        Notes
        -----
        WRITE operations use calc_crc16 (no final XOR), unlike
        READ operations which use calc_crc16_read (with final XOR).
        """
        # Encode register
        reg_bytes = []
        if register > 0xFFFF:
            reg_bytes = [
                (register >> 16) & 0xFF,
                (register >> 8) & 0xFF,
                register & 0xFF,
            ]
        else:
            reg_bytes = [(register >> 8) & 0xFF, register & 0xFF]

        # Encode value
        val_bytes = [value & 0xFF] if isinstance(value, int) else list(value)
        payload = reg_bytes + val_bytes

        # Command opcode for WRITE
        from ..constants import CommandOpcode

        header = [
            FRAME_START,
            4 + len(payload),
            SERVICE_ID_HIGH,
            source,
            RESERVED_BYTE,
            CommandOpcode.WRITE,
        ]
        packet = bytearray(header + payload)

        # Note: WRITE uses calc_crc16 (no XOR), CRC excludes start byte
        crc = calc_crc16(bytes(packet[1:]))
        packet.extend([(crc >> 8) & 0xFF, crc & 0xFF])

        return bytes(packet)

    @staticmethod
    def build_execute_request(
        reg_class: int, reg_id: int, source: int = 0x0A
    ) -> bytes:
        """
        Build EXECUTE command.

        EXECUTE commands trigger operations without data transfer.

        Parameters
        ----------
        reg_class : int
            Register class
        reg_id : int
            Register ID within class
        source : int, default=0x0A
            Source address

        Returns
        -------
        bytes
            Complete frame ready to send
        """
        payload = [reg_class, reg_id]

        from ..constants import CommandOpcode

        header = [
            FRAME_START,
            4 + len(payload),
            SERVICE_ID_HIGH,
            source,
            RESERVED_BYTE,
            CommandOpcode.EXECUTE,
        ]

        packet = bytearray(header + payload)
        crc = calc_crc16_read(bytes(packet[1:]))
        packet.extend([(crc >> 8) & 0xFF, crc & 0xFF])

        return bytes(packet)


# ==========================================================================
# TEST VECTORS AND VALIDATION
# ==========================================================================
"""
Frame Builder Test Vectors
===========================

Use these to validate implementations in other languages.

1. INFO Command (Read Temperature Register 0x5D012C)
----------------------------------------------------
Input:
  class_byte = 0x03
  register = 0x5D012C
  source = 0xF8

Expected Output (hex):
  27 07 E7 F8 03 03 5D 01 2C [CRC-H] [CRC-L]

Breakdown:
  27        - FRAME_START
  07        - Length (7 bytes)
  E7 F8     - Service ID + Source
  03        - Class 3
  03        - OpSpec (INFO, 3 bytes data)
  5D 01 2C  - Register address (3 bytes)
  [CRC]     - CRC-16-CCITT with XOR

Python validation:
>>> packet = FrameBuilder.build_command_info(0x03, 0x5D012C, 0xF8)
>>> assert packet[0] == 0x27
>>> assert packet[1] == 0x07
>>> assert packet[4] == 0x03
>>> assert packet[6:9] == bytes([0x5D, 0x01, 0x2C])

2. Class 10 SET (Unlock Command)
---------------------------------
Input:
  sub_id = 0x5600
  obj_id = 0x0006
  data = b''  # Empty (trigger operation)
  
Expected Output:
  27 07 E7 F8 0A 03 56 00 06 C5 5A

Breakdown:
  27        - FRAME_START
  07        - Length (7 bytes)
  E7 F8     - Service ID + Source
  0A        - Class 10
  03        - OpSpec (SET, 3 bytes = SubID + ObjID)
  56 00     - SubID 0x5600
  06        - ObjID 0x0006 (only 1 byte since < 256)
  C5 5A     - CRC

Python validation:
>>> packet = FrameBuilder.build_data_object_set(0x5600, 0x0006, b'')
>>> assert packet == bytes.fromhex("2707e7f80a03560006c55a")

3. Class 10 SET with Data (Control Mode)
-----------------------------------------
Input:
  sub_id = 0x5600
  obj_id = 0x0601
  data = bytes([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00]) + encode_float_be(14710.0)

Expected:
  Frame with 12-byte payload (8 header + 4 float)

Python validation:
>>> from alpha_hwr.protocol.codec import encode_float_be
>>> control_data = bytes([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00])
>>> control_data += encode_float_be(14710.0)
>>> packet = FrameBuilder.build_data_object_set(0x5600, 0x0601, control_data)
>>> assert packet[0] == 0x27
>>> assert packet[4] == 0x0A  # Class 10
>>> assert packet[6:8] == bytes([0x56, 0x00])  # SubID
>>> assert packet[8:10] == bytes([0x06, 0x01])  # ObjID
"""
