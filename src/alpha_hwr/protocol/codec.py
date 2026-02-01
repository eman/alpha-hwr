"""
Codec module for GENI protocol primitive encoding/decoding.

This module provides functions for encoding and decoding basic data types
used in the GENI protocol. All multi-byte values use Big-Endian byte order.

Data Types
----------
- Float (32-bit IEEE 754): Used for telemetry values (flow, pressure, power, etc.)
- Uint16 (16-bit unsigned): Used for integer values, alarms, etc.
- Uint32 (32-bit unsigned): Used for timestamps, counters, etc.

Byte Order: Big-Endian
-----------------------
All GENI protocol values use network byte order (big-endian).

Examples:
- Float 1.5 = 0x3FC00000 = bytes [3F, C0, 00, 00]
- Uint16 1000 = 0x03E8 = bytes [03, E8]
- Uint32 1234567890 = 0x499602D2 = bytes [49, 96, 02, D2]

For reference implementations in other languages, use platform-native
big-endian encoding functions or manual bit shifting.

Reference Implementations
-------------------------

C:
```c
// Float encoding (big-endian)
void encode_float_be(float value, uint8_t *bytes) {
    uint32_t temp;
    memcpy(&temp, &value, 4);
    bytes[0] = (temp >> 24) & 0xFF;
    bytes[1] = (temp >> 16) & 0xFF;
    bytes[2] = (temp >> 8) & 0xFF;
    bytes[3] = temp & 0xFF;
}

// Float decoding (big-endian)
float decode_float_be(const uint8_t *bytes) {
    uint32_t temp = (bytes[0] << 24) | (bytes[1] << 16) |
                    (bytes[2] << 8) | bytes[3];
    float value;
    memcpy(&value, &temp, 4);
    return value;
}
```

JavaScript:
```javascript
// Float encoding
function encodeFloatBE(value) {
    const buffer = new ArrayBuffer(4);
    const view = new DataView(buffer);
    view.setFloat32(0, value, false); // false = big-endian
    return new Uint8Array(buffer);
}

// Float decoding
function decodeFloatBE(bytes, offset) {
    const view = new DataView(bytes.buffer);
    return view.getFloat32(offset, false); // false = big-endian
}
```

Rust:
```rust
// Float encoding
fn encode_float_be(value: f32) -> [u8; 4] {
    value.to_be_bytes()
}

// Float decoding
fn decode_float_be(bytes: &[u8]) -> f32 {
    f32::from_be_bytes(bytes[0..4].try_into().unwrap())
}
```
"""

import struct


def encode_float_be(value: float) -> bytes:
    """
    Encode a float as 4-byte big-endian IEEE 754.

    Parameters
    ----------
    value : float
        Value to encode

    Returns
    -------
    bytes
        4 bytes in big-endian order

    Examples
    --------
    >>> encode_float_be(1.5)
    b'\\x3f\\xc0\\x00\\x00'

    >>> encode_float_be(100.0)
    b'B\\xc8\\x00\\x00'

    Notes
    -----
    Uses Python struct module with format '>f':
    - '>' = big-endian
    - 'f' = float (4 bytes, IEEE 754)
    """
    return struct.pack(">f", value)


def decode_float_be(data: bytes, offset: int = 0) -> float | None:
    """
    Decode a big-endian float from bytes.

    Parameters
    ----------
    data : bytes
        Byte array containing float
    offset : int, default=0
        Starting position in byte array

    Returns
    -------
    float | None
        Decoded float value, or None if insufficient bytes

    Examples
    --------
    >>> data = b'\\x3f\\xc0\\x00\\x00'
    >>> decode_float_be(data)
    1.5

    >>> data = b'\\x00\\x00B\\xc8\\x00\\x00'
    >>> decode_float_be(data, offset=2)
    100.0

    >>> decode_float_be(b'\\x00\\x00')  # Not enough bytes
    None

    Notes
    -----
    Returns None if there aren't enough bytes from offset.
    This is safer than raising exceptions during telemetry parsing.
    """
    if offset + 4 > len(data):
        return None
    return struct.unpack(">f", data[offset : offset + 4])[0]


def encode_uint16_be(value: int) -> bytes:
    """
    Encode a 16-bit unsigned integer as big-endian bytes.

    Parameters
    ----------
    value : int
        Value to encode (0-65535)

    Returns
    -------
    bytes
        2 bytes in big-endian order

    Examples
    --------
    >>> encode_uint16_be(1000)
    b'\\x03\\xe8'

    >>> encode_uint16_be(0)
    b'\\x00\\x00'

    >>> encode_uint16_be(65535)
    b'\\xff\\xff'

    Notes
    -----
    Values outside 0-65535 will wrap around (mod 65536).
    """
    return struct.pack(">H", value)


def decode_uint16_be(data: bytes, offset: int = 0) -> int | None:
    """
    Decode a big-endian 16-bit unsigned integer.

    Parameters
    ----------
    data : bytes
        Byte array containing integer
    offset : int, default=0
        Starting position in byte array

    Returns
    -------
    int | None
        Decoded integer (0-65535), or None if insufficient bytes

    Examples
    --------
    >>> data = b'\\x03\\xe8'
    >>> decode_uint16_be(data)
    1000

    >>> data = b'\\x00\\x00\\xff\\xff'
    >>> decode_uint16_be(data, offset=2)
    65535
    """
    if offset + 2 > len(data):
        return None
    return struct.unpack(">H", data[offset : offset + 2])[0]


def encode_uint32_be(value: int) -> bytes:
    """
    Encode a 32-bit unsigned integer as big-endian bytes.

    Parameters
    ----------
    value : int
        Value to encode (0-4294967295)

    Returns
    -------
    bytes
        4 bytes in big-endian order

    Examples
    --------
    >>> encode_uint32_be(1234567890)
    b'I\\x96\\x02\\xd2'

    >>> encode_uint32_be(0)
    b'\\x00\\x00\\x00\\x00'
    """
    return struct.pack(">I", value)


def decode_uint32_be(data: bytes, offset: int = 0) -> int | None:
    """
    Decode a big-endian 32-bit unsigned integer.

    Parameters
    ----------
    data : bytes
        Byte array containing integer
    offset : int, default=0
        Starting position in byte array

    Returns
    -------
    int | None
        Decoded integer (0-4294967295), or None if insufficient bytes

    Examples
    --------
    >>> data = b'I\\x96\\x02\\xd2'
    >>> decode_uint32_be(data)
    1234567890
    """
    if offset + 4 > len(data):
        return None
    return struct.unpack(">I", data[offset : offset + 4])[0]


def encode_int16_be(value: int) -> bytes:
    """
    Encode a 16-bit signed integer as big-endian bytes.

    Parameters
    ----------
    value : int
        Value to encode (-32768 to 32767)

    Returns
    -------
    bytes
        2 bytes in big-endian order
    """
    return struct.pack(">h", value)


def decode_int16_be(data: bytes, offset: int = 0) -> int | None:
    """
    Decode a big-endian 16-bit signed integer.

    Parameters
    ----------
    data : bytes
        Byte array containing integer
    offset : int, default=0
        Starting position in byte array

    Returns
    -------
    int | None
        Decoded integer (-32768 to 32767), or None if insufficient bytes
    """
    if offset + 2 > len(data):
        return None
    return struct.unpack(">h", data[offset : offset + 2])[0]


# ==========================================================================
# TESTING AND VALIDATION
# ==========================================================================
"""
Test Vectors for Codec Validation
==================================

Use these test vectors to validate implementations in other languages:

Float Encoding (Big-Endian IEEE 754):
--------------------------------------
Value       Hex Bytes           Binary
1.5     ->  3F C0 00 00     ->  0011 1111 1100 0000 0000 0000 0000 0000
100.0   ->  42 C8 00 00     ->  0100 0010 1100 1000 0000 0000 0000 0000
-1.5    ->  BF C0 00 00     ->  1011 1111 1100 0000 0000 0000 0000 0000
0.0     ->  00 00 00 00     ->  0000 0000 0000 0000 0000 0000 0000 0000
9806.65 ->  45 19 41 47     ->  0100 0101 0001 1001 0100 0001 0100 0111

Uint16 Encoding (Big-Endian):
-----------------------------
Value       Hex Bytes       Binary
0       ->  00 00       ->  0000 0000 0000 0000
1000    ->  03 E8       ->  0000 0011 1110 1000
65535   ->  FF FF       ->  1111 1111 1111 1111
2500    ->  09 C4       ->  0000 1001 1100 0100

Uint32 Encoding (Big-Endian):
-----------------------------
Value          Hex Bytes           Binary
0          ->  00 00 00 00     ->  0x00000000
1234567890 ->  49 96 02 D2     ->  0x499602D2
4294967295 ->  FF FF FF FF     ->  0xFFFFFFFF

Validation Code (Python):
-------------------------
```python
from alpha_hwr.protocol.codec import *

# Test float encoding
assert encode_float_be(1.5) == bytes([0x3F, 0xC0, 0x00, 0x00])
assert encode_float_be(100.0) == bytes([0x42, 0xC8, 0x00, 0x00])

# Test float decoding
assert decode_float_be(bytes([0x3F, 0xC0, 0x00, 0x00])) == 1.5
assert decode_float_be(bytes([0x42, 0xC8, 0x00, 0x00])) == 100.0

# Test uint16
assert encode_uint16_be(1000) == bytes([0x03, 0xE8])
assert decode_uint16_be(bytes([0x03, 0xE8])) == 1000

# Test uint32
assert encode_uint32_be(1234567890) == bytes([0x49, 0x96, 0x02, 0xD2])
assert decode_uint32_be(bytes([0x49, 0x96, 0x02, 0xD2])) == 1234567890
```
"""
