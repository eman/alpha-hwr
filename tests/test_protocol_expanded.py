import struct
from alpha_hwr.protocol.frame_builder import FrameBuilder
from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.protocol.telemetry_decoder import TelemetryDecoder
from alpha_hwr.protocol.codec import encode_float_be, decode_float_be
from alpha_hwr.constants import RESPONSE_START


class TestProtocolExpanded:
    def test_float_encoding(self):
        val = 123.456
        encoded = encode_float_be(val)
        assert len(encoded) == 4
        decoded = decode_float_be(encoded, 0)
        assert abs(decoded - val) < 0.001

    
    
    
    def test_parse_packet_structure(self):
        # Valid Header
        # Header needs to be at least 10 bytes for full Class 10 parse or just enough for 'valid'
        # parse_packet checks: data[0] in [START, RESP] and len > 6
        # To get class=10, data[4] == 10.
        # To get sub/obj, len > 9.

        pkt = bytes(
            [RESPONSE_START, 0x05, 0x00, 0x00, 10, 0x00, 0x01, 0x02, 0x03, 0x04]
        )
        # Len=10. Index 4=10 (Class). Index 6,7=0x0102 (Sub). Index 8,9=0x0304 (Obj).

        res = FrameParser.parse_frame(pkt)
        assert res.class_byte == 10
        assert res.sub_id == 0x0102
        assert res.obj_id == 0x0304

    def test_build_write_request(self):
        # Test 2-byte register write
        # Reg 0x1234, Value 0xABCD
        # Header + Reg(2) + Val(?)
        # Write Request typically writes 1 byte unless value is bytes?
        # Default value=1

        pkt = FrameBuilder.build_write_request(0x1234, 0x05)
        # Check op code WRITE (0xC1/193) in header
        # Header: START(1) LEN(1) DEST(1) SRC(1) RES(1) OP(1)
        assert pkt[5] == 0xC1
        # Register: 12 34
        assert pkt[6] == 0x12
        assert pkt[7] == 0x34
        # Value: 05
        assert pkt[8] == 0x05

    def test_class10_temperature_parsing(self):
        """Test Class 10 Temperature Object (Sub 300) Parsing."""
        # Media (0-4), PCB (4-8), ControlBox (8-12)
        # Type 534: 3 floats
        payload = bytearray(12)
        payload[0:4] = struct.pack(">f", 25.5)  # Media
        payload[4:8] = struct.pack(">f", 40.0)  # PCB
        payload[8:12] = struct.pack(">f", 30.0)  # Control Box

        # Build packet: [START] [LEN?] [DEST] [SRC] [CLASS=10] [OP] [SUB_H] [SUB_L] [OBJ_H] [OBJ_L] [PAYLOAD...] [CRC_H] [CRC_L]
        # Length is not checked strictly in parser, but structure is.
        # SubID = 300 = 0x012C
        # ObjID = 93 = 0x5D = 0x005D

        header = bytes(
            [RESPONSE_START, 20, 0x01, 0x02, 0x0A, 0x00, 0x01, 0x2C, 0x00, 0x5D]
        )
        crc = bytes([0x00, 0x00])
        packet = header + payload + crc

        # Call parse and decode
        frame = FrameParser.parse_frame(packet)
        data = TelemetryDecoder.decode(frame)

        assert data["media_temperature_c"] == 25.5
        assert data["pcb_temperature_c"] == 40.0
        assert data["control_box_temperature_c"] == 30.0
