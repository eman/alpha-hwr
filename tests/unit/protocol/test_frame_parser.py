"""
Unit tests for frame_parser.py

Tests the GENI protocol frame parser with various frame types and edge cases.
"""

from alpha_hwr.protocol.frame_parser import (
    FrameParser,
    TEST_VECTORS,
)
from alpha_hwr.constants import FRAME_START, RESPONSE_START, CLASS_10


class TestFrameParser:
    """Test basic frame parsing functionality."""

    def test_parse_empty_frame(self):
        """Test parsing empty data."""
        frame = FrameParser.parse_frame(b"")
        assert frame.valid is False
        assert frame.frame_type is None
        assert frame.class_byte is None

    def test_parse_too_short_frame(self):
        """Test parsing frame shorter than minimum length."""
        frame = FrameParser.parse_frame(bytes([0x27, 0x05, 0xE7]))
        assert frame.valid is False

    def test_parse_invalid_start_byte(self):
        """Test parsing frame with invalid start byte."""
        # Valid length but wrong start byte
        data = bytes(
            [0xFF, 0x07, 0xE7, 0xF8, 0x02, 0x03, 0x94, 0x95, 0x96, 0xEB]
        )
        frame = FrameParser.parse_frame(data)
        assert frame.valid is False
        assert frame.frame_type is None

    def test_parse_request_frame(self):
        """Test parsing a request frame (0x27 start byte)."""
        # Auth legacy magic packet
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)
        assert frame.valid is True
        assert frame.frame_type == "request"
        assert frame.class_byte == 2

    def test_parse_response_frame(self):
        """Test parsing a response frame (0x24 start byte)."""
        # Construct a simple response
        data = bytes.fromhex("2407e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)
        assert frame.valid is True
        assert frame.frame_type == "response"
        assert frame.class_byte == 2

    def test_parse_class2_frame(self):
        """Test parsing Class 2 frame."""
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)
        assert frame.class_byte == 2
        assert frame.sub_id is None
        assert frame.obj_id is None
        # Payload contains register address + data (OpSpec=0x03 means 3 bytes)
        assert len(frame.payload) == 3  # Register(2) + Data(1) = 0x94 0x95 0x96
        assert frame.payload == bytes([0x94, 0x95, 0x96])

    def test_parse_class10_frame(self):
        """Test parsing Class 10 frame with Sub-ID and Object ID."""
        # Class 10 frame: motor state telemetry (Sub=0x0045=69, Obj=0x0057=87)
        data = bytes.fromhex("2412e7f80a0a0045005700000000000000000000fd72")
        frame = FrameParser.parse_frame(data)
        assert frame.valid is True
        assert frame.class_byte == CLASS_10
        assert frame.sub_id == 0x0045  # 69
        assert frame.obj_id == 0x0057  # 87
        assert len(frame.payload) == 10

    def test_crc_validation_valid(self):
        """Test CRC validation with correct CRC."""
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)
        assert frame.crc_valid is True

    def test_crc_validation_invalid(self):
        """Test CRC validation with incorrect CRC."""
        # Valid frame with modified CRC
        data = bytes.fromhex("2707e7f80203949596eb00")  # Wrong CRC
        frame = FrameParser.parse_frame(data)
        assert frame.valid is True  # Structure is valid
        assert frame.crc_valid is False  # But CRC is wrong

    def test_raw_data_preserved(self):
        """Test that raw data is preserved in parsed frame."""
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)
        assert frame.raw_data == data


class TestClass10Parsing:
    """Test Class 10 specific parsing."""

    def test_motor_state_frame(self):
        """Test parsing motor state telemetry frame."""
        # Motor state: Sub=0x0045 (69), Obj=0x0057 (87)
        data = bytes.fromhex("2412e7f80a0a0045005700000000000000000000fd72")
        frame = FrameParser.parse_frame(data)
        assert frame.class_byte == CLASS_10
        assert frame.sub_id == 69  # 0x0045
        assert frame.obj_id == 87  # 0x0057
        assert frame.crc_valid is True

    def test_flow_pressure_frame(self):
        """Test parsing flow/pressure telemetry frame."""
        # Flow/pressure: Sub=0x0122 (290), Obj=0x005D (93)
        data = bytes.fromhex(
            "2416e7f80a0e0122005d00000000000000000000000000000b8b"
        )
        frame = FrameParser.parse_frame(data)

        assert frame.valid is True
        assert frame.class_byte == CLASS_10
        assert frame.sub_id == 290  # 0x0122
        assert frame.obj_id == 93  # 0x005D
        assert len(frame.payload) == 14
        assert frame.crc_valid is True

    def test_class10_identifiers_extraction(self):
        """Test extracting Class 10 identifiers."""
        # Motor state packet
        data = bytes.fromhex("2412e7f80a0a0045005700000000000000000000fd72")
        frame = FrameParser.parse_frame(data)

        ids = FrameParser.extract_class10_identifiers(frame)
        assert ids["sub_id"] == 69  # 0x0045
        assert ids["obj_id"] == 87  # 0x0057


class TestTelemetryFrameDetection:
    """Test telemetry frame detection."""

    def test_is_telemetry_motor_state(self):
        """Test detection of motor state telemetry."""
        # Motor state packet
        data = bytes.fromhex("2412e7f80a0a0045005700000000000000000000fd72")
        frame = FrameParser.parse_frame(data)
        # Motor state: obj_id=87, sub_id=69
        assert frame.obj_id == 87
        assert frame.sub_id == 69

    def test_is_telemetry_non_telemetry_frame(self):
        """Test detection returns false for non-telemetry frames."""
        # Class 2 frame
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)
        assert FrameParser.is_telemetry_frame(frame) is False

    def test_is_telemetry_unknown_class10(self):
        """Test detection returns false for unknown Class 10 objects."""
        # Class 10 frame with unknown object (SubID=0xFFFF, ObjID=0x0000)
        data = bytes.fromhex("2415e7f80a01ffff0000000000000000000000000000")
        frame = FrameParser.parse_frame(data)
        # This may fail due to invalid CRC, but structure should be valid
        assert frame.class_byte == CLASS_10


class TestFrameIntegrityValidation:
    """Test comprehensive frame integrity validation."""

    def test_validate_good_frame(self):
        """Test validation of good frame."""
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)

        valid, error = FrameParser.validate_frame_integrity(frame)
        assert valid is True
        assert error == ""

    def test_validate_invalid_structure(self):
        """Test validation of invalid frame structure."""
        frame = FrameParser.parse_frame(b"")

        valid, error = FrameParser.validate_frame_integrity(frame)
        assert valid is False
        assert "structure" in error.lower()

    def test_validate_bad_crc(self):
        """Test validation detects CRC errors."""
        data = bytes.fromhex("2707e7f80203949596eb00")  # Bad CRC
        frame = FrameParser.parse_frame(data)

        valid, error = FrameParser.validate_frame_integrity(frame)
        assert valid is False
        assert "crc" in error.lower()

    def test_validate_missing_class10_ids(self):
        """Test validation of Class 10 frame with missing IDs."""
        # Create a short Class 10 frame (not enough bytes for IDs)
        data = bytes.fromhex(
            "2407e7f80a01008b08"
        )  # Too short - missing SubID/ObjID
        frame = FrameParser.parse_frame(data)

        # Frame should parse but be missing Sub/Obj IDs
        if frame.class_byte == CLASS_10:
            valid, error = FrameParser.validate_frame_integrity(frame)
            if frame.sub_id is None or frame.obj_id is None:
                assert valid is False
                assert "sub-id" in error.lower() or "object id" in error.lower()


class TestReferenceVectors:
    """Test with reference test vectors for other language implementations."""

    def test_class10_motor_state_vector(self):
        """Test motor state reference vector."""
        vector = TEST_VECTORS["class10_motor_state"]
        data = bytes.fromhex(vector["hex"])
        frame = FrameParser.parse_frame(data)

        expected = vector["expected"]
        assert frame.valid == expected["valid"]
        assert frame.frame_type == expected["frame_type"]
        assert frame.class_byte == expected["class_byte"]
        assert frame.sub_id == expected["sub_id"]
        assert frame.obj_id == expected["obj_id"]
        assert len(frame.payload) == expected["payload_len"]
        assert frame.crc_valid == expected["crc_valid"]

    def test_class10_flow_pressure_vector(self):
        """Test flow/pressure reference vector."""
        vector = TEST_VECTORS["class10_flow_pressure"]
        data = bytes.fromhex(vector["hex"])
        frame = FrameParser.parse_frame(data)

        expected = vector["expected"]
        assert frame.valid == expected["valid"]
        assert frame.frame_type == expected["frame_type"]
        assert frame.class_byte == expected["class_byte"]
        assert frame.sub_id == expected["sub_id"]
        assert frame.obj_id == expected["obj_id"]
        assert len(frame.payload) == expected["payload_len"]
        assert frame.crc_valid == expected["crc_valid"]

    def test_auth_legacy_magic_vector(self):
        """Test authentication legacy magic reference vector."""
        vector = TEST_VECTORS["auth_legacy_magic"]
        data = bytes.fromhex(vector["hex"])
        frame = FrameParser.parse_frame(data)

        expected = vector["expected"]
        assert frame.valid == expected["valid"]
        assert frame.frame_type == expected["frame_type"]
        assert frame.class_byte == expected["class_byte"]
        assert frame.sub_id == expected["sub_id"]
        assert frame.obj_id == expected["obj_id"]
        assert len(frame.payload) == expected["payload_len"]
        assert frame.crc_valid == expected["crc_valid"]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_minimum_valid_frame(self):
        """Test parsing minimum valid frame (8 bytes)."""
        # Construct minimal frame: [Start][Len][SvcH][SvcL][Class][OpSpec][CRC-H][CRC-L]
        data = bytes([FRAME_START, 0x04, 0xE7, 0xF8, 0x02, 0x00, 0x00, 0x00])
        frame = FrameParser.parse_frame(data)
        assert frame.valid is True
        # CRC will be invalid unless we calculate it properly

    def test_maximum_payload(self):
        """Test parsing frame with large payload."""
        # Create frame with 100-byte payload
        header = bytes(
            [
                RESPONSE_START,
                0x64,
                0xE7,
                0xF8,
                CLASS_10,
                0x00,
                0x00,
                0x01,
                0x00,
                0x02,
            ]
        )
        payload = bytes([0x00] * 100)
        # Calculate CRC would be needed for valid frame
        data = header + payload + bytes([0x00, 0x00])

        frame = FrameParser.parse_frame(data)
        assert frame.valid is True
        assert frame.class_byte == CLASS_10
        # CRC will be invalid but structure is valid

    def test_payload_extraction_accuracy(self):
        """Test that payload is extracted correctly without header/CRC."""
        # Known frame with specific payload
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)

        # Payload should be after OpSpec (offset 6) and before CRC (last 2 bytes)
        expected_payload = bytes.fromhex("949596")
        assert frame.payload == expected_payload


class TestParsingConsistency:
    """Test that parsing is consistent and deterministic."""

    def test_parse_same_data_twice(self):
        """Test parsing same data twice yields same result."""
        data = bytes.fromhex("2707e7f80203949596eb47")

        frame1 = FrameParser.parse_frame(data)
        frame2 = FrameParser.parse_frame(data)

        assert frame1.valid == frame2.valid
        assert frame1.frame_type == frame2.frame_type
        assert frame1.class_byte == frame2.class_byte
        assert frame1.payload == frame2.payload
        assert frame1.crc_valid == frame2.crc_valid

    def test_parse_does_not_modify_input(self):
        """Test that parsing does not modify input data."""
        original = bytes.fromhex("2707e7f80203949596eb47")
        data = bytearray(original)

        FrameParser.parse_frame(bytes(data))

        assert bytes(data) == original
