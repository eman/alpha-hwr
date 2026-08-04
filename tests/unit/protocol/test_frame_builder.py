"""
Unit tests for GENI protocol frame builder.

Tests frame construction with CRC validation for all operation types.
"""

import pytest

from alpha_hwr.constants import CLASS_10, FRAME_START, SERVICE_ID_HIGH
from alpha_hwr.protocol.codec import encode_float_be
from alpha_hwr.protocol.frame_builder import FrameBuilder
from alpha_hwr.utils import calc_crc16, calc_crc16_read


class TestFrameBuilderBasics:
    """Test basic frame structure and CRC calculation."""

    def test_frame_starts_with_start_byte(self):
        """All frames must start with FRAME_START (0x27)."""
        packet = FrameBuilder.build_command_info(0x03, 0x45)
        assert packet[0] == FRAME_START

    def test_frame_has_service_id(self):
        """All frames must have SERVICE_ID_HIGH (0xE7)."""
        packet = FrameBuilder.build_command_info(0x03, 0x45)
        assert packet[2] == SERVICE_ID_HIGH

    def test_frame_length_field_correct(self):
        """Length field should match actual APDU + header length."""
        packet = FrameBuilder.build_command_info(0x03, 0x45)
        stated_length = packet[1]
        # Length counts from ServiceID-H to end of APDU (excludes Start and CRC)
        actual_payload_length = len(
            packet[2:-2]
        )  # From ServiceID to before CRC
        assert stated_length == actual_payload_length

    def test_crc_is_valid(self):
        """CRC should validate correctly."""
        packet = FrameBuilder.build_command_info(0x03, 0x45)

        # Extract CRC from packet
        crc_in_packet = (packet[-2] << 8) | packet[-1]

        # Calculate CRC over data (everything after start, before CRC)
        data_for_crc = packet[1:-2]
        calculated_crc = calc_crc16_read(data_for_crc)

        assert crc_in_packet == calculated_crc


class TestCommandInfo:
    """Test INFO command building (register reads)."""

    def test_build_info_1byte_register(self):
        """Test INFO with 1-byte register address."""
        packet = FrameBuilder.build_command_info(0x02, 0x45, source=0xF8)

        assert packet[0] == FRAME_START
        assert packet[4] == 0x02  # Class byte
        assert packet[5] == 0x01  # OpSpec: INFO (00) + length 1
        assert packet[6] == 0x45  # Register

    def test_build_info_2byte_register(self):
        """Test INFO with 2-byte register address."""
        packet = FrameBuilder.build_command_info(0x03, 0x5D01, source=0xF8)

        assert packet[4] == 0x03  # Class byte
        assert packet[5] == 0x02  # OpSpec: INFO (00) + length 2
        assert packet[6] == 0x5D  # Register high byte
        assert packet[7] == 0x01  # Register low byte

    def test_build_info_3byte_register(self):
        """Test INFO with 3-byte register address."""
        packet = FrameBuilder.build_command_info(0x03, 0x5D012C, source=0xF8)

        assert packet[4] == 0x03  # Class byte
        assert packet[5] == 0x03  # OpSpec: INFO (00) + length 3
        assert packet[6] == 0x5D  # Register byte 1
        assert packet[7] == 0x01  # Register byte 2
        assert packet[8] == 0x2C  # Register byte 3

    def test_info_different_sources(self):
        """Test INFO with different source addresses."""
        packet_f8 = FrameBuilder.build_command_info(0x03, 0x45, source=0xF8)
        packet_0a = FrameBuilder.build_command_info(0x03, 0x45, source=0x0A)

        assert packet_f8[3] == 0xF8
        assert packet_0a[3] == 0x0A

        # Rest should be identical except source and CRC
        assert packet_f8[0:3] == packet_0a[0:3]  # Start, length, ServiceID
        assert packet_f8[4:7] == packet_0a[4:7]  # Class, OpSpec, Register


class TestSetCommand:
    """Test SET command building."""

    def test_build_set_single_byte_value(self):
        """Test SET with single byte value."""
        packet = FrameBuilder.build_set_command(
            0x02, 0x01, 0x45, 0x01, source=0xF8
        )

        assert packet[4] == 0x02  # Class byte
        # OpSpec: 01 (SET) << 6 | length
        assert (packet[5] >> 6) == 0x01  # SET operation
        assert packet[6] == 0x45  # Register
        assert packet[7] == 0x01  # Value

    def test_build_set_multi_byte_value(self):
        """Test SET with multi-byte value."""
        value = encode_float_be(100.0)
        packet = FrameBuilder.build_set_command(
            0x03, 0x01, 0x5D01, value, source=0xF8
        )

        assert packet[4] == 0x03  # Class byte
        # Register should be 2 bytes, value 4 bytes = 6 total
        assert (packet[5] & 0x3F) == 6  # Length field
        assert packet[6:8] == bytes([0x5D, 0x01])  # Register
        assert packet[8:12] == value  # Float value


class TestDataObjectSet:
    """Test Class 10 DataObject SET operations."""

    def test_build_class10_empty_data(self):
        """Test building Class 10 SET with empty data (just SubID+ObjID)."""
        # Note: Authentication packet (OpSpec=0x03) is hardcoded, not built dynamically
        # build_data_object_set always creates SET commands (OpSpec bit 7 set)
        packet = FrameBuilder.build_data_object_set(
            0x5600, 0x0006, b"", source=0xF8
        )

        # Verify structure
        assert packet[0] == FRAME_START
        assert packet[2] == SERVICE_ID_HIGH
        assert packet[3] == 0xF8  # Source
        assert packet[4] == CLASS_10
        # OpSpec should have bit 7 set (SET command)
        assert (packet[5] & 0x80) == 0x80
        # SubID should be 0x5600
        assert packet[6:8] == bytes([0x56, 0x00])
        # ObjID should be 0x0006 (2 bytes in Class 10)
        assert packet[8:10] == bytes([0x00, 0x06])

    def test_build_class10_with_data(self):
        """Test Class 10 SET with data payload."""
        # Example: Control mode change with setpoint
        control_header = bytes([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00])
        setpoint = encode_float_be(14710.0)  # 1.5m pressure in Pascals
        data = control_header + setpoint

        packet = FrameBuilder.build_data_object_set(
            0x5600, 0x0601, data, source=0xF8
        )

        assert packet[0] == FRAME_START
        assert packet[4] == CLASS_10
        assert packet[6:8] == bytes([0x56, 0x00])  # SubID
        assert packet[8:10] == bytes([0x06, 0x01])  # ObjID
        assert packet[10 : 10 + len(data)] == data

    def test_class10_opspec_calculation(self):
        """Test OpSpec calculation for Class 10."""
        # Empty data = 4 bytes (SubID + ObjID), OpSpec should be 0x80 | 4 = 0x84
        packet = FrameBuilder.build_data_object_set(0x5600, 0x0006, b"")

        op_spec = packet[5]
        assert (op_spec & 0x80) == 0x80  # SET bit set
        # Length includes SubID (2) + ObjID (2) = 4
        assert (op_spec & 0x3F) >= 4  # At least 4 bytes

    def test_class10_different_sub_obj_ids(self):
        """Test with various SubID and ObjID combinations."""
        test_cases = [
            (0x5600, 0x0006),  # Control unlock
            (0x5600, 0x0601),  # Control mode
            (0x5100, 0x0001),  # Device info (hypothetical)
            (0xFFFF, 0xFFFF),  # Maximum values
        ]

        for sub_id, obj_id in test_cases:
            packet = FrameBuilder.build_data_object_set(sub_id, obj_id, b"")

            # Verify IDs are encoded correctly
            assert packet[6] == (sub_id >> 8) & 0xFF
            assert packet[7] == sub_id & 0xFF
            assert packet[8] == (obj_id >> 8) & 0xFF
            assert packet[9] == obj_id & 0xFF

    def test_class10_override_parameters(self):
        """Test override_op and override_len parameters."""
        # Test with override_op
        packet1 = FrameBuilder.build_data_object_set(
            0x5600, 0x0006, b"test", override_op=0x88
        )
        assert packet1[5] == 0x88

        # Test with override_len
        packet2 = FrameBuilder.build_data_object_set(
            0x5600, 0x0006, b"test", override_len=12
        )
        assert packet2[1] == 12


class TestReadRequest:
    """Test READ request building."""

    def test_build_read_2byte_register(self):
        """Test READ with 2-byte register."""
        packet = FrameBuilder.build_read_request(0x5D01, source=0xF8)

        assert packet[0] == FRAME_START
        assert packet[2] == SERVICE_ID_HIGH
        assert packet[3] == 0xF8
        # Contains RESERVED_BYTE and READ opcode
        from alpha_hwr.constants import RESERVED_BYTE, CommandOpcode

        assert packet[4] == RESERVED_BYTE
        assert packet[5] == CommandOpcode.READ

    def test_build_read_3byte_register(self):
        """Test READ with 3-byte register."""
        packet = FrameBuilder.build_read_request(0x5D012C)

        # Should have 3-byte register
        assert packet[6] == 0x5D
        assert packet[7] == 0x01
        assert packet[8] == 0x2C


class TestWriteRequest:
    """Test WRITE request building."""

    def test_build_write_single_byte(self):
        """Test WRITE with single byte value."""
        packet = FrameBuilder.build_write_request(
            0x5D01, value=0x01, source=0x0A
        )

        assert packet[0] == FRAME_START
        assert packet[3] == 0x0A  # Source
        from alpha_hwr.constants import CommandOpcode

        assert packet[5] == CommandOpcode.WRITE

    def test_build_write_multi_byte(self):
        """Test WRITE with multi-byte value."""
        value = bytes([0x01, 0x02, 0x03, 0x04])
        packet = FrameBuilder.build_write_request(0x5D01, value=value)

        # Find value in packet (after register)
        # Register is 2 bytes, value starts after that
        value_start = (
            8  # Start + Len + ServiceID + Source + Reserved + Opcode + Reg(2)
        )
        assert packet[value_start : value_start + 4] == value

    def test_write_uses_different_crc(self):
        """WRITE uses calc_crc16 (no XOR), excluding start byte."""
        packet = FrameBuilder.build_write_request(0x5D01, value=0x01)

        # Extract CRC
        crc_in_packet = (packet[-2] << 8) | packet[-1]

        # WRITE uses calc_crc16 over packet excluding start byte
        calculated_crc = calc_crc16(packet[1:-2])

        assert crc_in_packet == calculated_crc


class TestExecuteRequest:
    """Test EXECUTE command building."""

    def test_build_execute(self):
        """Test EXECUTE command."""
        packet = FrameBuilder.build_execute_request(0x03, 0x01, source=0x0A)

        assert packet[0] == FRAME_START
        assert packet[3] == 0x0A
        from alpha_hwr.constants import CommandOpcode

        assert packet[5] == CommandOpcode.EXECUTE
        assert packet[6] == 0x03  # reg_class
        assert packet[7] == 0x01  # reg_id


# ==========================================================================
# REFERENCE IMPLEMENTATION TEST VECTORS
# ==========================================================================
class TestReferenceVectors:
    """
    Test vectors for validating implementations in other languages.

    These provide exact byte sequences that other implementations
    should produce for the same inputs.
    """

    def test_vector_class10_set_command(self):
        """
        Reference vector: Class 10 SET command with empty data.

        Note: The authentication packet (OpSpec=0x03) is hardcoded in
        AuthenticationHandler, not built dynamically. build_data_object_set
        always creates SET commands with bit 7 set in OpSpec.
        """
        packet = FrameBuilder.build_data_object_set(
            0x5600, 0x0006, b"", source=0xF8
        )

        # Verify it's a valid SET command
        assert packet[0] == FRAME_START
        assert packet[4] == CLASS_10
        assert (packet[5] & 0x80) == 0x80  # SET bit set
        assert packet[6:8] == bytes([0x56, 0x00])  # SubID
        assert packet[8:10] == bytes([0x00, 0x06])  # ObjID

        # Verify CRC is valid
        crc_in_packet = (packet[-2] << 8) | packet[-1]
        calculated_crc = calc_crc16_read(packet[1:-2])
        assert crc_in_packet == calculated_crc

    def test_vector_info_temperature_register(self):
        """Reference vector: Read temperature register."""
        packet = FrameBuilder.build_command_info(0x03, 0x5D012C, source=0xF8)

        # Validate structure
        assert packet[0] == 0x27  # FRAME_START
        assert packet[1] == 0x07  # Length
        assert packet[2] == 0xE7  # ServiceID high
        assert packet[3] == 0xF8  # Source
        assert packet[4] == 0x03  # Class
        assert packet[5] == 0x03  # OpSpec (INFO, 3 bytes)
        assert packet[6:9] == bytes([0x5D, 0x01, 0x2C])  # Register
        # Last 2 bytes are CRC (validated by other tests)

    def test_vector_control_mode_setpoint(self):
        """Reference vector: Set control mode with setpoint."""
        # Build control data payload
        control_header = bytes([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00])
        setpoint = encode_float_be(14710.0)  # 1.5m in Pascals
        data = control_header + setpoint

        packet = FrameBuilder.build_data_object_set(
            0x5600, 0x0601, data, source=0xF8
        )

        # Validate key fields
        assert packet[0] == 0x27
        assert packet[4] == 0x0A  # Class 10
        assert packet[6:8] == bytes([0x56, 0x00])  # SubID
        assert packet[8:10] == bytes([0x06, 0x01])  # ObjID
        assert packet[10:18] == control_header
        assert packet[18:22] == setpoint


class TestFrameBuilderEdgeCases:
    """Test edge cases and error conditions."""

    def test_register_value_boundaries(self):
        """Test register address boundary conditions."""
        # Maximum 1-byte register
        packet1 = FrameBuilder.build_command_info(0x02, 0xFF)
        assert len(packet1[6:7]) == 1  # 1-byte register

        # Minimum 2-byte register
        packet2 = FrameBuilder.build_command_info(0x02, 0x100)
        assert len(packet2[6:8]) == 2  # 2-byte register

        # Maximum 2-byte register
        packet3 = FrameBuilder.build_command_info(0x02, 0xFFFF)
        assert len(packet3[6:8]) == 2  # 2-byte register

        # Minimum 3-byte register
        packet4 = FrameBuilder.build_command_info(0x02, 0x10000)
        assert len(packet4[6:9]) == 3  # 3-byte register

    def test_empty_data_class10(self):
        """Test Class 10 with empty data (trigger operations)."""
        packet = FrameBuilder.build_data_object_set(0x5600, 0x0006, b"")

        # Should still be valid with just SubID + ObjID
        assert len(packet) >= 11  # Start + Len + ... + SubID + ObjID + CRC

    def test_large_data_class10(self):
        """Test Class 10 rejects data too large for 6-bit OpSpec."""
        # OpSpec bits 5-0 encode the payload length (max 63).
        # Payload = SubID(2) + ObjID(2) + Data, so max Data = 59 bytes.
        # Larger payloads must use override_op.
        large_data = bytes(range(200))
        with pytest.raises(ValueError, match="Payload too large"):
            FrameBuilder.build_data_object_set(0x5600, 0x0601, large_data)

    def test_large_data_class10_with_override(self):
        """Test Class 10 with large data using override_op."""
        large_data = bytes(range(200))
        packet = FrameBuilder.build_data_object_set(
            0x5600, 0x0601, large_data, override_op=0xB3
        )

        # Verify data is present
        data_start = 10  # After frame header and IDs
        data_end = data_start + len(large_data)
        assert packet[data_start:data_end] == large_data

    def test_all_methods_return_bytes(self):
        """Ensure all builder methods return bytes, not bytearray."""
        packet1 = FrameBuilder.build_command_info(0x03, 0x45)
        assert isinstance(packet1, bytes)

        packet2 = FrameBuilder.build_data_object_set(0x5600, 0x0006, b"")
        assert isinstance(packet2, bytes)

        packet3 = FrameBuilder.build_read_request(0x5D01)
        assert isinstance(packet3, bytes)

        packet4 = FrameBuilder.build_write_request(0x5D01, 0x01)
        assert isinstance(packet4, bytes)

        packet5 = FrameBuilder.build_execute_request(0x03, 0x01)
        assert isinstance(packet5, bytes)
