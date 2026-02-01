from .constants import CRC_TABLE


def calc_crc16(data: bytes, init: int = 0xFFFF) -> int:
    """Calculate CRC-16-CCITT checksum (No Final XOR). Used for Writes."""
    crc = init
    for byte in data:
        crc = ((crc << 8) ^ CRC_TABLE[((crc >> 8) ^ byte) & 0xFF]) & 0xFFFF
    return crc


def calc_crc16_read(data: bytes, init: int = 0xFFFF) -> int:
    """Calculate CRC-16-CCITT checksum (With Final XOR). Used for Reads/Execute."""
    crc = calc_crc16(data, init)
    return crc ^ 0xFFFF
