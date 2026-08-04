import struct
from alpha_hwr.protocol.frame_builder import FrameBuilder
from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.protocol.telemetry_decoder import TelemetryDecoder
from alpha_hwr.constants import (
    AUTH_LEGACY_MAGIC,
    AUTH_CLASS10_MAGIC,
    AUTH_EXTEND_1,
    AUTH_EXTEND_2,
    CommandOpcode,
    FRAME_START,
    RESPONSE_START,
    SERVICE_ID_HIGH,
    RESERVED_BYTE,
    CLASS_10,
)
from alpha_hwr.utils import calc_crc16_read


class TestPacketCreation:
    """
    Unit tests for GENI Packet Creation.
    Ensures that refactoring does not break exact byte sequences required by the hardware.
    """

    def test_auth_magic_packets(self):
        """Verify Authentication Magic Packets match known good sequences."""
        # Derived from constants.py
        # Legacy magic addresses the broadcast unit 0xFF (not 0xE7), matching
        # the payload captured from the Grundfos GO app - see issue #65.
        assert AUTH_LEGACY_MAGIC == bytes.fromhex("2707fff802039495964f91")
        assert AUTH_CLASS10_MAGIC == bytes.fromhex("2707e7f80a03560006c55a")
        assert AUTH_EXTEND_1 == bytes.fromhex("2705e7f805c14bc382")
        assert AUTH_EXTEND_2 == bytes.fromhex("2705e7f80bc10fd0c3")

    def test_build_read_request_electrical(self):
        """Verify construction of 3-byte Register Read Request."""
        # Expected: [27][06][E7][F8][0A][03][00][45][CRC_H][CRC_L]??
        # Using Register 0x570045 as an example
        # FrameBuilder.build_read_request logic:
        # If > 0xFFFF: Reg Bytes = [57, 00, 45]
        # Header: [27, 4+3, E7, F8, 0A, 03] -> [27, 07, E7, F8, 0A, 03]
        # Payload: [57, 00, 45]
        # Total: 27 07 E7 F8 0A 03 57 00 45 [CRC]

        reg = 0x570045  # 3-byte register address
        cmd = FrameBuilder.build_read_request(reg)

        assert cmd[0] == FRAME_START
        assert cmd[1] == 0x07  # Length
        assert cmd[2] == SERVICE_ID_HIGH  # 0xE7
        assert cmd[3] == 0xF8  # Source
        assert cmd[4] == RESERVED_BYTE  # 0x0A
        assert cmd[5] == CommandOpcode.READ  # 0x03

        # Register address
        assert cmd[6] == 0x57
        assert cmd[7] == 0x00
        assert cmd[8] == 0x45

        # CRC Check (Last 2 bytes)
        payload_for_crc = cmd[1:-2]
        expected_crc = calc_crc16_read(payload_for_crc)
        assert (cmd[-2] << 8 | cmd[-1]) == expected_crc

    def test_build_start_pump_packet(self):
        """
        Verify START Pump Packet (Class 10 DataObject SET).
        Based on captured frame: 27 14 E7 F8 0A 90 56 00 06 01 2F 01 00 00 07 00 00 02 45 65 [CRC]
        (First 20 bytes usually)
        """
        # Construction logic in client.py:
        # payload = 2F 01 00 00 07 00 00 [MODE] 45 65 70 00
        # build_data_object_set(0x5600, 0x0601, payload, source=0xF8, override_len=20, override_op=0x90)

        mode = 0x02  # Auto
        payload = bytearray.fromhex("2F010000070000")
        payload.append(mode)
        payload.extend(bytes.fromhex("45657000"))

        cmd = FrameBuilder.build_data_object_set(
            sub_id=0x5600,
            obj_id=0x0601,
            data=bytes(payload),
            source=0xF8,
            override_len=20,
            override_op=0x90,
        )

        # Verification
        assert cmd[0] == 0x27
        assert cmd[1] == 0x14  # 20 decimal
        assert cmd[2] == 0xE7
        assert cmd[3] == 0xF8
        assert cmd[4] == 0x0A  # Class 10
        assert cmd[5] == 0x90  # OpSpec (Overridden)

        # SubID
        assert cmd[6] == 0x56
        assert cmd[7] == 0x00

        # ObjID
        assert cmd[8] == 0x06
        assert cmd[9] == 0x01

        # Payload Start (2F 01 ...)
        assert cmd[10] == 0x2F
        assert cmd[11] == 0x01

        # Mode at offset 10+7 = 17?
        # 2F 01 00 00 07 00 00 [02]
        # 0  1  2  3  4  5  6   7
        assert cmd[10 + 7] == 0x02

        # CRC
        payload_for_crc = cmd[1:-2]
        expected_crc = calc_crc16_read(payload_for_crc)
        assert (cmd[-2] << 8 | cmd[-1]) == expected_crc

    def test_build_stop_pump_packet(self):
        """
        Verify STOP Pump Packet.
        Based on logic: same as start but payload index 6 is 0x01 (Stop) instead of 0x00?
        Client.py: payload = '2F010000070001'
        """
        # payload = 2F 01 00 00 07 00 01 [MODE] 45 65 70 00
        mode = 0x02
        payload = bytearray.fromhex("2F010000070001")
        payload.append(mode)
        payload.extend(bytes.fromhex("45657000"))

        cmd = FrameBuilder.build_data_object_set(
            sub_id=0x5600,
            obj_id=0x0601,
            data=bytes(payload),
            source=0xF8,
            override_len=20,
            override_op=0x90,
        )

        # Verify Stop Byte
        # 2F 01 00 00 07 00 [01]
        # Offset 6 in payload -> Offset 16 in packet
        assert cmd[16] == 0x01

        # CRC Check
        payload_for_crc = cmd[1:-2]
        expected_crc = calc_crc16_read(payload_for_crc)
        assert (cmd[-2] << 8 | cmd[-1]) == expected_crc

    def test_telemetry_decoder_class10(self):
        """
        Test FrameBuilder.parse_class10_telemetry logic.
        Specifically correct mapping of RPM and Setpoint.
        """
        # Mock Packet: [24][Len]... [Sub=69][Obj=87] ...
        # Layout based on ProtocolHandler:
        # 0-4: Voltage
        # 8-12: Current
        # 16-20: Power
        # 20-24: Speed

        sub_id = 69  # 0x45
        obj_id = 87  # 0x57

        # Construct payload
        volt_bytes = struct.pack(">f", 230.0)
        curr_bytes = struct.pack(">f", 1.5)
        pwr_bytes = struct.pack(">f", 100.0)
        speed_bytes = struct.pack(">f", 3000.0)
        padding = bytes(4)

        # Layout: V(4) + Pad(4) + I(4) + Pad(4) + P(4) + S(4)
        payload = (
            volt_bytes
            + padding
            + curr_bytes
            + padding
            + pwr_bytes
            + speed_bytes
        )

        # Build Packet manually to simulate device response
        # [24][Len][Dst][Src][0A][Op][Sub][Obj][Data]
        length = 10 + len(payload)

        packet = bytearray(
            [
                RESPONSE_START,
                length,
                0xF8,  # Dest (Client)
                0xE7,  # Src (Pump)
                CLASS_10,
                0x00,  # Op
                (sub_id >> 8) & 0xFF,
                sub_id & 0xFF,
                (obj_id >> 8) & 0xFF,
                obj_id & 0xFF,
            ]
        )
        packet.extend(payload)
        packet.extend([0x00, 0x00])  # Fake CRC

        frame = FrameParser.parse_frame(bytes(packet))
        data = TelemetryDecoder.decode(frame)

        assert data["speed_rpm"] == 3000.0
        assert data["power_w"] == 100.0
        assert data["voltage_ac_v"] == 230.0
        assert data["current_a"] == 1.5

    def test_telemetry_decoder_legacy_setpoint(self):
        """
        Test decoding of Legacy 2F01 Object as Setpoint RPM.
        """
        # Packet containing ... 2F 01 ... [6 bytes] ... [U16 RPM]
        # RPM Raw = 15000 (0x3A98) -> 1500.0 RPM

        prefix = bytes.fromhex("240000000A0000000000")  # Dummy header
        obj_marker = bytes.fromhex("2F01")
        padding = bytes(6)  # Was 8, reset to 6 to match offset 8
        val = struct.pack(">H", 15000)

        packet = prefix + obj_marker + padding + val + padding

        data = TelemetryDecoder.decode_legacy_packet(packet)

        assert "setpoint_rpm" in data
        assert data["setpoint_rpm"] == 1500.0
        # Crucial: Should NOT set 'speed_rpm'
        assert "speed_rpm" not in data

    def test_build_command_info_remote_enable(self):
        """
        Verify construction of 'Enable Remote' INFO Command.
        Used to unlock control.
        """
        # build_command_info(0x03, 0x07, source=0xF8)
        # Expected header: [27][Len][E7][F8][03][OpLen][07]
        # OpLen = (OS_INFO << 6) | data_length = (0 << 6) | 1 = 0x01

        cmd = FrameBuilder.build_command_info(0x03, 0x07, source=0xF8)

        assert cmd[0] == FRAME_START
        assert cmd[2] == SERVICE_ID_HIGH
        assert cmd[3] == 0xF8

        # APDU starts at 4
        # Class 3
        assert cmd[4] == 0x03
        # OpByte: (0 << 6) | 1 = 0x01
        assert cmd[5] == 0x01
        # ID Byte
        assert cmd[6] == 0x07

        # CRC
        payload_for_crc = cmd[1:-2]
        expected_crc = calc_crc16_read(payload_for_crc)
        assert (cmd[-2] << 8 | cmd[-1]) == expected_crc

    def test_telemetry_decoder_flow_head(self):
        """
        Test FrameBuilder.parse_class10_telemetry for Flow/Head (Sub 0x122, Obj 0x5D).
        """
        sub_id = 0x0122
        obj_id = 0x005D

        # Flow = 2.5 m3/h, Head = 4.0 m
        flow_bytes = struct.pack(">f", 2.5)
        head_bytes = struct.pack(">f", 4.0)
        payload = flow_bytes + head_bytes

        length = 10 + len(payload)
        packet = bytearray(
            [
                RESPONSE_START,
                length,
                0xF8,
                0xE7,
                CLASS_10,
                0x00,
                (sub_id >> 8) & 0xFF,
                sub_id & 0xFF,
                (obj_id >> 8) & 0xFF,
                obj_id & 0xFF,
            ]
        )
        packet.extend(payload)
        packet.extend([0x00, 0x00])

        frame = FrameParser.parse_frame(bytes(packet))
        data = TelemetryDecoder.decode(frame)

        assert data["flow_m3h"] == 2.5
        assert data["head_m"] == 4.0

    def test_telemetry_decoder_temperature(self):
        """
        Test FrameBuilder.parse_class10_telemetry for Temperature (Sub 0x12C, Obj 0x5D).
        """
        sub_id = 0x012C
        obj_id = 0x005D

        # Media Temp = 45.5 C
        temp_bytes = struct.pack(">f", 45.5)
        payload = temp_bytes

        length = 10 + len(payload)
        packet = bytearray(
            [
                RESPONSE_START,
                length,
                0xF8,
                0xE7,
                CLASS_10,
                0x00,
                (sub_id >> 8) & 0xFF,
                sub_id & 0xFF,
                (obj_id >> 8) & 0xFF,
                obj_id & 0xFF,
            ]
        )
        packet.extend(payload)
        packet.extend([0x00, 0x00])

        frame = FrameParser.parse_frame(bytes(packet))
        data = TelemetryDecoder.decode(frame)

        assert data["media_temperature_c"] == 45.5
