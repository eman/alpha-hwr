"""
GENI protocol frame parser.

This module parses raw GENI protocol frames received from the pump:
- Response validation (start byte, length, CRC)
- Class 2/3 register responses
- Class 10 DataObject notifications
- Error handling and validation

Frame Structure
---------------
All GENI frames follow this structure:

[Start] [Length] [ServiceID-H] [ServiceID-L/Source] [APDU...] [CRC-H] [CRC-L]

Where:
- Start: 0x24 (RESPONSE_START for responses) or 0x27 (FRAME_START for requests)
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

For complete protocol reference, see:
- docs/protocol/wire_format.md
- docs/protocol/ble_architecture.md

Implementation Notes for Other Languages
----------------------------------------
This parser is designed to be easily portable to other languages:

1. **Validation First**: Always validate start byte, length, and CRC before parsing
2. **Big-Endian**: All multi-byte values are big-endian (network byte order)
3. **Minimal State**: Parser is stateless - each frame parsed independently
4. **Type Safety**: Use dataclasses/structs to ensure type correctness

Example in C:
```c
typedef struct {
    bool valid;
    FrameType frame_type;
    uint8_t class_byte;
    uint16_t sub_id;
    uint16_t obj_id;
    uint8_t* payload;
    size_t payload_len;
    bool crc_valid;
} ParsedFrame;

ParsedFrame parse_frame(const uint8_t* data, size_t len) {
    ParsedFrame frame = {0};

    // Validate minimum length
    if (len < 8) return frame;

    // Validate start byte
    if (data[0] != FRAME_START && data[0] != RESPONSE_START) return frame;

    // Validate CRC
    uint16_t expected_crc = calc_crc16(&data[1], len - 3);
    uint16_t actual_crc = (data[len-2] << 8) | data[len-1];
    frame.crc_valid = (expected_crc == actual_crc);

    // Extract fields
    frame.frame_type = (data[0] == RESPONSE_START) ? RESPONSE : REQUEST;
    frame.class_byte = data[4];

    if (frame.class_byte == CLASS_10 && len > 9) {
        frame.sub_id = (data[6] << 8) | data[7];
        frame.obj_id = (data[8] << 8) | data[9];
        frame.payload = &data[10];
        frame.payload_len = len - 12;  // Subtract header + CRC
    }

    frame.valid = true;
    return frame;
}
```

Example in JavaScript:
```javascript
class ParsedFrame {
    constructor() {
        this.valid = false;
        this.frameType = null;
        this.classByte = null;
        this.subId = null;
        this.objId = null;
        this.payload = null;
        this.crcValid = false;
    }
}

function parseFrame(data) {
    const frame = new ParsedFrame();

    // Validate minimum length
    if (data.length < 8) return frame;

    // Validate start byte
    if (data[0] !== FRAME_START && data[0] !== RESPONSE_START) return frame;

    // Validate CRC
    const expectedCrc = calcCrc16(data.slice(1, -2));
    const actualCrc = (data[data.length-2] << 8) | data[data.length-1];
    frame.crcValid = (expectedCrc === actualCrc);

    // Extract fields
    frame.frameType = data[0] === RESPONSE_START ? 'response' : 'request';
    frame.classByte = data[4];

    if (frame.classByte === CLASS_10 && data.length > 9) {
        frame.subId = (data[6] << 8) | data[7];
        frame.objId = (data[8] << 8) | data[9];
        frame.payload = data.slice(10, -2);
    }

    frame.valid = true;
    return frame;
}
```
"""

from dataclasses import dataclass
from typing import Literal

from ..constants import CLASS_10, FRAME_START, RESPONSE_START
from ..utils import calc_crc16_read


@dataclass
class ParsedFrame:
    """
    Parsed GENI protocol frame.

    This structure represents a fully parsed GENI frame with all fields extracted
    and validated. Use this as a reference for implementing in other languages.

    Attributes:
        valid: True if the frame structure is valid (correct start byte, length)
        frame_type: 'request' (0x27) or 'response' (0x24)
        class_byte: GENI class byte (2, 3, 10, etc.)
        sub_id: Sub-ID for Class 10 frames (None for other classes)
        obj_id: Object ID for Class 10 frames (None for other classes)
        payload: Raw payload bytes (excluding header and CRC)
        crc_valid: True if CRC checksum is correct
        raw_data: Original raw frame data

    Example:
        >>> # Parse a Class 10 telemetry response
        >>> raw = bytes.fromhex('2415e7f80a015700450000000000000000000000fa3c')
        >>> frame = FrameParser.parse_frame(raw)
        >>> frame.valid
        True
        >>> frame.class_byte
        10
        >>> frame.sub_id
        22272  # 0x5700
        >>> frame.obj_id
        69     # 0x0045
    """

    valid: bool
    frame_type: Literal["request", "response"] | None
    class_byte: int | None
    sub_id: int | None
    obj_id: int | None
    payload: bytes
    crc_valid: bool
    raw_data: bytes


class FrameParser:
    """
    Parses GENI protocol frames.

    This is a stateless parser - each frame is parsed independently.
    All methods are static for easy porting to other languages.
    """

    @staticmethod
    def parse_frame(data: bytes) -> ParsedFrame:
        """
        Parse raw GENI frame into structured data.

        This method validates the frame structure and extracts all fields.
        It performs the following validations:
        1. Minimum length (8 bytes)
        2. Valid start byte (0x27 or 0x24)
        3. CRC checksum

        Args:
            data: Raw frame bytes from BLE notification or response

        Returns:
            ParsedFrame with extracted fields and validation flags

        Examples:
            >>> # Parse a request frame
            >>> request = bytes.fromhex('2707e7f80203949596eb47')
            >>> frame = FrameParser.parse_frame(request)
            >>> frame.valid
            True
            >>> frame.frame_type
            'request'
            >>> frame.class_byte
            2

            >>> # Parse a Class 10 response
            >>> response = bytes.fromhex('2415e7f80a015700450000000000000000000000fa3c')
            >>> frame = FrameParser.parse_frame(response)
            >>> frame.class_byte
            10
            >>> frame.sub_id
            22272
            >>> frame.obj_id
            69

            >>> # Parse invalid frame
            >>> invalid = bytes.fromhex('ff00')
            >>> frame = FrameParser.parse_frame(invalid)
            >>> frame.valid
            False

        Implementation Notes:
            - Always check `valid` flag before using parsed data
            - Check `crc_valid` for data integrity
            - Handle None values for sub_id/obj_id (not present in Class 2/3)
        """
        # Initialize result with invalid state
        result = ParsedFrame(
            valid=False,
            frame_type=None,
            class_byte=None,
            sub_id=None,
            obj_id=None,
            payload=b"",
            crc_valid=False,
            raw_data=data,
        )

        # Validate minimum length
        if len(data) < 8:
            return result

        # Validate start byte
        start_byte = data[0]
        if start_byte == RESPONSE_START:
            result.frame_type = "response"
        elif start_byte == FRAME_START:
            result.frame_type = "request"
        else:
            return result

        # Frame is structurally valid
        result.valid = True

        # Validate CRC
        # CRC covers from Length byte to end of APDU (excludes Start and CRC itself)
        crc_data = data[1:-2]
        calculated_crc = calc_crc16_read(crc_data)
        actual_crc = (data[-2] << 8) | data[-1]
        result.crc_valid = calculated_crc == actual_crc

        # Extract class byte (offset 4 in frame)
        result.class_byte = data[4]

        # Parse based on class
        if result.class_byte == CLASS_10 and len(data) > 5:
            opspec = data[5]
            # OpSpecs for register-read responses: 0x30 (motor), 0x2b (flow), 0x14 (temp), 0x09 (alarms/warnings), etc.
            # Format: [Class][OpSpec][Seq(2)][Id(2)][Res(2)][DataLen][Data...]
            if opspec in (0x30, 0x2B, 0x14, 0x2E, 0x2D, 0x09):
                if len(data) > 12:
                    result.payload = data[13:-2]  # Data starts at offset 13
                    # We can store the ID as obj_id for routing if needed,
                    # but these are handled by decode_register_read_response anyway.
                    result.obj_id = (data[8] << 8) | data[9]
                    result.sub_id = (data[6] << 8) | data[
                        7
                    ]  # This is actually sequence number
            elif len(data) > 9:
                # Class 10 Notification/SET: [Class][OpSpec][SubH][SubL][ObjH][ObjL][Payload...][CRC]
                result.sub_id = (data[6] << 8) | data[7]  # Big-endian uint16
                result.obj_id = (data[8] << 8) | data[9]  # Big-endian uint16
                result.payload = data[10:-2]  # From after ObjID to before CRC
        else:
            # Class 2/3: Payload starts after OpSpec
            # Format: [Start][Len][SvcH][SvcL][Class][OpSpec][Register...][Payload...][CRC]
            result.payload = data[6:-2]  # From after OpSpec to before CRC

        return result

    @staticmethod
    def extract_class10_identifiers(
        frame: ParsedFrame,
    ) -> dict[str, int | None]:
        """
        Extract Class 10 identifiers from parsed frame.

        Convenience method to get Sub-ID and Object ID as a dictionary.
        Useful for routing/dispatching based on object type.

        Args:
            frame: Parsed frame from parse_frame()

        Returns:
            Dictionary with 'sub_id' and 'obj_id' keys

        Examples:
            >>> frame = FrameParser.parse_frame(response_data)
            >>> ids = FrameParser.extract_class10_identifiers(frame)
            >>> if ids['obj_id'] == 87 and ids['sub_id'] == 69:
            ...     print("Motor state telemetry")
        """
        return {
            "sub_id": frame.sub_id,
            "obj_id": frame.obj_id,
        }

    @staticmethod
    def is_telemetry_frame(frame: ParsedFrame) -> bool:
        """
        Check if frame is a telemetry notification.

        Telemetry frames are Class 10 responses with known Sub-ID/Object ID pairs.

        Args:
            frame: Parsed frame from parse_frame()

        Returns:
            True if frame is a known telemetry type

        Examples:
            >>> frame = FrameParser.parse_frame(response_data)
            >>> if FrameParser.is_telemetry_frame(frame):
            ...     telemetry_data = TelemetryDecoder.decode(frame)
        """
        if not frame.valid or frame.class_byte != CLASS_10:
            return False

        # Known telemetry object IDs
        TELEMETRY_OBJECTS = {
            (87, 69),  # Motor state
            (93, 290),  # Flow/Pressure
            (93, 300),  # Temperature
            (88, 0),  # Active alarms
            (88, 11),  # Active warnings
            (3, 1),  # Custom electrical
            (0x2D01, 1),  # Custom speed/power
            (0x1602, 2),  # Custom temperature
        }

        return (frame.obj_id, frame.sub_id) in TELEMETRY_OBJECTS

    @staticmethod
    def validate_frame_integrity(frame: ParsedFrame) -> tuple[bool, str]:
        """
        Comprehensive validation of frame integrity.

        Checks all validation flags and returns detailed error message if invalid.

        Args:
            frame: Parsed frame from parse_frame()

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if all checks pass
            - error_message: Empty string if valid, otherwise describes the issue

        Examples:
            >>> frame = FrameParser.parse_frame(data)
            >>> valid, error = FrameParser.validate_frame_integrity(frame)
            >>> if not valid:
            ...     logger.error(f"Frame validation failed: {error}")
        """
        if not frame.valid:
            return False, "Invalid frame structure (bad start byte or length)"

        if not frame.crc_valid:
            return False, "CRC checksum mismatch"

        if frame.class_byte is None:
            return False, "Missing class byte"

        if frame.class_byte == CLASS_10 and (
            frame.sub_id is None or frame.obj_id is None
        ):
            return False, "Class 10 frame missing Sub-ID or Object ID"

        return True, ""


# Test vectors for validation in other languages
# These can be used to verify correct implementation
TEST_VECTORS = {
    "class10_motor_state": {
        "hex": "2412e7f80a0a0045005700000000000000000000fd72",
        "expected": {
            "valid": True,
            "frame_type": "response",
            "class_byte": 10,
            "sub_id": 69,  # 0x0045
            "obj_id": 87,  # 0x0057
            "payload_len": 10,
            "crc_valid": True,
        },
    },
    "class10_flow_pressure": {
        "hex": "2416e7f80a0e0122005d00000000000000000000000000000b8b",
        "expected": {
            "valid": True,
            "frame_type": "response",
            "class_byte": 10,
            "sub_id": 290,  # 0x0122 (big-endian: 01 22)
            "obj_id": 93,  # 0x005D (big-endian: 00 5D)
            "payload_len": 14,
            "crc_valid": True,
        },
    },
    "auth_legacy_magic": {
        "hex": "2707e7f80203949596eb47",
        "expected": {
            "valid": True,
            "frame_type": "request",
            "class_byte": 2,
            "sub_id": None,
            "obj_id": None,
            "payload_len": 3,  # Payload is after OpSpec (offset 6), before CRC
            "crc_valid": True,
        },
    },
}
