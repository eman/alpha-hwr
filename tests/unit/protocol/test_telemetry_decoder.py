"""
Unit tests for telemetry_decoder.py

Tests the telemetry decoder with various payload types and edge cases.
"""

import struct

from alpha_hwr.protocol.codec import encode_float_be, encode_uint16_be
from alpha_hwr.protocol.frame_parser import FrameParser, ParsedFrame
from alpha_hwr.protocol.telemetry_decoder import (
    TEST_VECTORS,
    TelemetryDecoder,
)


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
    """
    Routing a real reply to the right decoder.

    These drive frames captured from an ALPHA HWR (family 52, type 7,
    version 2) on 2026-08-20 through the production parser, rather than
    hand-building a ParsedFrame. That matters here specifically: the router
    used to match on the Object and Sub-ID pairs that were *requested*
    ((87, 69), (93, 290), (93, 300)), and a reply carries neither - so every
    case fell through to a fallback and the routing table was never
    exercised by a frame the pump could send. Synthetic frames agreed with
    it, because they were built from the same wrong assumption.
    """

    #: Reply to the motor-state register read, 56 bytes on the wire.
    MOTOR_FRAME = bytes.fromhex(
        "2434f8e70a300001000300002942e730d643237a000000000000000000"
        "00000000000000007fffffff7fffffff0000000000000000002385"
    )

    #: Reply to the flow/pressure register read, 51 bytes.
    FLOW_FRAME = bytes.fromhex(
        "242ff8e70a2b0002350200002400000000000000007fffffff7fffffff"
        "7fffffff7fffffff000000000000000000000000edbe"
    )

    #: Reply to the temperature register read, 28 bytes.
    TEMP_FRAME = bytes.fromhex(
        "2418f8e70a140002160200000d41e0f24d41e9654e41d60bac001c01"
    )

    def test_decode_motor_state_frame(self):
        frame = FrameParser.parse_frame(self.MOTOR_FRAME)
        assert frame.crc_valid
        result = TelemetryDecoder.decode(frame)
        assert "voltage_ac_v" in result
        # 0x42E730D6 - the pump was on mains at the time of capture.
        assert 100.0 < result["voltage_ac_v"] < 130.0

    def test_decode_flow_pressure_frame(self):
        frame = FrameParser.parse_frame(self.FLOW_FRAME)
        assert frame.crc_valid
        result = TelemetryDecoder.decode(frame)
        assert "flow_m3h" in result
        assert "head_m" in result

    def test_decode_temperature_frame(self):
        frame = FrameParser.parse_frame(self.TEMP_FRAME)
        assert frame.crc_valid
        result = TelemetryDecoder.decode(frame)
        assert "media_temperature_c" in result
        assert 20.0 < result["media_temperature_c"] < 40.0

    def test_each_register_answers_with_its_own_type(self):
        """
        The three telemetry replies are told apart by type, not by length.

        A previous filter keyed on the declared payload length - 48, 43 and
        20 for these three - which is why it appeared to work while
        discarding any other reply that happened to be one of those sizes.
        """
        types = {
            FrameParser.parse_frame(f).type_low_ver
            for f in (self.MOTOR_FRAME, self.FLOW_FRAME, self.TEMP_FRAME)
        }
        assert types == {0x0003, 0x3502, 0x1602}

    def test_alarms_and_warnings_are_not_routed(self):
        """
        The router cannot label an alarm list, and does not pretend to.

        Reading Object 88 Sub 0 and Object 88 Sub 11 on 2026-08-20 returned
        byte-identical frames, both typed 0x3A01 version 2. Whichever list
        came back, the reply says the same thing - so only the caller that
        issued the read knows, and DeviceInfoService.read_alarms() decodes
        them itself rather than coming through here.
        """
        captured = bytes.fromhex("240df8e70a0900023a010000020000dc50")
        frame = FrameParser.parse_frame(captured)

        assert frame.crc_valid
        assert (frame.type_high, frame.type_low_ver) == (0x0002, 0x3A01)
        assert TelemetryDecoder.decode(frame) == {}

    def test_alarm_codes_still_decode_when_the_caller_knows(self):
        frame = ParsedFrame(
            valid=True,
            frame_type="response",
            class_byte=0x0A,
            type_high=0x0002,
            type_low_ver=0x3A01,
            payload=encode_uint16_be(42) + encode_uint16_be(7),
            multi_apdu=False,
            crc_valid=True,
            raw_data=b"",
        )
        assert TelemetryDecoder.decode_alarms_warnings(frame.payload) == [42, 7]

    def test_decode_non_class10_frame(self):
        """A Class 7 string reply carries no telemetry."""
        frame = FrameParser.parse_frame(
            bytes.fromhex("240ef8e7070a414c5048412048575200838d")
        )
        assert frame.class_byte == 7
        assert TelemetryDecoder.decode(frame) == {}

    def test_decode_refusal_frame(self):
        """
        A refusal is not telemetry, and must not decode as any.

        ``0x81`` is Unknown Data Item with one payload byte naming the item
        the pump did not recognise - here item 0. Read as an acknowledgement
        carrying an error code, this frame said "success, code 0".
        """
        frame = FrameParser.parse_frame(bytes.fromhex("2407f8e70a810040405ebf"))
        assert frame.class_byte == 0x0A
        assert TelemetryDecoder.decode(frame) == {}


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
    """Parse a frame off the wire and decode it, with nothing in between."""

    def test_parse_and_decode_motor_state(self):
        """
        The captured motor reply survives the whole path.

        The frame this replaced was hand-built with the destination and
        source addresses swapped and a deliberately wrong CRC, and it
        declared a zero-byte payload while carrying 28 - so it exercised
        neither the length field nor the checksum, which are the two things
        parsing a real frame depends on.
        """
        raw = bytes.fromhex(
            "2434f8e70a300001000300002942e730d643237a000000000000000000"
            "00000000000000007fffffff7fffffff0000000000000000002385"
        )

        frame = FrameParser.parse_frame(raw)

        assert frame.valid is True
        assert frame.crc_valid is True
        assert frame.frame_type == "response"
        assert frame.class_byte == 0x0A
        # Declared payload length and frame length agree, as they do for
        # every CRC-valid reply this pump sends.
        assert raw[5] == len(raw) - 8
        assert frame.multi_apdu is False

        telemetry = TelemetryDecoder.decode(frame)
        assert "voltage_ac_v" in telemetry
        assert "current_a" in telemetry
        assert "power_w" in telemetry
        assert "speed_rpm" in telemetry


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
