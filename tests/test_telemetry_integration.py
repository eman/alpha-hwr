"""
Tests for TelemetryDecoder functionality.

This module tests the telemetry decoder's ability to decode Class 10 DataObject
telemetry notifications including motor state, flow/pressure, temperature, and
alarms/warnings using the new protocol architecture.
"""

import struct

from wire import class10_reply

from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.protocol.telemetry_decoder import TelemetryDecoder


class TestTelemetryDecoder:
    """Tests for TelemetryDecoder methods."""

    def test_decode_motor_state_complete(self):
        """Test decoding complete motor state telemetry (Obj 87, Sub 69).

        Payload structure:
        - 0-3: Grid voltage (float)
        - 4-7: Reserved
        - 8-11: Current (float)
        - 12-15: Reserved
        - 16-19: DC power (float)
        - 20-23: Speed (float)
        - 24-27: Converter temp (float)
        """
        voltage = 230.0
        current = 1.5
        power = 45.0
        speed = 1500.0
        temp = 35.0

        # Build payload with padding
        payload = bytearray()
        payload.extend(struct.pack(">f", voltage))  # 0-3
        payload.extend(bytes(4))  # 4-7 (padding)
        payload.extend(struct.pack(">f", current))  # 8-11
        payload.extend(bytes(4))  # 12-15 (padding)
        payload.extend(struct.pack(">f", power))  # 16-19
        payload.extend(struct.pack(">f", speed))  # 20-23
        payload.extend(struct.pack(">f", temp))  # 24-27

        data = TelemetryDecoder.decode_motor_state(bytes(payload))

        assert "voltage_ac_v" in data
        assert abs(data["voltage_ac_v"] - voltage) < 0.1
        assert "current_a" in data
        assert abs(data["current_a"] - current) < 0.1
        assert "power_w" in data
        assert abs(data["power_w"] - power) < 0.1
        assert "speed_rpm" in data
        assert abs(data["speed_rpm"] - speed) < 0.1
        assert "converter_temperature_c" in data
        assert abs(data["converter_temperature_c"] - temp) < 0.1

    def test_decode_motor_state_partial(self):
        """Test decoding partial motor state (only voltage and current)."""
        voltage = 240.0
        current = 2.0

        # Build minimal payload (only voltage + padding + current)
        payload = bytearray()
        payload.extend(struct.pack(">f", voltage))  # 0-3
        payload.extend(bytes(4))  # 4-7 (padding)
        payload.extend(struct.pack(">f", current))  # 8-11

        data = TelemetryDecoder.decode_motor_state(bytes(payload))

        assert "voltage_ac_v" in data
        assert abs(data["voltage_ac_v"] - voltage) < 0.1
        assert "current_a" in data
        assert abs(data["current_a"] - current) < 0.1
        # Other fields should not be present
        assert "power_w" not in data
        assert "speed_rpm" not in data

    def test_decode_motor_state_invalid_ranges(self):
        """Test that values outside valid ranges are rejected."""
        # Invalid voltage (too high)
        invalid_voltage = 400.0
        payload = struct.pack(">f", invalid_voltage)

        data = TelemetryDecoder.decode_motor_state(payload)
        assert "voltage_ac_v" not in data

        # Invalid current (negative)
        payload = bytearray()
        payload.extend(struct.pack(">f", 230.0))  # Valid voltage
        payload.extend(bytes(4))  # Padding
        payload.extend(struct.pack(">f", -5.0))  # Invalid current

        data = TelemetryDecoder.decode_motor_state(bytes(payload))
        assert "voltage_ac_v" in data
        assert "current_a" not in data  # Should be rejected

    def test_decode_flow_pressure_complete(self):
        """Test decoding complete flow/pressure telemetry (Obj 93, Sub 290).

        Payload structure:
        - 0-3: Flow rate (float, m³/h)
        - 4-7: Head (float, m)
        - 8-11: Inlet pressure (float, bar)
        - 12-15: Outlet pressure (float, bar)
        """
        flow = 2.5
        head = 5.0
        p_in = 1.2
        p_out = 2.0

        payload = struct.pack(">ffff", flow, head, p_in, p_out)

        data = TelemetryDecoder.decode_flow_pressure(payload)

        assert "flow_m3h" in data
        assert abs(data["flow_m3h"] - flow) < 0.1
        assert "head_m" in data
        assert abs(data["head_m"] - head) < 0.1
        assert "inlet_pressure_bar" in data
        assert abs(data["inlet_pressure_bar"] - p_in) < 0.1
        assert "outlet_pressure_bar" in data
        assert abs(data["outlet_pressure_bar"] - p_out) < 0.1

    def test_decode_flow_pressure_partial(self):
        """Test decoding partial flow/pressure data."""
        flow = 1.8
        head = 4.2

        payload = struct.pack(">ff", flow, head)

        data = TelemetryDecoder.decode_flow_pressure(payload)

        assert "flow_m3h" in data
        assert abs(data["flow_m3h"] - flow) < 0.1
        assert "head_m" in data
        assert abs(data["head_m"] - head) < 0.1
        # Pressures not included
        assert "inlet_pressure_bar" not in data
        assert "outlet_pressure_bar" not in data

    def test_decode_temperature_complete(self):
        """Test decoding complete temperature telemetry (Obj 93, Sub 300).

        Payload structure:
        - 0-3: Media temperature (float, °C)
        - 4-7: PCB temperature (float, °C)
        - 8-11: Control box temperature (float, °C)
        """
        media_temp = 45.0
        pcb_temp = 55.0
        box_temp = 50.0

        payload = struct.pack(">fff", media_temp, pcb_temp, box_temp)

        data = TelemetryDecoder.decode_temperature(payload)

        assert "media_temperature_c" in data
        assert abs(data["media_temperature_c"] - media_temp) < 0.1
        assert "pcb_temperature_c" in data
        assert abs(data["pcb_temperature_c"] - pcb_temp) < 0.1
        assert "control_box_temperature_c" in data
        assert abs(data["control_box_temperature_c"] - box_temp) < 0.1

    def test_decode_temperature_invalid_ranges(self):
        """Test that temperatures outside valid ranges are rejected."""
        # Media temp too high (> 100°C)
        invalid_media = 150.0
        valid_pcb = 60.0
        valid_box = 55.0

        payload = struct.pack(">fff", invalid_media, valid_pcb, valid_box)

        data = TelemetryDecoder.decode_temperature(payload)

        # Invalid media temp should be rejected
        assert "media_temperature_c" not in data
        # But valid temps should be included
        assert "pcb_temperature_c" in data
        assert "control_box_temperature_c" in data

    def test_decode_alarms_warnings(self):
        """Test decoding alarm/warning codes (Obj 88, Sub 0/11).

        Payload: Array of uint16 codes (big-endian)
        Code 0 = no alarm/warning (filtered out)
        """
        # Build array: [0, 10, 0, 25, 42, 0]
        payload = bytearray()
        payload.extend(struct.pack(">H", 0))  # Filtered
        payload.extend(struct.pack(">H", 10))  # Active
        payload.extend(struct.pack(">H", 0))  # Filtered
        payload.extend(struct.pack(">H", 25))  # Active
        payload.extend(struct.pack(">H", 42))  # Active
        payload.extend(struct.pack(">H", 0))  # Filtered

        codes = TelemetryDecoder.decode_alarms_warnings(
            bytes(payload), is_alarms=True
        )

        # Should only include non-zero codes
        assert len(codes) == 3
        assert 10 in codes
        assert 25 in codes
        assert 42 in codes
        assert 0 not in codes

    def test_decode_alarms_empty(self):
        """Test decoding when no alarms are active (all zeros)."""
        # Array of all zeros
        payload = struct.pack(">HHHH", 0, 0, 0, 0)

        codes = TelemetryDecoder.decode_alarms_warnings(payload, is_alarms=True)

        assert len(codes) == 0

    def test_decode_alarms_single_code(self):
        """Test decoding single alarm code."""
        payload = struct.pack(">H", 100)

        codes = TelemetryDecoder.decode_alarms_warnings(payload, is_alarms=True)

        assert len(codes) == 1
        assert codes[0] == 100

    def test_empty_payload_handling(self):
        """Test graceful handling of empty payloads."""
        empty = b""

        motor_data = TelemetryDecoder.decode_motor_state(empty)
        assert len(motor_data) == 0

        flow_data = TelemetryDecoder.decode_flow_pressure(empty)
        assert len(flow_data) == 0

        temp_data = TelemetryDecoder.decode_temperature(empty)
        assert len(temp_data) == 0

        alarm_codes = TelemetryDecoder.decode_alarms_warnings(empty)
        assert len(alarm_codes) == 0

    def test_truncated_payload_handling(self):
        """Test handling of truncated payloads (incomplete fields)."""
        # Motor state with only 2 bytes (incomplete float)
        truncated = bytes([0x43, 0x66])

        data = TelemetryDecoder.decode_motor_state(truncated)
        # Should not crash, just return empty or partial data
        assert isinstance(data, dict)

    def test_integration_with_frame_parser(self):
        """Test integration: parse frame then decode telemetry."""
        # Build complete GENI Class 10 frame for motor state
        voltage = 230.0
        current = 1.5
        power = 45.0
        speed = 1500.0

        # Build telemetry payload
        payload = bytearray()
        payload.extend(struct.pack(">f", voltage))
        payload.extend(bytes(4))  # Padding
        payload.extend(struct.pack(">f", current))
        payload.extend(bytes(4))  # Padding
        payload.extend(struct.pack(">f", power))
        payload.extend(struct.pack(">f", speed))

        # The motor-state register answers as type 3 version 1. The frame
        # this replaced put the requested Sub-ID and Object ID in bytes
        # 6-9, declared a length eight bytes past the frame's end, and left
        # two zero bytes where the CRC goes.
        packet = class10_reply(0x0001, 0x0003, bytes(payload))

        frame = FrameParser.parse_frame(packet)

        assert frame is not None
        assert frame.valid
        assert frame.crc_valid
        assert frame.class_byte == 10
        assert frame.type_high == 0x0001
        assert frame.type_low_ver == 0x0003

        # object_body strips the object's own three-byte size header.
        motor_data = TelemetryDecoder.decode_motor_state(frame.object_body)

        assert "voltage_ac_v" in motor_data
        assert abs(motor_data["voltage_ac_v"] - voltage) < 0.1
        assert "speed_rpm" in motor_data
        assert abs(motor_data["speed_rpm"] - speed) < 0.1

    def test_zero_values_are_valid(self):
        """Test that zero values are correctly decoded (not filtered)."""
        # Zero speed is valid (pump stopped)
        voltage = 230.0
        speed = 0.0

        payload = bytearray()
        payload.extend(struct.pack(">f", voltage))
        payload.extend(bytes(16))  # Skip to speed offset
        payload.extend(struct.pack(">f", speed))

        data = TelemetryDecoder.decode_motor_state(bytes(payload))

        # Zero speed should be included
        assert "speed_rpm" in data
        assert data["speed_rpm"] == 0.0

    def test_nan_and_inf_handling(self):
        """Test handling of NaN and Infinity values."""
        import math

        # NaN voltage
        nan_payload = struct.pack(">f", math.nan)
        data = TelemetryDecoder.decode_motor_state(nan_payload)
        # NaN should either be filtered or handled gracefully
        # Implementation may vary - just ensure no crash
        assert isinstance(data, dict)

        # Infinity current
        payload = bytearray()
        payload.extend(struct.pack(">f", 230.0))  # Valid voltage
        payload.extend(bytes(4))
        payload.extend(struct.pack(">f", math.inf))  # Inf current

        data = TelemetryDecoder.decode_motor_state(bytes(payload))
        # Infinity should be outside valid range and filtered
        assert "current_a" not in data or data["current_a"] != math.inf
