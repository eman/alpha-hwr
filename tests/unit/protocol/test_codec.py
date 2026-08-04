"""
Unit tests for protocol codec module.

Tests encoding and decoding of primitive types used in GENI protocol.
All values use big-endian byte order.
"""

from alpha_hwr.protocol.codec import (
    decode_float_be,
    decode_int16_be,
    decode_uint16_be,
    decode_uint32_be,
    encode_float_be,
    encode_int16_be,
    encode_uint16_be,
    encode_uint32_be,
)


class TestFloatCodec:
    """Test big-endian float encoding/decoding."""

    def test_encode_positive_float(self):
        """Test encoding positive float values."""
        assert encode_float_be(1.5) == bytes([0x3F, 0xC0, 0x00, 0x00])
        assert encode_float_be(100.0) == bytes([0x42, 0xC8, 0x00, 0x00])
        assert encode_float_be(9806.65) == bytes([0x46, 0x19, 0x3A, 0x9A])

    def test_encode_negative_float(self):
        """Test encoding negative float values."""
        assert encode_float_be(-1.5) == bytes([0xBF, 0xC0, 0x00, 0x00])
        assert encode_float_be(-100.0) == bytes([0xC2, 0xC8, 0x00, 0x00])

    def test_encode_zero(self):
        """Test encoding zero."""
        assert encode_float_be(0.0) == bytes([0x00, 0x00, 0x00, 0x00])

    def test_decode_positive_float(self):
        """Test decoding positive float values."""
        assert decode_float_be(bytes([0x3F, 0xC0, 0x00, 0x00])) == 1.5
        assert decode_float_be(bytes([0x42, 0xC8, 0x00, 0x00])) == 100.0
        # Use approximate comparison for float precision
        result = decode_float_be(bytes([0x46, 0x19, 0x3A, 0x9A]))
        assert result is not None
        assert abs(result - 9806.65) < 0.01

    def test_decode_negative_float(self):
        """Test decoding negative float values."""
        assert decode_float_be(bytes([0xBF, 0xC0, 0x00, 0x00])) == -1.5
        assert decode_float_be(bytes([0xC2, 0xC8, 0x00, 0x00])) == -100.0

    def test_decode_zero(self):
        """Test decoding zero."""
        assert decode_float_be(bytes([0x00, 0x00, 0x00, 0x00])) == 0.0

    def test_decode_with_offset(self):
        """Test decoding float at different offsets."""
        data = bytes([0xFF, 0xFF, 0x3F, 0xC0, 0x00, 0x00, 0xFF])
        assert decode_float_be(data, offset=2) == 1.5
        assert decode_float_be(data, offset=0) is not None  # Valid but garbage

    def test_decode_insufficient_bytes(self):
        """Test decoding returns None when insufficient bytes."""
        assert decode_float_be(bytes([0x3F, 0xC0])) is None
        assert decode_float_be(bytes([0x3F, 0xC0, 0x00]), offset=0) is None
        assert (
            decode_float_be(bytes([0x00, 0x00, 0x00, 0x00, 0x00]), offset=2)
            is None
        )

    def test_round_trip(self):
        """Test encoding then decoding returns original value."""
        test_values = [0.0, 1.5, -1.5, 100.0, -100.0, 3.14159, 2500.0]
        for value in test_values:
            encoded = encode_float_be(value)
            decoded = decode_float_be(encoded)
            assert decoded is not None
            assert abs(decoded - value) < 0.0001  # Float precision


class TestUint16Codec:
    """Test big-endian uint16 encoding/decoding."""

    def test_encode_uint16(self):
        """Test encoding uint16 values."""
        assert encode_uint16_be(0) == bytes([0x00, 0x00])
        assert encode_uint16_be(1000) == bytes([0x03, 0xE8])
        assert encode_uint16_be(65535) == bytes([0xFF, 0xFF])
        assert encode_uint16_be(2500) == bytes([0x09, 0xC4])

    def test_decode_uint16(self):
        """Test decoding uint16 values."""
        assert decode_uint16_be(bytes([0x00, 0x00])) == 0
        assert decode_uint16_be(bytes([0x03, 0xE8])) == 1000
        assert decode_uint16_be(bytes([0xFF, 0xFF])) == 65535
        assert decode_uint16_be(bytes([0x09, 0xC4])) == 2500

    def test_decode_with_offset(self):
        """Test decoding uint16 at offset."""
        data = bytes([0xFF, 0x03, 0xE8, 0xFF])
        assert decode_uint16_be(data, offset=1) == 1000

    def test_decode_insufficient_bytes(self):
        """Test decoding returns None when insufficient bytes."""
        assert decode_uint16_be(bytes([0x03])) is None
        assert decode_uint16_be(bytes([0x00, 0x00]), offset=1) is None

    def test_round_trip(self):
        """Test encoding then decoding returns original value."""
        test_values = [0, 1, 255, 256, 1000, 32767, 32768, 65535]
        for value in test_values:
            encoded = encode_uint16_be(value)
            decoded = decode_uint16_be(encoded)
            assert decoded == value


class TestUint32Codec:
    """Test big-endian uint32 encoding/decoding."""

    def test_encode_uint32(self):
        """Test encoding uint32 values."""
        assert encode_uint32_be(0) == bytes([0x00, 0x00, 0x00, 0x00])
        assert encode_uint32_be(1234567890) == bytes([0x49, 0x96, 0x02, 0xD2])
        assert encode_uint32_be(4294967295) == bytes([0xFF, 0xFF, 0xFF, 0xFF])

    def test_decode_uint32(self):
        """Test decoding uint32 values."""
        assert decode_uint32_be(bytes([0x00, 0x00, 0x00, 0x00])) == 0
        assert decode_uint32_be(bytes([0x49, 0x96, 0x02, 0xD2])) == 1234567890
        assert decode_uint32_be(bytes([0xFF, 0xFF, 0xFF, 0xFF])) == 4294967295

    def test_decode_with_offset(self):
        """Test decoding uint32 at offset."""
        data = bytes([0xFF, 0xFF, 0x49, 0x96, 0x02, 0xD2, 0xFF])
        assert decode_uint32_be(data, offset=2) == 1234567890

    def test_decode_insufficient_bytes(self):
        """Test decoding returns None when insufficient bytes."""
        assert decode_uint32_be(bytes([0x49, 0x96, 0x02])) is None

    def test_round_trip(self):
        """Test encoding then decoding returns original value."""
        test_values = [0, 1, 1000, 1234567890, 4294967295]
        for value in test_values:
            encoded = encode_uint32_be(value)
            decoded = decode_uint32_be(encoded)
            assert decoded == value


class TestInt16Codec:
    """Test big-endian int16 (signed) encoding/decoding."""

    def test_encode_positive(self):
        """Test encoding positive int16 values."""
        assert encode_int16_be(0) == bytes([0x00, 0x00])
        assert encode_int16_be(1000) == bytes([0x03, 0xE8])
        assert encode_int16_be(32767) == bytes([0x7F, 0xFF])

    def test_encode_negative(self):
        """Test encoding negative int16 values."""
        assert encode_int16_be(-1) == bytes([0xFF, 0xFF])
        assert encode_int16_be(-1000) == bytes([0xFC, 0x18])
        assert encode_int16_be(-32768) == bytes([0x80, 0x00])

    def test_decode_positive(self):
        """Test decoding positive int16 values."""
        assert decode_int16_be(bytes([0x00, 0x00])) == 0
        assert decode_int16_be(bytes([0x03, 0xE8])) == 1000
        assert decode_int16_be(bytes([0x7F, 0xFF])) == 32767

    def test_decode_negative(self):
        """Test decoding negative int16 values."""
        assert decode_int16_be(bytes([0xFF, 0xFF])) == -1
        assert decode_int16_be(bytes([0xFC, 0x18])) == -1000
        assert decode_int16_be(bytes([0x80, 0x00])) == -32768

    def test_round_trip(self):
        """Test encoding then decoding returns original value."""
        test_values = [-32768, -1000, -1, 0, 1, 1000, 32767]
        for value in test_values:
            encoded = encode_int16_be(value)
            decoded = decode_int16_be(encoded)
            assert decoded == value


class TestCodecEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_bytes(self):
        """Test decoding empty byte arrays."""
        assert decode_float_be(b"") is None
        assert decode_uint16_be(b"") is None
        assert decode_uint32_be(b"") is None
        assert decode_int16_be(b"") is None

    def test_special_float_values(self):
        """Test special float values (inf, nan)."""
        import math

        # Infinity
        encoded_inf = encode_float_be(math.inf)
        decoded_inf = decode_float_be(encoded_inf)
        assert decoded_inf is not None
        assert math.isinf(decoded_inf)

        # NaN
        encoded_nan = encode_float_be(math.nan)
        decoded_nan = decode_float_be(encoded_nan)
        assert decoded_nan is not None
        assert math.isnan(decoded_nan)

    def test_large_offset(self):
        """Test offset beyond data length."""
        data = bytes([0x00, 0x00, 0x00, 0x00])
        assert decode_float_be(data, offset=10) is None
        assert decode_uint16_be(data, offset=10) is None


# ==========================================================================
# REFERENCE IMPLEMENTATION TESTS
# ==========================================================================
class TestReferenceVectors:
    """
    Test vectors for validating implementations in other languages.

    These tests use exact byte sequences that can be ported to other
    languages to validate their codec implementations.
    """

    def test_float_reference_vectors(self):
        """Reference test vectors for float encoding."""
        vectors = [
            (1.5, bytes([0x3F, 0xC0, 0x00, 0x00])),
            (100.0, bytes([0x42, 0xC8, 0x00, 0x00])),
            (-1.5, bytes([0xBF, 0xC0, 0x00, 0x00])),
            (0.0, bytes([0x00, 0x00, 0x00, 0x00])),
        ]

        for value, expected_bytes in vectors:
            # Test encoding
            assert encode_float_be(value) == expected_bytes, (
                f"Encoding {value} failed"
            )

            # Test decoding
            decoded = decode_float_be(expected_bytes)
            assert decoded is not None
            assert abs(decoded - value) < 0.0001, (
                f"Decoding {expected_bytes.hex()} failed"
            )

    def test_uint16_reference_vectors(self):
        """Reference test vectors for uint16 encoding."""
        vectors = [
            (0, bytes([0x00, 0x00])),
            (1000, bytes([0x03, 0xE8])),
            (65535, bytes([0xFF, 0xFF])),
            (2500, bytes([0x09, 0xC4])),
        ]

        for value, expected_bytes in vectors:
            assert encode_uint16_be(value) == expected_bytes
            assert decode_uint16_be(expected_bytes) == value

    def test_uint32_reference_vectors(self):
        """Reference test vectors for uint32 encoding."""
        vectors = [
            (0, bytes([0x00, 0x00, 0x00, 0x00])),
            (1234567890, bytes([0x49, 0x96, 0x02, 0xD2])),
            (4294967295, bytes([0xFF, 0xFF, 0xFF, 0xFF])),
        ]

        for value, expected_bytes in vectors:
            assert encode_uint32_be(value) == expected_bytes
            assert decode_uint32_be(expected_bytes) == value

    def test_pressure_conversion_vector(self):
        """
        Test vector for pressure conversion (common in pump control).

        Pressure setpoint: 1.5 meters of water column
        Pascals: 1.5 * 9806.65 = 14709.975 Pa
        Encoded as float: 0x4565704X (approximately)
        """
        pressure_m = 1.5
        pressure_pa = pressure_m * 9806.65
        encoded = encode_float_be(pressure_pa)
        decoded = decode_float_be(encoded)

        assert decoded is not None
        # Allow 0.1 Pa tolerance for float precision
        assert abs(decoded - pressure_pa) < 0.1

        # Verify we can convert back
        recovered_m = decoded / 9806.65
        assert abs(recovered_m - pressure_m) < 0.001
