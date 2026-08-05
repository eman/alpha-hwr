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

The reply uses the standard response layout. Its byte 5 reads `0x09`, which is the **payload length** — see [below](#byte-5-is-a-length-not-an-opspec):

```
[Start] [Length] [Dest] [Src] [Class] [Byte5=len] [ID-A (2B)] [ID-B (2B)] [Data...] [CRC]
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
- `09`: payload length (9 bytes)
- `00 02`: Sequence number
- `3A 01`: ID field (depends on register queried)
- `00 00`: Reserved
- `02`: DataLen (2 bytes of data)
- `00 00`: Data (uint16 = 0x0000, meaning "no alarms")
- `DC 50`: CRC16

**Interpretation:** The data value `0x0000` means there are no active alarms or warnings. This is the normal/healthy state.

### Active Alarms Response

!!! note "Constructed, not captured"

    The no-alarm response above is a real capture. This one is **built by
    hand** to show how multiple codes are laid out — a pump with two active
    alarms was not available to record. Its CRC is a placeholder and its
    length fields are illustrative. Trust the field layout, not the bytes.

**Illustrative example, alarm codes 42 and 7:**

```
24 11 F8 E7 0A 09 00 03 58 00 00 00 06 00 2A 00 07 00 00 XX XX
```

**Breakdown:**
- `24`: Response start byte
- `11`: Length (17 bytes)
- `F8`: Destination (Client)
- `E7`: Source (Pump)
- `0A`: Class 10
- `09`: payload length (9 bytes)
- `00 03`: Sequence number
- `58 00`: ID field (Obj=88, Sub=0 for alarms)
- `00 00`: Reserved
- `06`: DataLen (6 bytes of data)
- `00 2A`: Alarm code 42 (uint16 big-endian)
- `00 07`: Alarm code 7 (uint16 big-endian)
- `00 00`: Terminating zero (filtered out)
- `XX XX`: CRC — not computed for this constructed example
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
- `XX XX`: CRC — not computed for this constructed example

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
    """Parse alarm/warning codes from the alarm response."""
    if len(packet) < 13:
        return []

    # Extract data length at offset 12
    data_len = packet[12]

    # Parse uint16 array starting at offset 13
    codes = []
    offset = 13
    while offset + 2 <= len(packet) - 2 and offset < 13 + data_len:
        code = struct.unpack(">H", packet[offset : offset + 2])[0]
        if code != 0:  # Filter out zero codes
            codes.append(code)
        offset += 2

    return codes


# Example: No alarms
packet = bytes.fromhex("24 0D F8 E7 0A 09 00 02 3A 01 00 00 02 00 00 DC 50")
print(parse_alarm_response(packet))  # Output: []

# Example: Active alarms 42 and 7 - CONSTRUCTED, not captured.
# The final two bytes are placeholders; parse_alarm_response ignores them.
packet = bytes.fromhex(
    "24 11 F8 E7 0A 09 00 03 58 00 00 00 06 00 2A 00 07 00 00 00 00"
)
print(parse_alarm_response(packet))  # Output: [42, 7]
```

## Byte 5 is a length, not an OpSpec

Earlier revisions of this page called `0x09` the "alarm/warning OpSpec" and
listed `0x30`, `0x2B` and `0x14` alongside it as the motor-state, flow and
temperature OpSpecs. **Those are payload lengths** — 9, 48, 43 and 20 bytes.

In a *response*, byte 5 is a length field. Measured across 13 objects and 10
distinct values:

```
0x09 = 0b00001001
       ││└─────┴─ Bits 0-5: payload length (9)
       └┴──────── Bits 6-7: operation code, always 00 in a response
```

and both of these hold without exception:

```
len(frame) == (frame[5] & 0x3F) + 8
frame[1]   == (frame[5] & 0x3F) + 4
```

This is not a naming quibble. Treating `{0x30, 0x2B, 0x14, 0x2E, 0x2D, 0x09}`
as "the register-read operation specifiers" and filtering replies against it
filtered by *length* — which is why the event log, whose entries carry a
20-byte payload, had to be exempted from the filter by hand.

### Matching the reply

A reply is matched by the identifier pair at bytes 6-9, which names the
object's **type**. See
[wire_format.md](../wire_format.md#matching-a-reply-to-a-request).

### What distinguishes this response

Alarm and warning payloads are **uint16 codes**, not IEEE 754 floats.
`0x0000` means none.

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

Early Python implementations incorrectly expected **OpSpec 0x13** for alarm responses. This was based on speculation before testing against actual hardware.

**Testing** confirmed the pump does answer, with a 9-byte payload in the standard response layout.

### Discovery

Testing against real hardware revealed consistent 9-byte replies carrying `0x0000`, which was initially misinterpreted as "not supported." In reality `0x0000` simply means "no active alarms."

## References

- [Protocol: Telemetry](../telemetry.md) - General telemetry overview
- [Protocol: Wire Format](../wire_format.md) - GENI packet structure
- [ESPHome Implementation](https://github.com/eman/esphome-alpha-hwr) - Reference C++ decoder
- [Python Implementation](https://github.com/eman/alpha-hwr) - Reference Python decoder

## Validation

This documentation is based on:

- Real-world testing with an ALPHA HWR pump
- Successful ESPHome C++ implementation (tested on ESP32-C3)
- Cross-validation between Python and ESPHome implementations
- Protocol documentation at https://eman.github.io/alpha-hwr/reimplementation/
