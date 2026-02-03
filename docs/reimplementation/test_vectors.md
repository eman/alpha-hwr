# Test Vectors

This document provides test vectors for validating your implementation. Each section includes inputs, expected outputs, and explanations.

## 1. CRC-16/MODBUS Calculation

All GENI frames use CRC-16/MODBUS (polynomial 0x8005, initial value 0xFFFF).

### Test Vector 1.1: Simple Packet

**Input bytes:**
```
0x27 0x07 0xE7 0xF8 0x02 0x03 0x94 0x95 0x96
```

**Expected CRC:**
```
0xEB47
```

**Breakdown:**
- CRC bytes: `0xEB` (high), `0x47` (low)
- Full packet: `27 07 E7 F8 02 03 94 95 96 EB 47`

**Validation:**
```python
data = bytes([0x27, 0x07, 0xE7, 0xF8, 0x02, 0x03, 0x94, 0x95, 0x96])
crc = calculate_crc16_modbus(data)
assert crc == 0xEB47
```

### Test Vector 1.2: Authentication Packet

**Input bytes:**
```
0x27 0x07 0xE7 0xF8 0x0A 0x03 0x56 0x00 0x06
```

**Expected CRC:**
```
0xC55A
```

**Full packet:**
```
27 07 E7 F8 0A 03 56 00 06 C5 5A
```

### Test Vector 1.3: Zero-Length Payload

**Input bytes:**
```
0x27 0x05 0xE7 0xF8
```

**Expected CRC:**
```
0x1F0D
```

## 2. IEEE 754 Big-Endian Float Encoding

All float values use IEEE 754 single-precision big-endian format.

### Test Vector 2.1: Positive Float (1.5)

**Decimal Value:** `1.5`

**Expected Bytes:**
```
0x3F 0xC0 0x00 0x00
```

**Binary Breakdown:**
```
Sign: 0 (positive)
Exponent: 01111111 (127, biased)
Mantissa: 10000000000000000000000
```

**Validation:**
```python
value = 1.5
encoded = encode_float_be(value)
assert encoded == bytes([0x3F, 0xC0, 0x00, 0x00])
decoded = decode_float_be(encoded)
assert decoded == 1.5
```

### Test Vector 2.2: Pressure Value (14710.0 Pa)

**Decimal Value:** `14710.0` (1.5m water = 14710 Pa)

**Expected Bytes:**
```
0x46 0xE5 0xB0 0x00
```

**Validation:**
```python
pressure_pa = 14710.0
encoded = encode_float_be(pressure_pa)
assert encoded == bytes([0x46, 0xE5, 0xB0, 0x00])
```

### Test Vector 2.3: Small Flow Rate (0.5 m³/h)

**Decimal Value:** `0.5`

**Expected Bytes:**
```
0x3F 0x00 0x00 0x00
```

### Test Vector 2.4: Zero

**Decimal Value:** `0.0`

**Expected Bytes:**
```
0x00 0x00 0x00 0x00
```

### Test Vector 2.5: Negative Temperature (-5.5°C)

**Decimal Value:** `-5.5`

**Expected Bytes:**
```
0xC0 0xB0 0x00 0x00
```

**Note:** Sign bit is 1 for negative numbers.

## 3. Uint16 Big-Endian Encoding

### Test Vector 3.1: Small Value

**Decimal Value:** `256`

**Expected Bytes:**
```
0x01 0x00
```

### Test Vector 3.2: Max Value

**Decimal Value:** `65535`

**Expected Bytes:**
```
0xFF 0xFF
```

### Test Vector 3.3: Sub ID (0x5600)

**Decimal Value:** `0x5600` (22016)

**Expected Bytes:**
```
0x56 0x00
```

## 4. Uint32 Big-Endian Encoding

### Test Vector 4.1: Register Address

**Decimal Value:** `0x5D012C` (6095148)

**Expected Bytes:**
```
0x00 0x5D 0x01 0x2C
```

### Test Vector 4.2: Operating Hours

**Decimal Value:** `123456` seconds

**Expected Bytes:**
```
0x00 0x01 0xE2 0x40
```

## 5. Complete Frame Building

### Test Vector 5.1: Legacy Magic Packet

**Purpose:** First authentication packet

**Expected Full Packet:**
```
27 07 E7 F8 02 03 94 95 96 EB 47
```

**Breakdown:**
- `27`: Start byte
- `07`: Length (7 bytes including start and length)
- `E7`: Service ID
- `F8`: Source address
- `02 03 94 95 96`: Payload (Class 2, OpSpec 0x03, Register 0x9495, Value 0x96)
- `EB 47`: CRC-16

### Test Vector 5.2: Class 10 Unlock Packet

**Purpose:** Unlock Class 10 commands

**Expected Full Packet:**
```
27 07 E7 F8 0A 03 56 00 06 C5 5A
```

**Breakdown:**
- `27`: Start byte
- `07`: Length
- `E7`: Service ID
- `F8`: Source
- `0A`: Class byte (Class 10)
- `03 56 00 06`: APDU (OpSpec 0x03, Sub 0x5600, Obj 0x0006)
- `C5 5A`: CRC-16

### Test Vector 5.3: Info Command (Read Temperature)

**Purpose:** Read register 0x5D012C

**Expected Full Packet:**
```
27 0B E7 F8 03 02 00 5D 01 2C 00 XX XX
```

**Breakdown:**
- `27`: Start byte
- `0B`: Length (11 bytes)
- `E7`: Service ID
- `F8`: Source
- `03`: Class 3
- `02`: Op-spec (INFO)
- `00 5D 01 2C`: Register address (big-endian)
- `00`: Additional byte
- `XX XX`: CRC-16 (calculate)

### Test Vector 5.4: Class 10 SET Command

**Purpose:** Set constant pressure mode to 1.5m

**Parameters:**
- Sub ID: `0x5600`
- Obj ID: `0x0601`
- Value: `1.5m` = `14710.0 Pa`

**Expected Packet:**
```
27 10 E7 F8 0A 14 56 00 06 01 46 E5 B0 00 XX XX
```

**Breakdown:**
- `27`: Start byte
- `10`: Length (16 bytes)
- `E7`: Service ID
- `F8`: Source
- `0A`: Class 10
- `14`: Op-spec (SET)
- `56 00`: Sub ID (big-endian)
- `06 01`: Obj ID (big-endian)
- `46 E5 B0 00`: Float value (14710.0)
- `XX XX`: CRC-16 (calculate)

## 6. Frame Parsing

### Test Vector 6.1: Parse Response Frame

**Input Packet:**
```
24 0E E7 20 0A 34 56 00 06 01 46 E5 B0 00 XX XX
```

**Expected Parsed Result:**
- Start byte: `0x24` (response)
- Length: `0x0E` (14 bytes)
- Service ID: `0xE7`
- Source: `0x20` (pump)
- Class: `0x0A` (Class 10)
- Op-spec: `0x34` (SET response)
- Sub ID: `0x5600`
- Obj ID: `0x0601`
- Payload: `46 E5 B0 00` (float 14710.0)
- CRC valid: `true`

### Test Vector 6.2: Parse Telemetry Notification

**Input Packet:**
```
24 XX E7 20 0A 34 00 45 00 57 [44 bytes of telemetry] XX XX
```

**Expected Parsed Result:**
- Response frame
- Class 10
- Sub ID: `0x0045` (motor state)
- Obj ID: `0x0057`
- Payload: 44 bytes of motor telemetry data

## 7. Telemetry Decoding

### Test Vector 7.1: Motor State Payload

**Input Payload (44 bytes):**
```
43 66 00 00  // Offset 0-3: Grid voltage (230.0V)
3E CC CC CD  // Offset 8-11: Current (0.4A)
42 48 00 00  // Offset 16-19: Power (50.0W)
44 BB 80 00  // Offset 20-23: Speed (1500.0 RPM)
42 28 00 00  // Offset 24-27: Temperature (42.0°C)
...
```

**Expected Decoded Values:**
- Grid voltage: `230.0 V`
- Current: `0.4 A`
- Power: `50.0 W`
- Speed: `1500.0 RPM`
- Temperature: `42.0 °C`

### Test Vector 7.2: Flow/Pressure Payload

**Input Payload (16 bytes):**
```
3F 00 00 00  // Offset 0-3: Flow (0.5 m³/h)
3F C0 00 00  // Offset 4-7: Head (1.5 m)
40 00 00 00  // Offset 8-11: Inlet pressure (2.0 bar)
40 40 00 00  // Offset 12-15: Outlet pressure (3.0 bar)
```

**Expected Decoded Values:**
- Flow: `0.5 m³/h`
- Head: `1.5 m`
- Inlet pressure: `2.0 bar`
- Outlet pressure: `3.0 bar`

## 8. Unit Conversions

### Test Vector 8.1: Meters to Pascals

**Input:** `1.5 m` (head)

**Calculation:**
```
pascals = meters × 9806.65
pascals = 1.5 × 9806.65
pascals = 14709.975 ≈ 14710.0
```

**Expected Output:** `14710.0 Pa`

### Test Vector 8.2: Pascals to Meters

**Input:** `14710.0 Pa`

**Calculation:**
```
meters = pascals / 9806.65
meters = 14710.0 / 9806.65
meters = 1.5
```

**Expected Output:** `1.5 m`

### Test Vector 8.3: Bar to Pascals

**Input:** `2.5 bar`

**Calculation:**
```
pascals = bar × 100000
pascals = 2.5 × 100000
pascals = 250000.0
```

**Expected Output:** `250000.0 Pa`

## 9. End-to-End Test Scenarios

### Scenario 9.1: Read Telemetry

**Step 1: Send INFO command**
```
TX: 27 0D E7 F8 0A 02 00 45 00 57 00 XX XX
```

**Step 2: Receive response**
```
RX: 24 XX E7 20 0A 34 00 45 00 57 [44 bytes] XX XX
```

**Step 3: Decode motor state**
```
Grid: 230.0V
Speed: 1500.0 RPM
Power: 50.0W
```

### Scenario 9.2: Set Control Mode

**Step 1: Build SET command (1.5m constant pressure)**
```
TX: 27 10 E7 F8 0A 14 56 00 06 01 46 E5 B0 00 XX XX
```

**Step 2: Receive ACK**
```
RX: 24 0A E7 20 0A 34 56 00 06 01 XX XX
```

**Step 3: Verify mode**
```
Mode: Constant Pressure
Setpoint: 1.5m
```

## 10. Error Cases

### Test Vector 10.1: Invalid CRC

**Input Packet:**
```
27 07 E7 F8 02 03 94 95 96 FF FF
```

**Expected Result:**
- CRC validation: `FAIL`
- Expected CRC: `0xEB47`
- Actual CRC: `0xFFFF`
- Action: Reject packet

### Test Vector 10.2: Invalid Start Byte

**Input Packet:**
```
FF 06 E7 F8 00 67 A3 E3
```

**Expected Result:**
- Invalid start byte (expected `0x27` or `0x24`)
- Action: Discard packet

### Test Vector 10.3: Length Mismatch

**Input Packet:**
```
27 99 E7 F8 00 67 A3 E3
```

**Expected Result:**
- Declared length: `0x99` (153 bytes)
- Actual packet: 8 bytes
- Action: Timeout or discard

## 11. Active Query (INFO) Response Parsing

Modern implementations use INFO queries to poll telemetry. These responses have a different header layout and specific field offsets.

### Test Vector 11.1: Flow/Pressure Query Response

**Purpose**: Parse and decode a 51-byte response to a Flow/Pressure query (OpSpec 0x2B).

**Input Packet:**
```
24 2F F8 E7 0A 2B 00 02 35 02 00 00 24 39 0A A4 26 46 E5 8A C2 7F FF FF FF 7F FF FF FF 7F FF FF FF 7F FF FF FF 3E F3 B4 8B 40 3F CC D4 3F 60 9F C2 BC 06
```

**Header Breakdown:**
- `24`: Start Delimiter (Response)
- `2F`: Length (47 bytes remaining)
- `F8`: Destination (Client)
- `E7`: Source (Service)
- `0A`: Class 10
- `2B`: **OpSpec (INFO Response)**
- `00 02`: Sequence Number
- `35 02`: Identifier (matches Query)
- `00 00`: Reserved
- `24`: **Data Array Length** (36 bytes = 9 floats)

**Data Array Breakdown (Floats starting at offset 13):**
- Offset 13 (+0): `39 0A A4 26` (Reserved/Unknown)
- Offset 17 (+4): `46 E5 8A C2` (Reserved/Unknown)
- Offset 21 (+8): `7F FF FF FF` (NaN)
- Offset 25 (+12): `7F FF FF FF` (NaN)
- Offset 29 (+16): `7F FF FF FF` (NaN)
- Offset 33 (+20): `7F FF FF FF` (NaN)
- Offset 37 (+24): `3E F3 B4 8B` = **0.476 m³/h** (Flow Rate)
- Offset 41 (+28): `40 3F CC D4` = **2.997 m** (Head Pressure)
- Offset 45 (+32): `3F 60 9F C2` = **0.877 bar** (Inlet Pressure)

**Expected Decoded Values:**
- Flow: `0.476 m³/h`
- Head: `2.997 m`
- Inlet Pressure: `0.877 bar`

**Validation:**
```python
packet = bytes.fromhex("242ff8e70a2b00023502000024390aa42646e58ac27fffffff7fffffff7fffffff7fffffff3ef3b48b403fccd43f609fc2bc06")
frame = FrameParser.parse_frame(packet)
assert frame.obj_id == 0x3502
data = TelemetryDecoder.decode(frame)
assert round(data["flow_m3h"], 3) == 0.476
assert round(data["head_m"], 3) == 2.997
```

## Validation Checklist

Use these test vectors to validate your implementation:

- [ ] CRC calculation matches all test vectors
- [ ] Float encoding produces correct bytes
- [ ] Float decoding produces correct values
- [ ] Uint16/32 encoding is big-endian
- [ ] Frame building produces valid packets
- [ ] Frame parsing extracts correct fields
- [ ] Telemetry decoding matches expected values
- [ ] Unit conversions are accurate
- [ ] Error cases handled correctly

## Language-Specific Examples

### Python

```python
def test_float_encoding():
    assert encode_float_be(1.5) == b'\x3f\xc0\x00\x00'
    assert decode_float_be(b'\x3f\xc0\x00\x00') == 1.5

def test_crc():
    data = bytes([0x27, 0x06, 0xE7, 0xF8, 0x00, 0x67])
    assert calculate_crc16_modbus(data) == 0xA3E3
```

### JavaScript

```javascript
function testFloatEncoding() {
  const encoded = encodeFloatBE(1.5);
  assert.deepEqual(encoded, [0x3F, 0xC0, 0x00, 0x00]);
  
  const decoded = decodeFloatBE([0x3F, 0xC0, 0x00, 0x00]);
  assert.equal(decoded, 1.5);
}
```

### Rust

```rust
#[test]
fn test_float_encoding() {
    let encoded = encode_float_be(1.5);
    assert_eq!(encoded, [0x3F, 0xC0, 0x00, 0x00]);
    
    let decoded = decode_float_be(&[0x3F, 0xC0, 0x00, 0x00]);
    assert_eq!(decoded, 1.5);
}
```

## Reference Implementation

See the Python implementation for complete examples:
- `src/alpha_hwr/protocol_new/codec.py` - Encoding/decoding
- `src/alpha_hwr/protocol_new/frame_builder.py` - Frame construction
- `src/alpha_hwr/protocol_new/frame_parser.py` - Frame parsing
- `tests/protocol_new/` - Test suite with all vectors

## Troubleshooting

If your implementation fails validation:

1. **CRC mismatch**: Verify polynomial (0x8005) and initial value (0xFFFF)
2. **Float encoding wrong**: Ensure big-endian (network byte order)
3. **Frame parsing fails**: Check byte offsets and endianness
4. **Telemetry values wrong**: Verify payload offsets from documentation

## Next Steps

1. Implement each function with test vectors
2. Validate against all test cases
3. Test with real pump hardware
4. Report any discrepancies or issues
