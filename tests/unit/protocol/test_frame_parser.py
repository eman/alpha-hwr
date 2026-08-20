"""
Unit tests for frame_parser.py

Tests the GENI protocol frame parser with various frame types and edge cases.
"""

from alpha_hwr.constants import CLASS_10, FRAME_START, RESPONSE_START
from alpha_hwr.protocol.frame_parser import (
    TEST_VECTORS,
    FrameParser,
)


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
        """
        A Class 10 reply carries a type in bytes 6-9, not an address.

        Captured motor-state reply: bytes 6-9 read ``00 01 00 03``, which is
        object type 3 version 1. Nothing in it echoes the Object 87 /
        Sub-ID 69 that was asked for, because the pump does not send an
        address back.
        """
        data = bytes.fromhex(
            "2434f8e70a300001000300002942e730d643237a000000000000000000"
            "00000000000000007fffffff7fffffff0000000000000000002385"
        )
        frame = FrameParser.parse_frame(data)
        assert frame.valid is True
        assert frame.crc_valid is True
        assert frame.class_byte == CLASS_10
        assert frame.type_high == 0x0001
        assert frame.type_low_ver == 0x0003
        # Declared payload is 48 bytes; four of them are the type fields.
        assert data[5] == 48
        assert len(frame.payload) == 44

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
        """Motor-state reply: object type 3 version 1."""
        data = bytes.fromhex(
            "2434f8e70a300001000300002942e730d643237a000000000000000000"
            "00000000000000007fffffff7fffffff0000000000000000002385"
        )
        frame = FrameParser.parse_frame(data)
        assert frame.class_byte == CLASS_10
        assert (frame.type_high, frame.type_low_ver) == (0x0001, 0x0003)
        assert frame.crc_valid is True

    def test_flow_pressure_frame(self):
        """Flow/pressure reply: object type 0x3502 version 2."""
        data = bytes.fromhex(
            "242ff8e70a2b0002350200002400000000000000007fffffff7fffffff"
            "7fffffff7fffffff000000000000000000000000edbe"
        )
        frame = FrameParser.parse_frame(data)

        assert frame.valid is True
        assert frame.class_byte == CLASS_10
        assert (frame.type_high, frame.type_low_ver) == (0x0002, 0x3502)
        assert data[5] == len(data) - 8
        assert len(frame.payload) == 39
        assert frame.crc_valid is True

    def test_four_objects_share_one_type(self):
        """
        Object 86 subs 13, 15, 17 and 39 answer identically.

        All four are instances of type 301 version 1, so a reply cannot say
        which sub-id it came from. That is why a chain reading them has to
        be strictly sequential and stop at the first failure - carrying on
        shifts every remaining answer by one slot.
        """
        speed = bytes.fromhex(
            "2427f8e70a2300012d0100001c452f000044ce400045657000"
            "c56570003f8000003f8000003f80000089a9"
        )
        pressure = bytes.fromhex(
            "2427f8e70a2300012d0100001c467a00004619300046bbb200"
            "461930003dcccccd3f7333333f8000006f88"
        )
        a = FrameParser.parse_frame(speed)
        b = FrameParser.parse_frame(pressure)
        assert a.crc_valid and b.crc_valid
        assert (a.type_high, a.type_low_ver) == (b.type_high, b.type_low_ver)
        assert a.payload != b.payload


class TestTelemetryFrameDetection:
    """Test telemetry frame detection."""

    def test_is_telemetry_motor_state(self):
        """Test detection of motor state telemetry."""
        # Motor state packet
        data = bytes.fromhex(
            "2434f8e70a300001000300002942e730d643237a000000000000000000"
            "00000000000000007fffffff7fffffff0000000000000000002385"
        )
        frame = FrameParser.parse_frame(data)
        assert FrameParser.is_telemetry_frame(frame) is True

    def test_is_telemetry_non_telemetry_frame(self):
        """Test detection returns false for non-telemetry frames."""
        # Class 2 frame
        data = bytes.fromhex("2707e7f80203949596eb47")
        frame = FrameParser.parse_frame(data)
        assert FrameParser.is_telemetry_frame(frame) is False

    def test_is_telemetry_unknown_class10(self):
        """A Class 10 object we have no type for is not telemetry."""
        # Schedule overview - a real reply, but not part of the stream.
        data = bytes.fromhex(
            "2415f8e70a110000da0100000a02050005010100000000dd89"
        )
        frame = FrameParser.parse_frame(data)
        assert frame.class_byte == CLASS_10
        assert frame.crc_valid is True
        assert FrameParser.is_telemetry_frame(frame) is False


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

    def test_short_class10_ack_is_valid_without_type_fields(self):
        """
        A short acknowledgement has no type fields, and is still valid.

        This used to be asserted the other way round - a Class 10 frame
        without identifiers was called invalid. But the pump's write
        acknowledgement is nine bytes and carries none, so the rule
        condemned every reply to every write.
        """
        data = bytes.fromhex("2405f8e70a0100aea2")
        frame = FrameParser.parse_frame(data)

        assert frame.class_byte == CLASS_10
        assert frame.type_high is None
        assert frame.type_low_ver is None
        valid, error = FrameParser.validate_frame_integrity(frame)
        assert valid is True, error


class TestReferenceVectors:
    """
    The captured vectors, for validating a reimplementation.

    Every entry is a recording from an ALPHA HWR. The table these replaced
    was hand-written with the destination and source addresses reversed,
    which is a shape this pump never sends - so a port checked against it
    was being checked against a frame that cannot arrive.
    """

    def test_every_vector_parses_and_checksums(self):
        for name, vector in TEST_VECTORS.items():
            data = bytes.fromhex(vector["hex"])
            frame = FrameParser.parse_frame(data)
            expected = vector["expected"]

            assert frame.valid == expected["valid"], name
            assert frame.frame_type == expected["frame_type"], name
            assert frame.class_byte == expected["class_byte"], name
            assert frame.crc_valid == expected["crc_valid"], name

            if "type_high" in expected:
                assert frame.type_high == expected["type_high"], name
                assert frame.type_low_ver == expected["type_low_ver"], name
            if "payload_len" in expected:
                assert len(frame.payload) == expected["payload_len"], name
            if "payload" in expected:
                assert frame.payload.decode() == expected["payload"], name

    def test_every_vector_is_addressed_pump_to_host(self):
        """Destination 0xF8, source 0xE7 - the reply direction."""
        for name, vector in TEST_VECTORS.items():
            data = bytes.fromhex(vector["hex"])
            assert (data[2], data[3]) == (0xF8, 0xE7), name

    def test_every_vector_declares_its_own_length(self):
        """``byte5 == len(frame) - 8`` on every reply this pump sends."""
        for name, vector in TEST_VECTORS.items():
            data = bytes.fromhex(vector["hex"])
            assert data[5] == len(data) - 8, name
            assert data[1] + 4 == len(data), name


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
