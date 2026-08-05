# Common Pitfalls and Solutions

This document covers common mistakes when implementing the ALPHA HWR protocol and how to avoid them.

## 1. Endianness Issues

### Problem: Little-Endian Instead of Big-Endian

**Symptom:** Float values decode incorrectly (very large/small numbers).

**Wrong:**
```python
# Little-endian (incorrect)
value = struct.unpack("<f", data)[0]  # Note the '<'
```

**Correct:**
```python
# Big-endian (network byte order)
value = struct.unpack(">f", data)[0]  # Note the '>'
```

**Why:** GENI protocol uses network byte order (big-endian) for all multi-byte values.

**Quick Test:**
```python
# 1.5 should encode as: 0x3F 0xC0 0x00 0x00
assert encode_float(1.5) == bytes([0x3F, 0xC0, 0x00, 0x00])
```

---

## 2. CRC Calculation

### Problem: Wrong CRC Polynomial, Range or Final XOR

**Symptom:** Every packet rejected. Nothing works at all.

**The algorithm is CRC-16/CCITT-FALSE:**

| | |
| :--- | :--- |
| Polynomial | `0x1021` |
| Initial value | `0xFFFF` |
| Reflect in / out | No / No |
| Final XOR | `0xFFFF` |
| Covered bytes | `frame[1:-2]` — everything **after** the start byte, up to but not including the CRC |

> **Earlier revisions of this guide specified CRC-16/MODBUS (`0x8005`,
> reflected, no final XOR) and listed "using CRC-16/CCITT" as the number-one
> mistake. That was exactly backwards.** A port built from those instructions
> cannot exchange a single valid frame with the pump. If you have such a port,
> this is the first thing to fix.

**Test — these are captured frames the pump accepted, so they are evidence,
not self-consistency:**

```python
def check(frame_hex, expected):
    frame = bytes.fromhex(frame_hex)
    assert calc_crc16(frame[1:-2]) == expected
    assert frame[-2:] == expected.to_bytes(2, "big")   # CRC is big-endian

check("2705e7f805c14bc382", 0xC382)          # Extend 1
check("2705e7f80bc10fd0c3", 0xD0C3)          # Extend 2
check("2707e7f80203949596eb47", 0xEB47)      # Legacy magic
check("2707e7f80a03560006c55a", 0xC55A)      # Class 10 unlock
check("2705e7f8038106e587", 0xE587)          # Class 3 START
```

**Reference implementation:**

```python
def calc_crc16(data: bytes, init: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE, computed over frame[1:-2]."""
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc ^ 0xFFFF
```

A table-driven form is in `alpha_hwr/utils.py`; it produces the same values.

### One convention, not two

The Python implementation carries a second helper that omits the final XOR,
described as "the write convention". **No frame the pump accepts uses it** —
the five vectors above include both reads and writes, and all five need the
XOR. The no-XOR helper is reachable from one code path that never talks to a
pump. Do not reproduce it.

---

## 3. Authentication Sequence

### Problem: Commands Don't Work After Connection

**Symptom:** Connection succeeds but all commands timeout or get rejected.

**Cause:** Skipped or incorrect authentication sequence.

**Correct Sequence:**
1. Connect to BLE device
2. Send **exactly 3** Legacy Magic packets: `27 07 E7 F8 02 03 94 95 96 EB 47`
3. Send **exactly 5** Class 10 Unlock packets: `27 07 E7 F8 0A 03 56 00 06 C5 5A`
4. Send **exactly 1** Extend 1 packet: `27 05 E7 F8 0B C1 0F D0 C3`
5. Send **exactly 1** Extend 2 packet: `27 05 E7 F8 05 C1 4B C3 82`

**Common Mistakes:**
- Wrong number of repetitions
- Wrong order
- Not waiting for BLE write confirmation
- Typos in packet bytes

**Validation:**
```python
# After authentication, this should work:
response = send_command(info_command())
assert response is not None  # Should get telemetry
```

---

## 4. BLE Notifications

### Problem: Never Receive Responses

**Symptom:** Send commands successfully but timeout waiting for response.

**Cause:** Forgot to subscribe to notifications — or went looking for a
separate RX characteristic that does not exist.

**There is one characteristic**, `859cffd1-036e-432a-aa28-1a0085b87ba9`, on
service `0000fdd0-0000-1000-8000-00805f9b34fb`. You write to it and you
subscribe to it.

**Wrong:**
```python
# No notification subscription!
await client.write_gatt_char(GENI_CHAR_UUID, packet, response=False)
response = await asyncio.wait_for(get_response(), timeout=5.0)
# Timeout!
```

**Correct:**
```python
# Subscribe first, on the same handle you are about to write to
def notification_handler(sender, data):
    process_response(data)


await client.start_notify(GENI_CHAR_UUID, notification_handler)

await client.write_gatt_char(GENI_CHAR_UUID, packet, response=False)
```

**Checklist:**
- [x] One characteristic: `859cffd1-036e-432a-aa28-1a0085b87ba9`
- [x] Enable notifications before sending commands
- [x] Bond with the device — otherwise the connection is dropped at ~1.8 s
      whether or not you are sending anything

---

## 4a. BLE Packet Fragmentation (Receiving)

### Problem: Incomplete or Corrupted Packets

**Symptom:** Packets fail CRC checks, telemetry values are garbage, or responses seem truncated.

**Cause:** BLE has a 20-byte MTU limit. Larger packets are fragmented across multiple notifications.

**Wrong:**
```python
def notification_handler(sender, data):
    # Process each notification as complete packet
    frame = parse_frame(data)  # Might be fragment!
    process_telemetry(frame)
```

**Correct:**
```python
class Transport:
    def __init__(self):
        self._response_buffer = bytearray()

    def notification_handler(self, sender, data):
        # Check if this starts a new packet
        if len(data) > 0 and data[0] in (0x24, 0x27):
            # Frame start byte - begin new packet
            self._response_buffer = bytearray(data)
        else:
            # Continuation - append to buffer
            self._response_buffer.extend(data)

        # Check if packet is complete
        if len(self._response_buffer) >= 2:
            expected_len = (
                self._response_buffer[1] + 4
            )  # len + start + len + CRC
            if len(self._response_buffer) >= expected_len:
                # Complete packet!
                full_packet = bytes(self._response_buffer)
                process_packet(full_packet)
                self._response_buffer.clear()
```

**Notes:**
- Frame start: `0x24` (response) or `0x27` (request)
- Expected length: `packet[1] + 4` (length field + start byte + length byte + 2-byte CRC)
- Buffer fragments until complete
- Clear buffer after processing complete packet

**Example Fragmentation:**
```
Complete packet (30 bytes):
  24 1C F8 E7 0A 30 00 01 00 03 00 00 42 EE E5 AA 43 27 D6 00 3E 1B F8 00 41 5A 29 C0 41 58

Arrives as:
  Notification 1 (20 bytes): 24 1C F8 E7 0A 30 00 01 00 03 00 00 42 EE E5 AA 43 27 D6 00
  Notification 2 (10 bytes): 3E 1B F8 00 41 5A 29 C0 41 58
```

**Validation:**
```python
# After reassembly, verify packet
assert full_packet[0] in (0x24, 0x27)  # Valid start
assert len(full_packet) == full_packet[1] + 4  # Length matches
assert verify_crc(full_packet)  # CRC valid
```

---

## 4aa. BLE Packet Splitting (Sending)

### Problem: Write Commands Don't Work (Pump Ignores Them)

**Symptom:** Commands like schedule enable/disable appear to succeed but pump state doesn't change. Read operations work fine but write operations fail silently.

**Cause:** **CRITICAL:** Packets >20 bytes **MUST** be split into multiple writes. The pump will **silently ignore** unsplit long packets.

**Wrong:**
```python
# WRONG: Writing 27-byte packet in one write
packet = build_schedule_command()  # 27 bytes
await client.write_gatt_char(GENI_CHAR_UUID, packet, response=False)
# Pump ignores this! No error, just fails silently.
```

**Also wrong — and much harder to spot:**
```python
# WRONG: two chunks, "first 20 and the rest"
await self.client.write_gatt_char(GENI_CHAR_UUID, data[:20], response=False)
await asyncio.sleep(0.01)
await self.client.write_gatt_char(GENI_CHAR_UUID, data[20:], response=False)
```

This is correct for every frame up to 40 bytes, which is every control packet
and every commit — so it passes all the obvious tests. It silently truncates
the **59-byte schedule-layer write**, whose second "chunk" is 39 bytes. That
shipped in this library, and the schedule write was the only casualty.

**Correct — N chunks:**
```python
BLE_MTU_LIMIT = 20
SEND_PACING = 0.05


async def write(self, data: bytes, response: bool = False) -> None:
    """Write data in as many MTU-sized chunks as it needs."""
    for offset in range(0, len(data), BLE_MTU_LIMIT):
        await self.client.write_gatt_char(
            GENI_CHAR_UUID,
            data[offset : offset + BLE_MTU_LIMIT],
            response=response,
        )
        await asyncio.sleep(SEND_PACING)
```

**Why This Happens:**
1. BLE ATT has a 20-byte payload limit (MTU - 3 header bytes = 20)
2. Some BLE stacks (like Bleak) don't automatically split writes
3. The pump **requires** manual splitting - it won't reassemble unsplit long packets
4. Failure is **silent** - no error response, just ignored

**Real Example:**

The configuration commit is 27 bytes:
```
Command: 2717e7f80a9354000100da0100000a02050005010100000000b44e
         ├──────────── 20 bytes ──────────┤├───── 7 bytes ─────┤
```

Must be written as:
```python
# Chunk 1 (20 bytes)
await write(bytes.fromhex("2717e7f80a9354000100da0100000a0205000500"))
await asyncio.sleep(0.05)

# Chunk 2 (7 bytes)
await write(bytes.fromhex("0100000000b44e"))
```

A schedule-layer write is 59 bytes and takes **three** chunks — 20 + 20 + 19.
Do not hardcode a chunk count.

> The commit payload above is a real capture, shown to illustrate chunking.
> Do not copy it as a constant: byte 4 of its 10-byte overview is the
> schedule's enabled flag, and a fixed value there overwrites whatever the
> user has configured.

**Detection:**
```python
# If reads work but writes fail silently, check packet length
if len(packet) > 20:
    print(f"WARNING: Packet is {len(packet)} bytes, needs splitting!")
```

**Commands Affected:**
- [x] Authentication (11 bytes) - No split needed
- [x] Telemetry read (11 bytes) - No split needed  
- [ ] Schedule enable/disable (27 bytes) - **MUST SPLIT**
- [ ] Schedule write (59 bytes) - **MUST SPLIT**
- [ ] Some setpoint writes (>20 bytes) - **MUST SPLIT**

**Testing:**
```python
# Test that splitting works
packet = bytes(range(27))  # 27-byte test packet

# This will fail (pump ignores it)
await client.write_gatt_char(uuid, packet, response=False)

# This will work
await client.write_gatt_char(uuid, packet[:20], response=False)
await asyncio.sleep(0.01)
await client.write_gatt_char(uuid, packet[20:], response=False)
```

**Performance Note:**
The 10ms delay between chunks is **critical** - it prevents buffer overflow on the pump's BLE controller. Shorter delays may cause corruption; longer delays are unnecessary.

---

## 4b. Error-Then-Data Response Pattern

### Problem: Get "Not Authorized" Errors But Telemetry Never Arrives

**Symptom:** After querying telemetry, receive Class 2 error response with "not authorized" code, but pump is authenticated.

**Cause:** Pump sends Class 2 error FIRST, then sends the actual telemetry data in a second packet. Naive implementations return the error and don't wait for the data.

**Wrong:**
```python
# Send telemetry query
await client.write_gatt_char(GENI_CHAR_UUID, telemetry_request, response=False)

# Wait for response
response = await wait_for_response(timeout=2.0)
if response[4] == 0x02:  # Class 2 = error
    raise Exception("Not authorized")  # Give up too early!
```

**Correct:**
```python
# Send telemetry query
await client.write_gatt_char(GENI_CHAR_UUID, telemetry_request, response=False)


# Filter function to skip errors and passive notifications
def is_telemetry_data(packet):
    if len(packet) < 6:
        return False
    # Reject Class 2 errors (data comes after)
    if packet[4] == 0x02:
        return False
    # Reject Class 10 passive notifications (OpSpec 0x0E)
    if packet[4] == 0x0A and packet[5] == 0x0E:
        return False
    # Accept Class 10 data responses
    return packet[4] == 0x0A


# Wait for ACTUAL data, skipping error responses
response = await wait_for_matching_response(
    timeout=2.0, match_func=is_telemetry_data
)
```

**What Happens:**
```
1. Client sends: 27 07 E7 F8 0A 03 57 00 45 [CRC]  (query motor state)
2. Pump sends:   24 07 F8 E7 02 03 34 07 02 [CRC]  (Class 2 error - IGNORE THIS)
3. Pump sends:   24 34 F8 E7 0A 30 ... [data]      (Class 10 data - USE THIS!)
```

**Why This Happens:**
- The error is the pump's immediate response to the query command
- The actual telemetry data is sent as a follow-up notification
- You must wait for and filter for the telemetry data packet

**Implementation Tip:**
Keep reading responses in a loop until you get a Class 10 packet or timeout expires.

---

## 4c. Register-Read Response Format

### Problem: Telemetry Decoder Returns Empty Results

**Symptom:** Receive telemetry responses but decoder extracts no values (all None/null).

**Cause:** Register-read queries (OpSpec 0x03) return responses with DIFFERENT format than passive notifications.

**Two Response Formats:**

**Format 1: Passive Notifications (OpSpec 0x0E)**
```
24 22 F8 E7 0A 0E [Sub-H] [Sub-L] [Obj-H] [Obj-L] [Payload...] [CRC]
                  ^  ^    ~~~~~~~~~~~~~~~~~~~~~ ~~~~~~~~~~~~~~~
                  |  |    Standard Sub/Obj     Structured payload
                Class OpSpec
```
Sub/Obj at bytes 6-9, payload follows standard structure.

**Format 2: Direct read responses** (byte 5 is the payload *length* — 48, 43, 20…)
```
24 34 F8 E7 0A 30 [Counters...] [Res] [Float1] [Float2] ... [CRC]
                  ^  ^           ~~~~~ ~~~~~~~~~~~~~~~~~~~~~~~~~~
                  |  |           Skip  Packed floats starting at offset 13
                Class OpSpec
```
No Sub/Obj headers! Data starts at offset 13 as packed IEEE 754 floats.

**OpSpec Mapping:**
- `0x30` = Motor state response (voltage, current, power, RPM)
- `0x2b` = Flow/pressure response (flow, head, inlet, outlet)
- `0x14` = Temperature response (media, PCB, box)

**Motor state response decoding** (byte 5 = `0x30` = 48-byte payload):
```python
def decode_register_read_motor(packet):
    # Skip to offset 13 where float data starts
    offset = 13
    floats = []

    # Extract floats (big-endian IEEE 754)
    while offset + 4 <= len(packet) - 2:  # Leave room for CRC
        val = struct.unpack(">f", packet[offset : offset + 4])[0]
        # Check for NaN marker (0x7FFFFFFF)
        if math.isnan(val) or abs(val) > 1e15:
            floats.append(None)
        else:
            floats.append(val)
        offset += 4

    # Map floats to telemetry fields
    return {
        "voltage_ac_v": floats[0] if len(floats) > 0 else None,  # Offset 13-16
        "voltage_dc_v": floats[1] if len(floats) > 1 else None,  # Offset 17-20
        "current_a": floats[2] if len(floats) > 2 else None,  # Offset 21-24
        "power_w": floats[3] if len(floats) > 3 else None,  # Offset 25-28
        "speed_rpm": floats[5] if len(floats) > 5 else None,  # Offset 33-36
    }
```

**Flow/Pressure Response (OpSpec 0x2b) Decoding:**
```python
def decode_register_read_flow(packet):
    floats = extract_floats_from_offset_13(packet)

    return {
        "flow_m3h": floats[0] if len(floats) > 0 else None,
        "head_m": floats[1] if len(floats) > 1 else None,
        "inlet_pressure_bar": floats[2] if len(floats) > 2 else None,
        "outlet_pressure_bar": floats[3] if len(floats) > 3 else None,
    }
```

**Detection Logic:**
```python
def decode_telemetry(packet):
    opspec = packet[5] if len(packet) > 5 else 0

    if opspec == 0x0E:
        # Passive notification - use standard decoder
        return decode_standard_notification(packet)
    elif opspec in (0x30, 0x2B, 0x14):
        # Register-read response - use packed float decoder
        return decode_register_read_response(packet)
    else:
        # Unknown format
        return {}
```

**Real Example:**
```
Query sent:
  27 07 E7 F8 0A 03 57 00 45 [CRC]  (Read motor state register 0x570045)

Response received (byte 5 = 0x30, a 48-byte payload):
  24 34 F8 E7 0A 30 00 01 00 03 00 00 42 EE E5 AA 43 27 D6 00 3E 1B F8 00 41 5A 29 C0 41 58 CD E0 45 65 3A D0 [CRC]

Decoded floats from offset 13:
  [0] 0x42EEE5AA = 119.45 V  (AC voltage)
  [1] 0x4327D600 = 167.84 V  (DC voltage)
  [2] 0x3E1BF800 = 0.152 A   (current)
  [3] 0x415A29C0 = 13.64 W   (power)
  [4] 0x4158CDE0 = 13.55     (unknown)
  [5] 0x45653AD0 = 3667.7 RPM (speed)
```

**Differences:**
| Aspect | Passive Notification (0x0E) | Register-Read Response (0x30/0x2b) |
|--------|---------------------------|----------------------------------|
| **OpSpec** | 0x0E | 0x30, 0x2b, 0x14, etc |
| **Sub/Obj** | Present at bytes 6-9 | Not present |
| **Data Start** | After Sub/Obj (byte 10) | Fixed offset 13 |
| **Data Format** | Structured with gaps | Packed sequential floats |
| **When** | Unsolicited stream | Response to query |

**Validation:**
```python
# Test with known packet
motor_response = bytes.fromhex(
    "2434f8e70a300001000300002942eee5aa4327d6003e1bf800415a29c04158cde045653ad0..."
)

data = decode_register_read_motor(motor_response)
assert 118 <= data["voltage_ac_v"] <= 120  # ~119V
assert 13 <= data["power_w"] <= 14  # ~13.6W
assert 3600 <= data["speed_rpm"] <= 3700  # ~3667 RPM
```

---

## 5. Frame Length Calculation

### Problem: Incorrect Length Field

**Symptom:** Pump doesn't respond or rejects packets.

**Cause:** Length field doesn't match actual packet size.

**Wrong:**
```python
# Length = payload only (wrong!)
length = len(payload)
```

**Correct:**
```python
# Length = start byte + length field + service ID + source + APDU + CRC
length = 1 + 1 + 1 + 1 + len(apdu) + 2
# OR simply: count all bytes including start and length itself
```

**Example:**
```
Packet: 27 07 E7 F8 02 03 94 95 96 EB 47
Length: 07 (means 7 bytes total, including start and length)
Bytes:  [27][07] E7 F8 02 03 94 95 96 EB 47
         ^   ^  ^  ^  ^  ^  ^  ^  ^  ^  ^
         1   2  3  4  5  6  7 (CRC doesn't count)
```

**Rule:** Length field = position of last APDU byte + 1

---

## 6. Payload Offsets

### Problem: Telemetry Values Are Wrong

**Symptom:** Speed shows as temperature, pressure shows as flow, etc.

**Cause:** Incorrect byte offsets when parsing telemetry.

**Example - Motor State (Sub 0x45, Obj 0x57):**

**Wrong:**
```python
grid_voltage = decode_float(payload[0:4])  # Correct
current = decode_float(payload[4:8])  # Wrong! Skip 4 bytes
power = decode_float(payload[8:12])  # Wrong!
```

**Correct:**
```python
grid_voltage = decode_float(payload[0:4])  # Offset 0-3
current = decode_float(payload[8:12])  # Offset 8-11 (skip 4 bytes!)
power = decode_float(payload[16:20])  # Offset 16-19 (skip gaps)
speed = decode_float(payload[20:24])  # Offset 20-23
temp = decode_float(payload[24:28])  # Offset 24-27
```

**Why:** Telemetry payloads have gaps (reserved bytes). Always check documentation.

**Reference:** See `telemetry_decoder.py` for correct offsets.

---

## 7. Unit Conversions

### Problem: Pressure Values Way Off

**Symptom:** Setting 1.5m results in pump showing 15000m.

**Cause:** Incorrect pressure unit conversion.

**Wrong:**
```python
# Wrong! Factor is off by 10000x
pascals = meters * 1000
```

**Correct:**
```python
# 1 meter water column = 9806.65 Pascals
pascals = meters * 9806.65
```

**Common Conversions:**
- **Meters to Pascals:** multiply by `9806.65`
- **Bar to Pascals:** multiply by `100000`
- **Flow m³/h:** no conversion (already correct unit)

**Quick Check:**
```python
assert meters_to_pascals(1.5) ≈ 14710.0
assert pascals_to_meters(14710.0) ≈ 1.5
```

---

## 8. Async/Concurrency Issues

### Problem: Commands Interfere With Each Other

**Symptom:** Random timeouts or corrupted responses.

**Cause:** Sending multiple commands concurrently without locking.

**Wrong:**
```python
# Two commands sent at same time
asyncio.gather(read_telemetry(), set_mode(...))
# Responses get mixed up!
```

**Correct:**
```python
# Use a lock for sequential execution
async with self.transport_lock:
    await self.send_command(packet)
    response = await self.wait_response()
```

**Rule:** Only one command in-flight at a time. Wait for response before sending next command.

---

## 9. Response Frame Detection

### Problem: Can't Distinguish Request from Response

**Symptom:** Try to parse responses but get confused with echoed requests.

**Cause:** Not checking start byte.

**Wrong:**
```python
# Assumes all frames are responses
frame = parse_frame(data)
process_response(frame)  # Might be request echo!
```

**Correct:**
```python
def parse_frame(data):
    start_byte = data[0]
    if start_byte == 0x27:
        return RequestFrame(...)
    elif start_byte == 0x24:
        return ResponseFrame(...)
    else:
        raise InvalidFrame()
```

**Legend:**
- `0x27` = Request (from client to pump)
- `0x24` = Response (from pump to client)

---

## 10. Timeout Values

### Problem: Premature Timeouts or Hanging

**Symptom:** Operations timeout even though pump is working.

**Cause:** Incorrect timeout values.

**Too Short:**
```python
response = await asyncio.wait_for(get_response(), timeout=0.1)
# Timeouts before pump can respond!
```

**Too Long:**
```python
response = await asyncio.wait_for(get_response(), timeout=300)
# Hangs for 5 minutes on error!
```

**Recommended:**
```python
# General commands
timeout = 5.0  # 5 seconds

# Authentication
timeout = 10.0  # 10 seconds (needs more time)

# Telemetry polling
timeout = 2.0  # 2 seconds (faster feedback)
```

---

## 11. Float Special Values

### Problem: Crashes on NaN or Infinity

**Symptom:** Pump returns unexpected float values that crash decoder.

**Cause:** Not handling IEEE 754 special values.

**Examples:**
- `0x7F800000` = Positive Infinity
- `0xFF800000` = Negative Infinity
- `0x7FC00000` = NaN (Not a Number)

**Correct:**
```python
import math

value = decode_float_be(data)
if math.isnan(value) or math.isinf(value):
    # Treat as invalid/unavailable
    value = None
```

**When This Happens:**
- Sensor disconnected
- Sensor not yet initialized
- Invalid measurement

---

## 12. Source Address

### Problem: Responses Don't Match Requests

**Symptom:** Send command with source `0xF8`, expect response from `0x20`, but get confused.

**Correct Understanding:**
- **Client (you):** Always use source `0xF8` in requests
- **Pump:** Always uses source `0x20` in responses
- **Match by:** Class, Sub ID, Obj ID (not source address)

**Frame Matching:**
```python
# Request
request = build_info_command(class=0x0A, sub=0x45, obj=0x57)
# Source will be 0xF8

# Response
response = parse_response(data)
# Source will be 0x20

# Match by content, not source
assert response.class_byte == 0x0A
assert response.sub_id == 0x45
assert response.obj_id == 0x57
```

---

## 13. Schedule Time Format

### Problem: Schedule Times Don't Work

**Symptom:** Schedule added but pump doesn't follow it.

**Cause:** Incorrect time encoding.

**Wrong:**
```python
# Sending time as string
schedule_data = "06:30"
```

**Also wrong:** minutes-since-midnight as a uint16. Earlier revisions of this
page taught that, and the pump accepts the bytes without complaint.

**Correct — plain hour and minute bytes.** A weekly schedule day is six
bytes:

```python
day = bytes([
    0x01,   # enabled
    0x01,   # action: 0x01 = run, 0x00 = stop
    6,      # start hour
    30,     # start minute
    8,      # end hour
    30,     # end minute
])
```

**Examples:**

| Time | Bytes |
| :--- | :--- |
| `00:00` | `00 00` |
| `06:30` | `06 1E` |
| `18:45` | `12 2D` |
| `23:59` | `17 3B` |

Seven of these, Monday first, make the 42-byte layer — and the layer is
always written whole. There is no partial update: to change one day, read
the layer, edit its six bytes, and write all 42 back.

> **Single-event** timestamps are a different encoding entirely: 32-bit
> **local Unix time**, the wall clock stamped as though it were UTC. Getting
> that one wrong round-trips byte-identically, so no amount of verification
> catches it. See
> [schedules.md](../protocol/schedules.md#timestamps-are-local-unix-time).

---

## 14. Connection Stability

### Problem: Random Disconnections

**Symptom:** Connection drops during long operations.

**Cause:** BLE connection not kept alive.

**Solution:**
```python
# Keep-alive mechanism
async def keep_alive_loop():
    while connected:
        # Send periodic command (e.g., read status)
        await read_pump_state()
        await asyncio.sleep(30)  # Every 30 seconds
```

**Best Practices:**
- Send command at least every 60 seconds
- Handle disconnection gracefully
- Implement reconnection logic
- Monitor connection state

---

## 15. Testing Without Hardware

### Problem: Can't Test Without Real Pump

**Solution:** Create mock pump for testing.

**Example Mock:**
```python
class MockPump:
    def __init__(self):
        self.authenticated = False
        self.mode = "stopped"
        
    async def handle_command(self, packet):
        if is_auth_packet(packet):
            self.authenticated = True
            return build_ack()
        
        if not self.authenticated:
            return None  # Reject
            
        # Handle other commands
        if is_telemetry_request(packet):
            return build_telemetry_response()
```

**Benefits:**
- Test protocol implementation
- Validate packet building
- Test error handling
- No hardware needed

---

## Quick Debug Checklist

When something doesn't work:

1. [x] **Endianness:** All multi-byte values big-endian?
2. [x] **CRC:** CCITT `0x1021`, init `0xFFFF`, final XOR `0xFFFF`, over `frame[1:-2]`?
3. [x] **Authentication:** Sent all packets in correct order?
4. [x] **Notifications:** Subscribed to the characteristic's notifications?
5. [x] **Packet Fragmentation:** Reassembling fragments before parsing?
6. [x] **Error Responses:** Filtering out Class 2 errors before data?
7. [x] **Response Format:** Reading byte 5 of a response as a *length*, not a format code?
8. [x] **Length:** Frame length field correct?
9. [x] **Offsets:** Using correct byte offsets for telemetry?
10. [x] **Units:** Pressure in Pascals, not meters?
11. [x] **Locking:** Only one command at a time?
12. [x] **Start Byte:** Checking 0x27 vs 0x24?
13. [x] **Timeouts:** Using reasonable timeout values?

---

## Getting Help

If you're still stuck:

1. **Compare with reference:** Check Python implementation
2. **Use test vectors:** Validate each component
3. **Enable logging:** Log all packets sent/received
4. **Hex dump packets:** Verify byte-by-byte
5. **Check documentation:** Review protocol docs
6. **File issue:** Report bugs or unclear documentation

## Debugging Tips

### Enable Packet Logging

```python
def log_packet(direction, packet):
    hex_str = packet.hex(" ")
    print(f"{direction}: {hex_str}")


# Log all packets
await client.write_gatt_char(GENI_CHAR_UUID, packet, response=False)
log_packet("TX", packet)


# In notification handler
def on_notification(sender, data):
    log_packet("RX", data)
```

### Validate Each Layer

```python
# Test codec
assert encode_float_be(1.5) == bytes([0x3F, 0xC0, 0x00, 0x00])

# Test frame building
packet = build_info_command(...)
assert packet[0] == 0x27  # Start byte
assert calculate_crc(packet[:-2]) == get_crc_from_packet(packet)

# Test authentication
await authenticate()
assert session.is_authenticated()
```

### Use BLE Debugging Tools

- **nRF Connect** - Monitor BLE traffic

---

## Summary

Most issues stem from:
1. **Endianness** (big-endian!)
2. **CRC algorithm** (CCITT/0x1021 with a final XOR — *not* MODBUS)
3. **Authentication sequence** (exact order and count!)
4. **Notifications** (must subscribe on the single characteristic!)
5. **Packet fragmentation** (reassemble before parsing!)
6. **Error-then-data pattern** (ignore Class 2 errors, wait for data!)
7. **Response format** (byte 5 is a length, not a type code — match on the identifier pair)
8. **Unit conversions** (9806.65 for meters to Pascals!)

Always validate with test vectors before testing with hardware!
