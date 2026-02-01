import re
import platform
from typing import Optional
from .constants import CRC_TABLE


def is_mac_address(address: str) -> bool:
    """Check if a string is a valid MAC address."""
    return bool(re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", address))


def is_uuid(address: str) -> bool:
    """Check if a string is a valid UUID."""
    return bool(
        re.match(
            r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$",
            address,
        )
    )


def resolve_platform_address(address_string: str) -> Optional[str]:
    """
    Pick the appropriate address from a potential list based on the current platform.

    Supports single addresses or comma-separated lists.
    """
    if not address_string:
        return None

    addresses = [a.strip() for a in address_string.split(",")]
    system = platform.system()

    if system == "Darwin":  # macOS
        # Look for UUID first
        for addr in addresses:
            if is_uuid(addr):
                return addr
    else:  # Linux/Windows
        # Look for MAC address first
        for addr in addresses:
            if is_mac_address(addr):
                return addr

    # Fallback to first address if no format match found
    return addresses[0] if addresses else None


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
