# Packet Trace: Alarms and Warnings

This document describes how to query and parse alarm/warning status from the ALPHA HWR pump.

## Overview

The ALPHA HWR reports active alarms and warnings through **Object 88** using the Active Query Response format. Unlike other telemetry that streams automatically via notifications, alarm/warning status must be queried explicitly.

## Query Format

Alarms and warnings use the standard Class 10 READ operation (OpSpec 0x03):

```
[Start] [Length] [Src] [Dest] [Class] [OpSpec] [Reg-H] [Reg-M] [Reg-L] [CRC]
```

### Query Alarms (Object 88, Sub 0)

Register address: `0x580000`

```
27 07 E7 F8 0A 03 58 00 00 XX XX
```

**Breakdown:**
- `27`: Request start byte
- `07`: Length (7 bytes total)
- `E7`: Source (Client)
- `F8`: Destination (Pump)
- `0A`: Class 10
- `03`: OpSpec (READ)
- `58 00 00`: Register (Obj=88, Sub=0 for alarms)
- `XX XX`: CRC16

### Query Warnings (Object 88, Sub 11)

Register address: `0x58000B`

```
27 07 E7 F8 0A 03 58 00 0B XX XX
```

**Breakdown:**
- Same as alarms query
- `58 00 0B`: Register (Obj=88, Sub=11 for warnings)

## Response Format

The pump responds with **OpSpec 0x09** (Active Query Response), using the same format as other register-read responses (0x30, 0x2B, 0x14):

```
[Start] [Length] [Dest] [Src] [Class] [OpSpec] [Seq-H] [Seq-L] [ID-H] [ID-L] [Res-H] [Res-L] [DataLen] [Data...] [CRC]
```

### No Active Alarms Response

**Validated on real hardware (ESPHome implementation):**

```
24 0D F8 E7 0A 09 00 02 3A 01 00 00 02 00 00 DC 50
```

**Breakdown:**
- `24`: Response start byte
- `0D`: Length (13 bytes)
- `F8`: Destination (Client)
- `E7`: Source (Pump)
- `0A`: Class 10
- `09`: OpSpec (Active Query Response)
- `00 02`: Sequence number
- `3A 01`: ID field (depends on register queried)
- `00 00`: Reserved
- `02`: DataLen (2 bytes of data)
- `00 00`: Data (uint16 = 0x0000, meaning "no alarms")
- `DC 50`: CRC16

**Interpretation:** The data value `0x0000` means there are no active alarms or warnings. This is the normal/healthy state.

### Active Alarms Response

**Example with alarm codes 42 and 7:**

```
24 11 F8 E7 0A 09 00 03 58 00 00 00 06 00 2A 00 07 00 00 XX XX
```

**Breakdown:**
- `24`: Response start byte
- `11`: Length (17 bytes)
- `F8`: Destination (Client)
- `E7`: Source (Pump)
- `0A`: Class 10
- `09`: OpSpec (Active Query Response)
- `00 03`: Sequence number
- `58 00`: ID field (Obj=88, Sub=0 for alarms)
- `00 00`: Reserved
- `06`: DataLen (6 bytes of data)
- `00 2A`: Alarm code 42 (uint16 big-endian)
- `00 07`: Alarm code 7 (uint16 big-endian)
- `00 00`: Terminating zero (filtered out)
- `XX XX`: CRC16

**Interpretation:** This packet indicates two active alarms with codes 42 and 7.

### Active Warnings Response

Same format as alarms, but ID field reflects Object 88, Sub 11:

```
24 0F F8 E7 0A 09 00 04 58 0B 00 00 04 00 05 00 00 XX XX
```

**Breakdown:**
- `58 0B`: ID field (Obj=88, Sub=11 for warnings)
- `04`: DataLen (4 bytes)
- `00 05`: Warning code 5
- `00 00`: Terminating zero (filtered out)

## Data Format

### Payload Structure

The data section contains an array of **uint16 values in big-endian format**:

```
[Code1-H] [Code1-L] [Code2-H] [Code2-L] ... [0x00] [0x00]
```

**Important Notes:**
- Each alarm/warning code is a 2-byte unsigned integer
- Byte order is **big-endian** (high byte first)
- A code value of `0x0000` means "no alarm/warning"
- Zero codes should be filtered out when parsing
- The array is typically terminated with a zero value

### Example Parsing (Python)

```python
import struct

def parse_alarm_response(packet: bytes) -> list[int]:
    """Parse alarm/warning codes from OpSpec 0x09 response."""
    if len(packet) < 13:
        return []
    
    # Extract data length at offset 12
    data_len = packet[12]
    
    # Parse uint16 array starting at offset 13
    codes = []
    offset = 13
    while offset + 2 <= len(packet) - 2 and offset < 13 + data_len:
        code = struct.unpack(">H", packet[offset:offset+2])[0]
        if code != 0:  # Filter out zero codes
            codes.append(code)
        offset += 2
    
    return codes

# Example: No alarms
packet = bytes.fromhex("24 0D F8 E7 0A 09 00 02 3A 01 00 00 02 00 00 DC 50")
print(parse_alarm_response(packet))  # Output: []

# Example: Active alarms 42 and 7
packet = bytes.fromhex("24 11 F8 E7 0A 09 00 03 58 00 00 00 06 00 2A 00 07 00 00 XX XX")
print(parse_alarm_response(packet))  # Output: [42, 7]
```

## OpSpec 0x09 Details

### OpSpec Byte Structure

The OpSpec byte `0x09` can be decoded as follows:

```
0x09 = 0b00001001
       ││     └─┴─ Bits 0-4: Data length indicator (9)
       │└──────── Bit 5: Reserved
       │└───────── Bit 6: Error flag (0 = success)
       └────────── Bit 7: Reserved
```

### Active Query Response Format

OpSpec 0x09 uses the **Active Query Response** layout, which is shared with other register-read responses:

- **OpSpec 0x30**: Motor state response
- **OpSpec 0x2B**: Flow/pressure response
- **OpSpec 0x14**: Temperature response
- **OpSpec 0x09**: Alarm/warning response

All these OpSpecs use the 7-byte header before data:

```
[OpSpec] [Seq-H] [Seq-L] [ID-H] [ID-L] [Res-H] [Res-L] [DataLen] [Data...]
```

The key difference is that OpSpec 0x09 contains **uint16 codes** rather than **IEEE 754 floats**.

## Integration Notes

### Polling Frequency

Unlike streaming telemetry, alarms/warnings must be polled:

- **Recommended interval**: 5-10 seconds
- **Minimum interval**: 1 second (avoid overwhelming the pump)
- **On-demand**: Query after pump mode changes or errors

### Error Handling

- If the pump doesn't respond, retry after 2-3 seconds
- If you receive malformed data, log the raw packet hex for debugging
- Empty response (DataLen=0) should be treated as "no data available"

### Home Assistant Integration

Example ESPHome text sensor configuration:

```yaml
text_sensor:
  - platform: ble_client
    name: "Active Alarms"
    id: active_alarms
    # Updated when alarm query response received
    
  - platform: ble_client
    name: "Active Warnings"
    id: active_warnings
    # Updated when warning query response received
```

## Historical Context

### Initial Confusion (Now Resolved)

Early Python implementations incorrectly expected **OpSpec 0x13** for alarm responses. This was based on speculation before hardware validation.

**Hardware validation (ESPHome, Feb 2025)** confirmed that the pump actually responds with **OpSpec 0x09**, using the standard Active Query Response format.

### Key Discovery

The breakthrough came from analyzing 100+ real packet captures showing consistent OpSpec 0x09 responses with data value `0x0000`, which was initially misinterpreted as "not supported." In reality, `0x0000` simply means "no active alarms."

## References

- [Protocol: Telemetry](../telemetry.md) - General telemetry overview
- [Protocol: Wire Format](../wire_format.md) - GENI packet structure
- [ESPHome Implementation](https://github.com/eman/esphome-alpha-hwr) - Reference C++ decoder
- [Python Implementation](https://github.com/eman/alpha-hwr) - Reference Python decoder

## Validation

This documentation is based on:

- 100+ real packet captures from ALPHA HWR pump (Feb 2025)
- Successful ESPHome C++ implementation (tested on ESP32-C3)
- Cross-validation between Python and ESPHome implementations
- Protocol documentation at https://eman.github.io/alpha-hwr/reimplementation/
