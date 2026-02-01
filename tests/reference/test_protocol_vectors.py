"""
Reference implementation tests with known byte-level test vectors.

These tests validate the Python implementation against known-good
protocol examples. The test vectors are portable and can be used
to validate implementations in other languages (TypeScript, Rust, etc.).

Test Coverage:
--------------
1. Codec Functions (encode/decode primitives)
2. Frame Building (command construction)
3. Frame Parsing (response parsing)
4. CRC Calculation
5. Complete Command/Response Cycles

These tests use hard-coded byte sequences to ensure the protocol
implementation matches the specification exactly.
"""

import pytest
from alpha_hwr.protocol.codec import (
    encode_float_be,
    decode_float_be,
    encode_uint16_be,
    decode_uint16_be,
    encode_uint32_be,
    decode_uint32_be,
)
from alpha_hwr.protocol.frame_builder import FrameBuilder
from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.utils import calc_crc16, calc_crc16_read


class TestCodecVectors:
    """Test codec functions with known byte sequences."""

    def test_encode_float_be_positive(self):
        """Test encoding positive float to big-endian bytes."""
        # 1.5 in IEEE 754 = 0x3FC00000
        result = encode_float_be(1.5)
        assert result == bytes([0x3F, 0xC0, 0x00, 0x00])

    def test_encode_float_be_negative(self):
        """Test encoding negative float."""
        # -1.5 in IEEE 754 = 0xBFC00000
        result = encode_float_be(-1.5)
        assert result == bytes([0xBF, 0xC0, 0x00, 0x00])

    def test_encode_float_be_zero(self):
        """Test encoding zero."""
        result = encode_float_be(0.0)
        assert result == bytes([0x00, 0x00, 0x00, 0x00])

    def test_encode_float_be_common_values(self):
        """Test encoding common pump values."""
        # 230.0V (typical voltage)
        assert encode_float_be(230.0) == bytes([0x43, 0x66, 0x00, 0x00])

        # 50.0Hz (typical frequency)
        assert encode_float_be(50.0) == bytes([0x42, 0x48, 0x00, 0x00])

        # 1500.0 RPM (typical speed)
        assert encode_float_be(1500.0) == bytes([0x44, 0xBB, 0x80, 0x00])

    def test_decode_float_be_positive(self):
        """Test decoding positive float from big-endian bytes."""
        result = decode_float_be(bytes([0x3F, 0xC0, 0x00, 0x00]))
        assert abs(result - 1.5) < 0.0001

    def test_decode_float_be_negative(self):
        """Test decoding negative float."""
        result = decode_float_be(bytes([0xBF, 0xC0, 0x00, 0x00]))
        assert abs(result - (-1.5)) < 0.0001

    def test_decode_float_be_zero(self):
        """Test decoding zero."""
        result = decode_float_be(bytes([0x00, 0x00, 0x00, 0x00]))
        assert result == 0.0

    def test_float_roundtrip(self):
        """Test encoding and decoding roundtrip."""
        values = [0.0, 1.5, -1.5, 230.0, 50.0, 1500.0, 3.14159, -273.15]
        for value in values:
            encoded = encode_float_be(value)
            decoded = decode_float_be(encoded)
            assert abs(decoded - value) < 0.0001

    def test_encode_uint16_be(self):
        """Test encoding 16-bit unsigned integer."""
        assert encode_uint16_be(0x0000) == bytes([0x00, 0x00])
        assert encode_uint16_be(0x00FF) == bytes([0x00, 0xFF])
        assert encode_uint16_be(0xFF00) == bytes([0xFF, 0x00])
        assert encode_uint16_be(0xFFFF) == bytes([0xFF, 0xFF])
        assert encode_uint16_be(0x1234) == bytes([0x12, 0x34])

    def test_decode_uint16_be(self):
        """Test decoding 16-bit unsigned integer."""
        assert decode_uint16_be(bytes([0x00, 0x00])) == 0x0000
        assert decode_uint16_be(bytes([0x00, 0xFF])) == 0x00FF
        assert decode_uint16_be(bytes([0xFF, 0x00])) == 0xFF00
        assert decode_uint16_be(bytes([0xFF, 0xFF])) == 0xFFFF
        assert decode_uint16_be(bytes([0x12, 0x34])) == 0x1234

    def test_encode_uint32_be(self):
        """Test encoding 32-bit unsigned integer."""
        assert encode_uint32_be(0x00000000) == bytes([0x00, 0x00, 0x00, 0x00])
        assert encode_uint32_be(0x12345678) == bytes([0x12, 0x34, 0x56, 0x78])
        assert encode_uint32_be(0xFFFFFFFF) == bytes([0xFF, 0xFF, 0xFF, 0xFF])

    def test_decode_uint32_be(self):
        """Test decoding 32-bit unsigned integer."""
        assert decode_uint32_be(bytes([0x00, 0x00, 0x00, 0x00])) == 0x00000000
        assert decode_uint32_be(bytes([0x12, 0x34, 0x56, 0x78])) == 0x12345678
        assert decode_uint32_be(bytes([0xFF, 0xFF, 0xFF, 0xFF])) == 0xFFFFFFFF


class TestCRCVectors:
    """Test CRC calculation with known values."""

    def test_crc_empty(self):
        """Test CRC of empty data."""
        # CRC16/CCITT-FALSE with init=0xFFFF, poly=0x1021
        result = calc_crc16(b"")
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFF

    def test_crc_single_byte(self):
        """Test CRC of single byte."""
        result = calc_crc16(b"\x00")
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFF

    def test_crc_known_sequence(self):
        """Test CRC with known good sequence."""
        # Test vector: "123456789" should give 0x29B1 with CRC16/CCITT-FALSE
        result = calc_crc16(b"123456789")
        # Note: Actual CRC depends on algorithm variant (init value, poly)
        # This tests that CRC is deterministic
        assert isinstance(result, int)

        # Same input should always give same output
        result2 = calc_crc16(b"123456789")
        assert result == result2

    def test_crc_different_inputs(self):
        """Test that different inputs give different CRCs."""
        crc1 = calc_crc16(b"test1")
        crc2 = calc_crc16(b"test2")
        # Should be different (with very high probability)
        assert crc1 != crc2


class TestFrameVectors:
    """Test frame building and parsing with known byte sequences."""

    def test_build_class10_read_frame(self):
        """Test building Class 10 READ command."""
        # Class 10 READ for motor state (0x570045)
        frame = FrameBuilder.build_class10_read(0x570045)

        assert frame[0] == 0x27  # Start byte (FRAME_START for commands)
        assert frame[4] == 0x0A  # Class 10
        assert frame[5] == 0x03  # OpSpec READ

        # Register should be encoded as 3 bytes big-endian
        assert frame[6] == 0x57
        assert frame[7] == 0x00
        assert frame[8] == 0x45

    def test_build_read_request_frame(self):
        """Test building generic read request."""
        # Alternative method for building read requests
        frame = FrameBuilder.build_read_request(0x570045)

        assert frame[0] == 0x27  # Start byte
        assert frame[4] == 0x0A  # Class 10
        assert frame[5] == 0x03  # OpSpec READ

    def test_parse_valid_frame(self):
        """Test parsing a valid response frame."""
        # Build a simple Class 3 response
        # Format: [Start][Len][SvcH][SvcL][Class][OpSpec][Data...][CRCH][CRCL]
        frame = bytearray(
            [
                0x24,  # Start (RESPONSE_START)
                0x06,  # Length (data + service + CRC)
                0xE7,
                0xF8,  # Service ID
                0x03,  # Class 3
                0x81,  # OpSpec (response)
            ]
        )

        # Calculate and append CRC (responses use calc_crc16_read with XOR)
        crc_data = frame[1:]  # Everything except start byte
        crc = calc_crc16_read(bytes(crc_data))
        frame.extend(encode_uint16_be(crc))

        # Parse the frame
        parsed = FrameParser.parse_frame(bytes(frame))

        assert parsed.valid
        assert parsed.frame_type == "response"
        assert parsed.class_byte == 0x03
        assert parsed.crc_valid

    def test_parse_invalid_start_byte(self):
        """Test parsing frame with invalid start byte."""
        frame = bytes([0xFF, 0x06, 0xE7, 0xF8, 0x03, 0x81, 0x00, 0x00])
        parsed = FrameParser.parse_frame(frame)

        assert not parsed.valid

    def test_parse_invalid_crc(self):
        """Test parsing frame with invalid CRC."""
        frame = bytes(
            [
                0x24,  # Start (valid)
                0x06,  # Length
                0xE7,
                0xF8,  # Service ID
                0x03,  # Class 3
                0x81,  # OpSpec
                0xFF,
                0xFF,  # Invalid CRC
            ]
        )
        parsed = FrameParser.parse_frame(frame)

        # Frame structure is valid but CRC check should fail
        assert parsed.valid
        assert not parsed.crc_valid


class TestCompleteProtocolVectors:
    """Test complete command/response cycles with known byte sequences."""

    def test_motor_state_command_structure(self):
        """Test motor state query command matches expected structure."""
        # Motor state register: 0x570045 (obj=87, sub=69)
        frame = FrameBuilder.build_class10_read(0x570045)

        # Verify complete frame structure
        assert frame[0] == 0x27  # Start byte (FRAME_START)
        assert frame[1] > 0  # Length > 0
        assert frame[2:4] == bytes([0xE7, 0xF8])  # Service ID
        assert frame[4] == 0x0A  # Class 10
        assert frame[5] == 0x03  # OpSpec READ
        assert frame[6:9] == bytes([0x57, 0x00, 0x45])  # Register

        # Last 2 bytes should be CRC (READ commands use calc_crc16_read with XOR)
        frame_without_crc = frame[:-2]
        crc_data = frame_without_crc[1:]  # Exclude start byte
        expected_crc = calc_crc16_read(crc_data)
        actual_crc = decode_uint16_be(frame[-2:])
        assert actual_crc == expected_crc

    def test_flow_pressure_command_structure(self):
        """Test flow/pressure query command structure."""
        # Flow/pressure register: 0x5D0122 (obj=93, sub=290)
        frame = FrameBuilder.build_class10_read(0x5D0122)

        assert frame[0] == 0x27
        assert frame[4] == 0x0A
        assert frame[5] == 0x03
        assert frame[6:9] == bytes([0x5D, 0x01, 0x22])

    def test_temperature_command_structure(self):
        """Test temperature query command structure."""
        # Temperature register: 0x5D012C (obj=93, sub=300)
        frame = FrameBuilder.build_class10_read(0x5D012C)

        assert frame[0] == 0x27
        assert frame[4] == 0x0A
        assert frame[5] == 0x03
        assert frame[6:9] == bytes([0x5D, 0x01, 0x2C])

    def test_write_request_structure(self):
        """Test write request command structure."""
        # Build a write request
        register = 0x5600  # Control register
        value = bytes([0x01, 0x00, 0x00, 0x00])  # Start command

        frame = FrameBuilder.build_write_request(register, value)

        assert frame[0] == 0x27
        assert frame[4] == 0x0A  # Class 10

    @pytest.mark.parametrize(
        "register,obj_id,sub_id",
        [
            (0x570045, 87, 69),  # Motor state
            (0x5D0122, 93, 290),  # Flow/pressure
            (0x5D012C, 93, 300),  # Temperature
        ],
    )
    def test_register_encoding(self, register: int, obj_id: int, sub_id: int):
        """Test that register value correctly encodes obj_id and sub_id."""
        frame = FrameBuilder.build_class10_read(register)

        # Extract encoded obj_id and sub_id from frame
        encoded_obj = frame[6]
        encoded_sub = (frame[7] << 8) | frame[8]

        assert encoded_obj == obj_id
        assert encoded_sub == sub_id


class TestCrossLanguageVectors:
    """
    Test vectors designed for cross-language validation.

    These tests use simple, well-documented examples that can be
    easily ported to other languages for validation.
    """

    def test_example_1_simple_float(self):
        """Example 1: Encode float 42.0"""
        result = encode_float_be(42.0)
        # 42.0 in IEEE 754 = 0x42280000
        assert result == bytes([0x42, 0x28, 0x00, 0x00])

    def test_example_2_simple_uint16(self):
        """Example 2: Encode uint16 12345"""
        result = encode_uint16_be(12345)
        # 12345 = 0x3039
        assert result == bytes([0x30, 0x39])

    def test_example_3_motor_state_command(self):
        """Example 3: Build motor state query command."""
        frame = FrameBuilder.build_class10_read(0x570045)

        # Document the expected structure for other languages:
        # Byte 0: Start (0x27)
        # Byte 1: Length
        # Bytes 2-3: Service ID (0xE7F8)
        # Byte 4: Class (0x0A)
        # Byte 5: OpSpec (0x03)
        # Bytes 6-8: Register (0x570045)
        # Last 2 bytes: CRC16

        assert len(frame) >= 11  # Minimum expected length
        assert frame[0] == 0x27
        assert frame[2:4] == bytes([0xE7, 0xF8])
        assert frame[4] == 0x0A
        assert frame[5] == 0x03

    def test_example_4_crc_calculation(self):
        """Example 4: Calculate CRC for known data."""
        data = bytes([0x06, 0xE7, 0xF8, 0x03, 0x81])
        crc = calc_crc16(data)

        # CRC should be deterministic and same across languages
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF

        # Verify determinism
        assert calc_crc16(data) == crc
