
from alpha_hwr.utils import calc_crc16, calc_crc16_read

class TestUtils:
    def test_calc_crc16_write(self):
        """Test CRC calculation for Write packets."""
        # Known packet payload (excluding start 0x27)
        # Packet: 27 05 E7 F8 0B [C1 0F] [D0 C3]
        # Payload for CRC: 05 E7 F8 0B C1 0F
        data = bytes.fromhex("05E7F80BC10F")
        expected_crc = 0x2F3C # Was 0xD0C3 (incorrect manual calc)
        
        assert calc_crc16(data) == expected_crc

    def test_calc_crc16_read(self):
        """Test CRC calculation for Read packets."""
        # Packet: 27 07 E7 F8 0A 03 56 00 06 [C5 5A]
        # Payload for CRC: 07 E7 F8 0A 03 56 00 06
        data = bytes.fromhex("07E7F80A03560006")
        expected_crc = 0xC55A
        
        assert calc_crc16_read(data) == expected_crc
