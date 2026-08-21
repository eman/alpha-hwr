"""
Decoding the pump's telemetry objects.

Every frame here is either a recording from an ALPHA HWR or is built by
``tests.wire``, which computes a real length field and a real CRC. The
frames these replaced were assembled by hand with a constant APDU head, a
two-zero-byte "mock CRC", and the requested Object/Sub-ID in bytes 6-9 -
where the pump puts an object type. They agreed with the decoder because
both were built from the same wrong reading of the wire.
"""

import struct

import pytest
from wire import CAPTURED, class10_reply

from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.protocol.telemetry_decoder import TelemetryDecoder

#: Object types the three telemetry registers answer with, measured
#: 2026-08-20 by issuing each read and recording bytes 6-9.
MOTOR_STATE_TYPE = (0x0001, 0x0003)
FLOW_PRESSURE_TYPE = (0x0002, 0x3502)
TEMPERATURE_TYPE = (0x0002, 0x1602)


def test_parse_motor_state_corrected():
    """Offsets 0, 8, 16, 20 and 24 of the motor-state struct."""
    body = bytearray([0] * 28)
    struct.pack_into(">f", body, 0, 230.5)  # Grid voltage
    struct.pack_into(">f", body, 8, 1.2)  # Current
    struct.pack_into(">f", body, 16, 45.0)  # DC power
    struct.pack_into(">f", body, 20, 1800.0)  # Speed
    struct.pack_into(">f", body, 24, 35.5)  # Converter temperature

    frame = FrameParser.parse_frame(
        class10_reply(*MOTOR_STATE_TYPE, bytes(body))
    )
    assert frame.crc_valid
    updates = TelemetryDecoder.decode(frame)

    assert updates["voltage_ac_v"] == pytest.approx(230.5)
    assert updates["current_a"] == pytest.approx(1.2)
    assert updates["power_w"] == pytest.approx(45.0)
    assert updates["speed_rpm"] == pytest.approx(1800.0)
    assert updates["converter_temperature_c"] == pytest.approx(35.5)


def test_parse_pressures():
    """Offsets 0, 4, 8 and 12 of the flow/pressure struct."""
    body = bytearray([0] * 20)
    struct.pack_into(">f", body, 0, 1.5)  # Flow
    struct.pack_into(">f", body, 4, 3.2)  # Head
    struct.pack_into(">f", body, 8, 0.8)  # Inlet pressure
    struct.pack_into(">f", body, 12, 1.1)  # Outlet pressure

    frame = FrameParser.parse_frame(
        class10_reply(*FLOW_PRESSURE_TYPE, bytes(body))
    )
    assert frame.crc_valid
    updates = TelemetryDecoder.decode(frame)

    assert updates["flow_m3h"] == pytest.approx(1.5)
    assert updates["head_m"] == pytest.approx(3.2)
    assert updates["inlet_pressure_bar"] == pytest.approx(0.8)
    assert updates["outlet_pressure_bar"] == pytest.approx(1.1)


def test_parse_detailed_temperatures():
    """Offsets 0, 4 and 8 of the temperature struct."""
    body = bytearray([0] * 12)
    struct.pack_into(">f", body, 0, 65.2)  # Media
    struct.pack_into(">f", body, 4, 42.1)  # PCB
    struct.pack_into(">f", body, 8, 38.5)  # Control box

    frame = FrameParser.parse_frame(
        class10_reply(*TEMPERATURE_TYPE, bytes(body))
    )
    assert frame.crc_valid
    updates = TelemetryDecoder.decode(frame)

    assert updates["media_temperature_c"] == pytest.approx(65.2)
    assert updates["pcb_temperature_c"] == pytest.approx(42.1)
    assert updates["control_box_temperature_c"] == pytest.approx(38.5)


def test_captured_temperature_frame_decodes():
    """The recorded temperature reply, decoded end to end."""
    frame = FrameParser.parse_frame(CAPTURED["temperature"])
    updates = TelemetryDecoder.decode(frame)

    assert updates["media_temperature_c"] == pytest.approx(28.118, abs=1e-3)
    assert updates["pcb_temperature_c"] == pytest.approx(29.174, abs=1e-3)
    assert updates["control_box_temperature_c"] == pytest.approx(
        26.756, abs=1e-3
    )


def test_alarms_and_warnings_share_one_type():
    """
    A reply cannot say whether it holds alarms or warnings.

    Reading Object 88 Sub 0 and Object 88 Sub 11 on 2026-08-20 returned
    byte-identical frames, both typed 0x3A01 version 2. So the automatic
    router deliberately does not handle them - only the caller that issued
    the read knows which list came back, which is why
    DeviceInfoService.read_alarms() decodes them itself.
    """
    captured = bytes.fromhex("240df8e70a0900023a010000020000dc50")
    frame = FrameParser.parse_frame(captured)

    assert frame.crc_valid
    assert (frame.type_high, frame.type_low_ver) == (0x0002, 0x3A01)
    assert TelemetryDecoder.decode(frame) == {}
    # An empty list: this pump had nothing active when the frame was taken.
    assert TelemetryDecoder.decode_alarms_warnings(frame.object_body) == []


def test_alarm_codes_decode_and_drop_padding():
    """Zero is padding, not alarm code zero."""
    body = struct.pack(">HHH", 42, 7, 0)

    frame = FrameParser.parse_frame(class10_reply(0x0002, 0x3A01, body))
    assert frame.crc_valid
    assert TelemetryDecoder.decode_alarms_warnings(frame.object_body) == [42, 7]
