import struct

from wire import class10_reply

from alpha_hwr.protocol.codec import decode_float_be, encode_float_be
from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.protocol.telemetry_decoder import TelemetryDecoder


class TestProtocolExpanded:
    def test_float_encoding(self):
        val = 123.456
        encoded = encode_float_be(val)
        assert len(encoded) == 4
        decoded = decode_float_be(encoded, 0)
        assert decoded is not None
        assert abs(decoded - val) < 0.001

    def test_parse_packet_structure(self):
        # Valid Header
        # Header needs to be at least 10 bytes for full Class 10 parse or just enough for 'valid'
        # parse_packet checks: data[0] in [START, RESP] and len > 6
        # To get class=10, data[4] == 10.
        # To get sub/obj, len > 9.

        # A reply's bytes 6-9 are [00][TypeH][TypeL][Version], not a
        # Sub-ID and Object ID. This frame used to be built with a length
        # byte of 5 - declaring nine bytes while carrying ten - and an
        # APDU head of 0, declaring no payload at all; it then asserted
        # that four bytes of that absent payload had been extracted.
        pkt = class10_reply(0x0001, 0x0203, b"\x04")

        res = FrameParser.parse_frame(pkt)
        assert res.valid
        assert res.crc_valid
        assert res.class_byte == 10
        assert res.type_high == 0x0001
        assert res.type_low_ver == 0x0203

    def test_class10_temperature_parsing(self):
        """Test Class 10 Temperature Object (Sub 300) Parsing."""
        # Media (0-4), PCB (4-8), ControlBox (8-12)
        # Type 534: 3 floats
        payload = bytearray(12)
        payload[0:4] = struct.pack(">f", 25.5)  # Media
        payload[4:8] = struct.pack(">f", 40.0)  # PCB
        payload[8:12] = struct.pack(">f", 30.0)  # Control Box

        # Temperatures answer as type 0x1602 version 2 (measured
        # 2026-08-20). The frame this replaced declared a 20-byte length
        # while carrying 24, an APDU head of 0 declaring no payload, and
        # two zero bytes where the CRC goes - so it tested neither the
        # length field nor the checksum.
        packet = class10_reply(0x0002, 0x1602, bytes(payload))

        frame = FrameParser.parse_frame(packet)
        assert frame.crc_valid
        data = TelemetryDecoder.decode(frame)

        assert data["media_temperature_c"] == 25.5
        assert data["pcb_temperature_c"] == 40.0
        assert data["control_box_temperature_c"] == 30.0
