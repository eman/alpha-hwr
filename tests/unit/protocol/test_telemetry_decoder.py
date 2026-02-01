"""
Unit tests for telemetry_decoder.py

Tests the telemetry decoder with various payload types and edge cases.
"""

import pytest
import struct

from alpha_hwr.protocol.telemetry_decoder import (
    TelemetryDecoder,
    TEST_VECTORS,
)
from alpha_hwr.protocol.frame_parser import FrameParser, ParsedFrame
from alpha_hwr.protocol.codec import encode_float_be, encode_uint16_be


class TestMotorStateDecoding:
    """Test motor state telemetry decoding (Obj 87, Sub 69)."""

    def test_decode_all_fields(self):
        """Test decoding all motor state fields."""
        # Construct payload with known values
        payload = bytearray(28)
        payload[0:4] = encode_float_be(240.0)  # Grid voltage
        payload[8:12] = encode_float_be(2.5)  # Current
        payload[16:20] = encode_float_be(150.0)  # Power
        payload[20:24] = encode_float_be(3000.0)  # Speed
        payload[24:28] = encode_float_be(45.0)  # Converter temp

        result = TelemetryDecoder.decode_motor_state(bytes(payload))

        assert "voltage_ac_v" in result
        assert abs(result["voltage_ac_v"] - 240.0) < 0.1
        assert "current_a" in result
        assert abs(result["current_a"] - 2.5) < 0.1
        assert "power_w" in result
        assert abs(result["power_w"] - 150.0) < 0.1
        assert "speed_rpm" in result
        assert abs(result["speed_rpm"] - 3000.0) < 0.1
        assert "converter_temperature_c" in result
        assert abs(result["converter_temperature_c"] - 45.0) < 0.1

    def test_decode_partial_payload(self):
        """Test decoding with only some fields present."""
        # Only voltage field
        payload = encode_float_be(230.0)
        result = TelemetryDecoder.decode_motor_state(payload)

        assert "voltage_ac_v" in result
        assert "current_a" not in result  # Not enough data

    def test_decode_empty_payload(self):
        """Test decoding empty payload."""
        result = TelemetryDecoder.decode_motor_state(b"")
        assert result == {}

    def test_voltage_range_validation(self):
        """Test voltage is rejected if out of range."""
        # Too high voltage (over 300V)
        payload = encode_float_be(500.0)
        result = TelemetryDecoder.decode_motor_state(payload)
        assert "voltage_ac_v" not in result

        # Negative voltage
        payload = encode_float_be(-10.0)
        result = TelemetryDecoder.decode_motor_state(payload)
        assert "voltage_ac_v" not in result

    def test_current_range_validation(self):
        """Test current is rejected if out of range."""
        # Construct payload with valid voltage but invalid current
        payload = bytearray(12)
        payload[0:4] = encode_float_be(240.0)  # Valid voltage
        payload[8:12] = encode_float_be(50.0)  # Invalid current (over 10A)

        result = TelemetryDecoder.decode_motor_state(bytes(payload))
        assert "voltage_ac_v" in result  # Voltage should be present
        assert "current_a" not in result  # Current should be rejected

    def test_speed_range_validation(self):
        """Test speed is rejected if out of range."""
        payload = bytearray(24)
        payload[20:24] = encode_float_be(10000.0)  # Too high (over 6000 RPM)

        result = TelemetryDecoder.decode_motor_state(bytes(payload))
        assert "speed_rpm" not in result

    def test_temperature_range_validation(self):
        """Test temperature is rejected if out of range."""
        payload = bytearray(28)
        payload[24:28] = encode_float_be(200.0)  # Too high (over 120°C)

        result = TelemetryDecoder.decode_motor_state(bytes(payload))
        assert "converter_temperature_c" not in result


class TestFlowPressureDecoding:
    """Test flow/pressure telemetry decoding (Obj 93, Sub 290)."""

    def test_decode_all_fields(self):
        """Test decoding all flow/pressure fields."""
        payload = bytearray(16)
        payload[0:4] = encode_float_be(2.5)  # Flow
        payload[4:8] = encode_float_be(5.0)  # Head
        payload[8:12] = encode_float_be(2.0)  # Inlet pressure
        payload[12:16] = encode_float_be(4.0)  # Outlet pressure

        result = TelemetryDecoder.decode_flow_pressure(bytes(payload))

        assert "flow_m3h" in result
        assert abs(result["flow_m3h"] - 2.5) < 0.1
        assert "head_m" in result
        assert abs(result["head_m"] - 5.0) < 0.1
        assert "inlet_pressure_bar" in result
        assert abs(result["inlet_pressure_bar"] - 2.0) < 0.1
        assert "outlet_pressure_bar" in result
        assert abs(result["outlet_pressure_bar"] - 4.0) < 0.1

    def test_decode_partial_payload(self):
        """Test decoding with only some fields present."""
        # Only flow and head
        payload = bytearray(8)
        payload[0:4] = encode_float_be(1.5)
        payload[4:8] = encode_float_be(3.0)

        result = TelemetryDecoder.decode_flow_pressure(bytes(payload))
        assert "flow_m3h" in result
        assert "head_m" in result
        assert "inlet_pressure_bar" not in result

    def test_flow_range_validation(self):
        """Test flow is rejected if out of range."""
        payload = encode_float_be(50.0)  # Over 10 m³/h
        result = TelemetryDecoder.decode_flow_pressure(payload)
        assert "flow_m3h" not in result

    def test_pressure_range_validation(self):
        """Test pressure is rejected if out of range."""
        payload = bytearray(12)
        payload[8:12] = encode_float_be(25.0)  # Over 20 bar

        result = TelemetryDecoder.decode_flow_pressure(bytes(payload))
        assert "inlet_pressure_bar" not in result


class TestTemperatureDecoding:
    """Test temperature telemetry decoding (Obj 93, Sub 300)."""

    def test_decode_all_fields(self):
        """Test decoding all temperature fields."""
        payload = bytearray(12)
        payload[0:4] = encode_float_be(55.0)  # Media temp
        payload[4:8] = encode_float_be(65.0)  # PCB temp
        payload[8:12] = encode_float_be(70.0)  # Control box temp

        result = TelemetryDecoder.decode_temperature(bytes(payload))

        assert "media_temperature_c" in result
        assert abs(result["media_temperature_c"] - 55.0) < 0.1
        assert "pcb_temperature_c" in result
        assert abs(result["pcb_temperature_c"] - 65.0) < 0.1
        assert "control_box_temperature_c" in result
        assert abs(result["control_box_temperature_c"] - 70.0) < 0.1

    def test_media_temperature_range(self):
        """Test media temperature range validation."""
        # Too cold
        payload = encode_float_be(-50.0)
        result = TelemetryDecoder.decode_temperature(payload)
        assert "media_temperature_c" not in result

        # Too hot
        payload = encode_float_be(150.0)
        result = TelemetryDecoder.decode_temperature(payload)
        assert "media_temperature_c" not in result

    def test_pcb_temperature_range(self):
        """Test PCB temperature range validation."""
        payload = bytearray(8)
        payload[4:8] = encode_float_be(200.0)  # Over 150°C

        result = TelemetryDecoder.decode_temperature(bytes(payload))
        assert "pcb_temperature_c" not in result


class TestAlarmsWarningsDecoding:
    """Test alarm/warning code decoding (Obj 88, Sub 0/11)."""

    def test_decode_alarms(self):
        """Test decoding alarm codes."""
        # Two alarm codes: 1 and 5
        payload = encode_uint16_be(1) + encode_uint16_be(5)
        result = TelemetryDecoder.decode_alarms_warnings(
            payload, is_alarms=True
        )

        assert result == [1, 5]

    def test_decode_warnings(self):
        """Test decoding warning codes."""
        # Three warning codes: 10, 20, 30
        payload = (
            encode_uint16_be(10) + encode_uint16_be(20) + encode_uint16_be(30)
        )
        result = TelemetryDecoder.decode_alarms_warnings(
            payload, is_alarms=False
        )

        assert result == [10, 20, 30]

    def test_filter_zero_codes(self):
        """Test that zero codes are filtered out."""
        # Mix of zero and non-zero codes
        payload = (
            encode_uint16_be(1) + encode_uint16_be(0) + encode_uint16_be(2)
        )
        result = TelemetryDecoder.decode_alarms_warnings(payload)

        assert 0 not in result
        assert result == [1, 2]

    def test_empty_alarm_list(self):
        """Test decoding empty alarm list."""
        result = TelemetryDecoder.decode_alarms_warnings(b"")
        assert result == []

    def test_all_zero_codes(self):
        """Test payload with all zero codes."""
        payload = encode_uint16_be(0) * 5
        result = TelemetryDecoder.decode_alarms_warnings(payload)
        assert result == []

    def test_partial_uint16(self):
        """Test handling of incomplete uint16 at end."""
        # Valid uint16 + 1 extra byte
        payload = encode_uint16_be(1) + bytes([0xFF])
        result = TelemetryDecoder.decode_alarms_warnings(payload)

        # Should only decode complete uint16
        assert result == [1]


class TestAutoDecoding:
    """Test automatic decoding based on frame identifiers."""

    def test_decode_motor_state_frame(self):
        """Test auto-decoding motor state frame."""
        # Create a mock frame
        payload = bytearray(28)
        payload[0:4] = encode_float_be(240.0)

        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            sub_id=69,
            obj_id=87,
            payload=bytes(payload),
            crc_valid=True,
            raw_data=b"",
        )

        result = TelemetryDecoder.decode(frame)
        assert "voltage_ac_v" in result

    def test_decode_flow_pressure_frame(self):
        """Test auto-decoding flow/pressure frame."""
        payload = bytearray(16)
        payload[0:4] = encode_float_be(2.5)

        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            sub_id=290,
            obj_id=93,
            payload=bytes(payload),
            crc_valid=True,
            raw_data=b"",
        )

        result = TelemetryDecoder.decode(frame)
        assert "flow_m3h" in result

    def test_decode_temperature_frame(self):
        """Test auto-decoding temperature frame."""
        payload = bytearray(12)
        payload[0:4] = encode_float_be(55.0)

        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            sub_id=300,
            obj_id=93,
            payload=bytes(payload),
            crc_valid=True,
            raw_data=b"",
        )

        result = TelemetryDecoder.decode(frame)
        assert "media_temperature_c" in result

    def test_decode_alarms_frame(self):
        """Test auto-decoding alarms frame."""
        payload = encode_uint16_be(1) + encode_uint16_be(2)

        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            sub_id=0,
            obj_id=88,
            payload=payload,
            crc_valid=True,
            raw_data=b"",
        )

        result = TelemetryDecoder.decode(frame)
        assert "active_alarms" in result
        assert result["active_alarms"] == [1, 2]

    def test_decode_warnings_frame(self):
        """Test auto-decoding warnings frame."""
        payload = encode_uint16_be(10)

        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            sub_id=11,
            obj_id=88,
            payload=payload,
            crc_valid=True,
            raw_data=b"",
        )

        result = TelemetryDecoder.decode(frame)
        assert "active_warnings" in result
        assert result["active_warnings"] == [10]

    def test_decode_unknown_frame(self):
        """Test auto-decoding unknown telemetry type."""
        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            sub_id=9999,
            obj_id=9999,
            payload=b"",
            crc_valid=True,
            raw_data=b"",
        )

        result = TelemetryDecoder.decode(frame)
        assert result == {}

    def test_decode_non_class10_frame(self):
        """Test auto-decoding rejects non-Class 10 frames."""
        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x02,  # Class 2
            sub_id=None,
            obj_id=None,
            payload=b"",
            crc_valid=True,
            raw_data=b"",
        )

        with pytest.raises(ValueError, match="Expected Class 10"):
            TelemetryDecoder.decode(frame)

    def test_decode_missing_identifiers(self):
        """Test auto-decoding rejects frames with missing IDs."""
        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            sub_id=None,
            obj_id=None,
            payload=b"",
            crc_valid=True,
            raw_data=b"",
        )

        with pytest.raises(ValueError, match="missing Sub-ID"):
            TelemetryDecoder.decode(frame)


class TestReferenceVectors:
    """Test with reference test vectors for other language implementations."""

    def test_motor_state_vector(self):
        """Test motor state reference vector."""
        vector = TEST_VECTORS["motor_state_normal"]
        payload = bytes.fromhex(vector["payload_hex"])

        result = TelemetryDecoder.decode_motor_state(payload)
        expected = vector["expected"]

        for key, expected_value in expected.items():
            assert key in result, f"Missing field: {key}"
            assert abs(result[key] - expected_value) < 0.1, (
                f"{key}: expected {expected_value}, got {result[key]}"
            )

    def test_flow_pressure_vector(self):
        """Test flow/pressure reference vector."""
        vector = TEST_VECTORS["flow_pressure_normal"]
        payload = bytes.fromhex(vector["payload_hex"])

        result = TelemetryDecoder.decode_flow_pressure(payload)
        expected = vector["expected"]

        for key, expected_value in expected.items():
            assert key in result
            assert abs(result[key] - expected_value) < 0.1

    def test_temperature_vector(self):
        """Test temperature reference vector."""
        vector = TEST_VECTORS["temperature_normal"]
        payload = bytes.fromhex(vector["payload_hex"])

        result = TelemetryDecoder.decode_temperature(payload)
        expected = vector["expected"]

        for key, expected_value in expected.items():
            assert key in result
            assert abs(result[key] - expected_value) < 0.1

    def test_alarms_vector(self):
        """Test alarms reference vector."""
        vector = TEST_VECTORS["alarms_active"]
        payload = bytes.fromhex(vector["payload_hex"])

        result = TelemetryDecoder.decode_alarms_warnings(
            payload, is_alarms=True
        )
        expected = vector["expected"]["active_alarms"]

        assert result == expected


class TestEndToEnd:
    """Test complete parsing and decoding workflow."""

    def test_parse_and_decode_motor_state(self):
        """Test complete workflow: parse frame -> decode telemetry."""
        # Construct complete frame with motor state telemetry
        payload = bytearray(28)
        payload[0:4] = encode_float_be(230.0)  # Voltage
        payload[8:12] = encode_float_be(1.5)  # Current

        # Build minimal frame (without proper CRC for simplicity)
        frame_data = bytes(
            [0x24, 0x1C, 0xE7, 0xF8, 0x0A, 0x00, 0x00, 0x45, 0x00, 0x57]
        )
        frame_data += bytes(payload) + bytes([0x00, 0x00])

        # Parse frame
        frame = FrameParser.parse_frame(frame_data)

        # Should parse successfully (even if CRC is wrong)
        assert frame.valid is True
        assert frame.class_byte == 0x0A

        # Decode telemetry
        if frame.obj_id == 87 and frame.sub_id == 69:
            telemetry = TelemetryDecoder.decode_motor_state(frame.payload)
            assert "voltage_ac_v" in telemetry
            assert "current_a" in telemetry


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_decode_nan_float(self):
        """Test handling of NaN float values."""
        payload = struct.pack(">f", float("nan"))
        result = TelemetryDecoder.decode_motor_state(payload)
        # NaN should fail range validation
        assert "voltage_ac_v" not in result

    def test_decode_inf_float(self):
        """Test handling of infinity float values."""
        payload = struct.pack(">f", float("inf"))
        result = TelemetryDecoder.decode_motor_state(payload)
        # Infinity should fail range validation
        assert "voltage_ac_v" not in result

    def test_decode_boundary_values(self):
        """Test decoding values at boundary limits."""
        # Test voltage at exact upper limit
        payload = encode_float_be(300.0)
        result = TelemetryDecoder.decode_motor_state(payload)
        assert "voltage_ac_v" in result
        assert result["voltage_ac_v"] == 300.0

        # Test voltage just over limit
        payload = encode_float_be(300.1)
        result = TelemetryDecoder.decode_motor_state(payload)
        assert "voltage_ac_v" not in result

    def test_decode_zero_values(self):
        """Test decoding zero values (should be valid)."""
        payload = bytearray(28)
        payload[0:4] = encode_float_be(0.0)  # Zero voltage
        payload[8:12] = encode_float_be(0.0)  # Zero current

        result = TelemetryDecoder.decode_motor_state(bytes(payload))
        assert "voltage_ac_v" in result
        assert result["voltage_ac_v"] == 0.0
        assert "current_a" in result
        assert result["current_a"] == 0.0
