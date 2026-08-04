import struct

import pytest

from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.protocol.telemetry_decoder import TelemetryDecoder


def test_parse_motor_state_corrected():
    # Obj 87, Sub 69 (Motor State), Type 256
    # Correct Offsets:
    # 0: Grid V (230.5)
    # 8: Current (1.2)
    # 16: DC Power (45.0)
    # 20: Speed (1800.0)
    # 24: Converter Temp (35.5)

    payload = bytearray([0] * 30)
    struct.pack_into(">f", payload, 0, 230.5)  # Grid V
    struct.pack_into(">f", payload, 8, 1.2)  # Current
    struct.pack_into(">f", payload, 16, 45.0)  # Power
    struct.pack_into(">f", payload, 20, 1800.0)  # Speed
    struct.pack_into(">f", payload, 24, 35.5)  # Converter Temp

    # GENI Packet: [STX][LEN][DST][SRC][Class=10][OpSpec=INFO][Sub_H][Sub_L][Obj_H][Obj_L][Payload...][CRC]
    # Sub=69 (0x0045), Obj=87 (0x0057)
    packet = bytearray(
        [0x24, len(payload) + 8, 0xF8, 0xE7, 0x0A, 0x13, 0x00, 69, 0x00, 87]
    )
    packet.extend(payload)
    packet.extend([0, 0])  # Mock CRC

    frame = FrameParser.parse_frame(bytes(packet))
    updates = TelemetryDecoder.decode(frame)

    assert updates["voltage_ac_v"] == pytest.approx(230.5)
    assert updates["current_a"] == pytest.approx(1.2)
    assert updates["power_w"] == pytest.approx(45.0)
    assert updates["speed_rpm"] == pytest.approx(1800.0)
    assert updates["converter_temperature_c"] == pytest.approx(35.5)


def test_parse_pressures():
    # Obj 93, Sub 290 (Flow/Pressure), Type 565
    # Offsets: 0:Flow, 4:Head, 8:InletP, 12:OutletP
    payload = bytearray([0] * 20)
    struct.pack_into(">f", payload, 0, 1.5)  # Flow
    struct.pack_into(">f", payload, 4, 3.2)  # Head
    struct.pack_into(">f", payload, 8, 0.8)  # Inlet P
    struct.pack_into(">f", payload, 12, 1.1)  # Outlet P

    # Sub 290=0x0122, Obj 93=0x005D
    packet = bytearray(
        [0x24, len(payload) + 8, 0xF8, 0xE7, 0x0A, 0x13, 0x01, 0x22, 0x00, 0x5D]
    )
    packet.extend(payload)
    packet.extend([0, 0])

    frame = FrameParser.parse_frame(bytes(packet))
    updates = TelemetryDecoder.decode(frame)

    assert updates["flow_m3h"] == pytest.approx(1.5)
    assert updates["head_m"] == pytest.approx(3.2)
    assert updates["inlet_pressure_bar"] == pytest.approx(0.8)
    assert updates["outlet_pressure_bar"] == pytest.approx(1.1)


def test_parse_detailed_temperatures():
    # Obj 93, Sub 300 (Temps), Type 534
    # Offsets: 0:Media, 4:PCB, 8:Controlbox
    payload = bytearray([0] * 12)
    struct.pack_into(">f", payload, 0, 65.2)  # Media
    struct.pack_into(">f", payload, 4, 42.1)  # PCB
    struct.pack_into(">f", payload, 8, 38.5)  # Ctrl

    # Sub 300=0x012C, Obj 93=0x005D
    packet = bytearray(
        [0x24, len(payload) + 8, 0xF8, 0xE7, 0x0A, 0x13, 0x01, 0x2C, 0x00, 0x5D]
    )
    packet.extend(payload)
    packet.extend([0, 0])

    frame = FrameParser.parse_frame(bytes(packet))
    updates = TelemetryDecoder.decode(frame)

    assert updates["media_temperature_c"] == pytest.approx(65.2)
    assert updates["pcb_temperature_c"] == pytest.approx(42.1)
    assert updates["control_box_temperature_c"] == pytest.approx(38.5)


def test_parse_alarms_warnings():
    # Obj 88, Sub 0 (Alarms)
    # Active Query Response Format: [Class][OpSpec][Seq(2)][ID(2)][Res(2)][DataLen][Data...]
    # OpSpec 0x09 (validated on real hardware - ESPHome implementation)
    alarm_data = struct.pack(
        ">HHH", 42, 7, 0
    )  # 2 alarms (42, 7), zero filtered

    # Build response: [STX][Len][Dst][Src][Class=10][OpSpec=0x09][Seq(2)][ID(2)][Res(2)][DataLen][Data...][CRC(2)]
    packet = bytearray(
        [
            0x24,  # STX
            13
            + len(
                alarm_data
            ),  # Length (total from STX through DataLen + Data, excluding CRC)
            0xF8,
            0xE7,  # Dst, Src
            0x0A,  # Class 10
            0x09,  # OpSpec (Active Query Response for alarms/warnings)
            0x00,
            0x01,  # Sequence number
            0x58,
            0x00,  # ID (Register 0x5800 = Obj 88, Sub 0)
            0x00,
            0x00,  # Reserved
            len(alarm_data),  # DataLen
        ]
    )
    packet.extend(alarm_data)
    packet.extend([0, 0])  # Mock CRC

    frame = FrameParser.parse_frame(bytes(packet))
    updates = TelemetryDecoder.decode(frame)
    assert updates["active_alarms"] == [42, 7]

    # Obj 88, Sub 11 (Warnings)
    # Same Active Query Response format
    warning_data = struct.pack(">HH", 5, 0)  # 1 warning (5)

    packet = bytearray(
        [
            0x24,  # STX
            13
            + len(
                warning_data
            ),  # Length (total from STX through DataLen + Data, excluding CRC)
            0xF8,
            0xE7,  # Dst, Src
            0x0A,  # Class 10
            0x09,  # OpSpec
            0x00,
            0x02,  # Sequence number
            0x58,
            0x0B,  # ID (Register 0x580B = Obj 88, Sub 11)
            0x00,
            0x00,  # Reserved
            len(warning_data),  # DataLen
        ]
    )
    packet.extend(warning_data)
    packet.extend([0, 0])  # Mock CRC

    frame = FrameParser.parse_frame(bytes(packet))
    updates = TelemetryDecoder.decode(frame)
    assert updates["active_warnings"] == [5]
