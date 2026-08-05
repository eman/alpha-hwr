# BLE Architecture and Protocol Layers

This document explains how the Grundfos ALPHA HWR communicates over Bluetooth Low Energy (BLE) and how different protocol layers work together.

## BLE Stack Overview

The ALPHA HWR uses a layered communication architecture:

| Layer | Responsibility | Components |
| :--- | :--- | :--- |
| **Application Layer** | Pump logic and user features | Schedule Management, Control, Telemetry |
| **GENI Protocol Layer** | Protocol semantics and object mapping | Class 2/3/7/10, OpSpec, Objects, SubIDs |
| **Framing Layer** | Low-level packet structure and integrity | Start, Length, CRC, Packet splitting |
| **BLE GATT Layer** | Data transport and service definition | Characteristics, Notifications, MTU |
| **BLE Link Layer** | Physical connection and radio management | Connection, Pairing, Security |

---

## Layer 1: BLE Link Layer

### Connection Parameters

**BLE Service:**

- **UUID:** `0000fdd0-0000-1000-8000-00805f9b34fb` (GENI Service)
- **Characteristic:** `859cffd1-036e-432a-aa28-1a0085b87ba9` (Read/Write/Notify)

**Connection Properties:**
...
### Device Discovery

The pump broadcasts BLE advertisements with:

```text
Service Data (Grundfos Company ID: 0000fe5d-0000-1000-8000-00805f9b34fb):
[flags...][product_family][product_type][product_version][...]
  Byte 3: 52 (0x34) = ALPHA family
  Byte 4: 7  (0x07) = HWR type
  Byte 5: 2  (0x02) = Version
```

**Example:**

```text
Service Data: 00 03 00 34 07 02 ...
              ^^ ^^ ^^ ^^ ^^ ^^
              |  |  |  |  |  └─ Product Version
              |  |  |  |  └──── Product Type (HWR)
              |  |  |  └─────── Product Family (ALPHA)
              |  |  └────────── Reserved
              |  └───────────── Reserved
              └──────────────── Flags
```

### Notifications

The characteristic supports **notifications** for:

- Real-time telemetry streaming (Class 10, OpSpec 0x0E)
- Command acknowledgments (ACK/NACK)
- Asynchronous responses

---

## Layer 2: BLE GATT Layer

### Characteristic Operations

**Write Operations:**

- Used for sending commands and requests
- **Write Without Response** (faster, no confirmation)
- Packets >20 bytes must be split across multiple writes

**Notify Operations:**

- Pump sends unsolicited data (telemetry, events)
- Client must enable notifications on characteristic
- High-frequency telemetry stream (~1-2 Hz)

### MTU Limitations

**Problem:** BLE ATT has a 20-byte payload limit  
**Solution:** Multi-chunk packet splitting

```python
# Example: 59-byte schedule write packet
packet = [59 bytes total]

# Split into 3 chunks:
chunk1 = packet[0:20]   # 20 bytes
chunk2 = packet[20:40]  # 20 bytes
chunk3 = packet[40:59]  # 19 bytes

await client.write_gatt_char(CHAR_UUID, chunk1, response=False)
await asyncio.sleep(0.01)  # 10ms delay between chunks
await client.write_gatt_char(CHAR_UUID, chunk2, response=False)
await asyncio.sleep(0.01)
await client.write_gatt_char(CHAR_UUID, chunk3, response=False)
```

**Critical:** The pump reassembles chunks in order. Delays between chunks prevent buffer overflow.

---

## Layer 3: Framing Layer

### GENI Frame Structure

Every packet follows this format:

```text
[Start][Length][Dest][Source][APDU...][CRC_H][CRC_L]
  0x27    N     0xE7   0xF8    ...      ...    ...
  
Start:  0x27 (request) or 0x24 (response)
Length: Dest + Source + APDU length
Dest:   0xE7 (pump/service)
Source: 0xF8 (local master/client)
APDU:   Application Protocol Data Unit
CRC:    CRC-16-CCITT (big-endian)
```

**Example Request:**

```text
2705e7f802c39421a6
││││││││││││││││││
│││││││││││││││└└─ CRC: 0x21A6
││││││││││││└└──── Register: 0x94 (Class 2, ID 148)
│││││││││└└─────── OpSpec: 0xC3 (INFO, 3 bytes)
││││││││└────────── Class: 0x02 (Class 2)
│││││││└─────────── Source: 0xF8 (client)
││││││└──────────── Dest: 0xE7 (pump)
│││││└───────────── Length: 0x05 (5 bytes)
││││└────────────── Start: 0x27 (request)
```

### CRC Calculation

**Two CRC variants:**

- **Read/Response CRC:** Standard CRC-16-CCITT with final XOR
- **Write CRC:** Alternative variant (rarely used)

```python
def calc_crc16_read(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc ^ 0xFFFF  # Final XOR
```

---

## Layer 4: GENI Protocol Layer

### Class System

GENI uses **classes** to categorize operations:

| Class | Name | Purpose | Example |
| :--- | :--- | :--- | :--- |
| 2 | Register | Read single-byte values | Alarm code, control mode |
| 3 | Command | Execute actions | Start, stop, set mode |
| 7 | String | Read text data | Serial number, firmware (NOT supported on HWR) |
| 10 | DataObject | Complex structures | Telemetry, schedules, setpoints |

### Class 10: DataObjects

**Most commonly used for:**

- Telemetry streaming (flow, pressure, power)
- Schedule management (Object 84)
- Setpoint configuration (Object 82, 86)
- Statistics (Object 93)

**Structure:**

```text
[Class=0x0A][OpSpec][SubID_H][SubID_L][ObjID_H][ObjID_L][Data...]

OpSpec encoding: [OpSpec(3 bits)][Length(5 bits)]
SubID: 16-bit identifier (big-endian)
ObjID: 16-bit identifier (big-endian)
```

**OpSpec Types:**

- `0x03`: INFO (read request)
- `0x0E`: Notification (unsolicited data)
- `0x93`: SET (10-byte structure write)
- `0xB3`: SET (42-byte schedule write)

### Object IDs and SubIDs

**Objects:**

| Object | SubID Range | Type | Purpose |
| :--- | :--- | :--- | :--- |
| 84 | 1 | Single | Schedule overview |
| 84 | 1000-1004 | Multiple | **Schedule layers 0-4** |
| 86 | varies | Multiple | Setpoint limits and current setpoint |
| 87 | 69 | Single | Electrical telemetry (Motor State) |
| 93 | 1 | Single | Operation statistics |
| 93 | 290 | Single | Flow/pressure telemetry |
| 93 | 300 | Single | Temperature telemetry |

---

## Layer 5: Application Layer

### Telemetry Update Rate

While basic notifications might arrive at ~1Hz, the high-frequency stream for Motor State and Flow/Pressure typically updates at **~10Hz** when the pump is actively running.

### Schedule Layers (Focus of This Guide)

The ALPHA HWR implements **5 independent schedule layers** within the GENI protocol:

#### Data Object Mapping

```text
Object 84: Clock Program
├─ SubID 1:    Overview (enabled/disabled)
├─ SubID 1000: Layer 0 schedule (42 bytes)
├─ SubID 1001: Layer 1 schedule (42 bytes)
├─ SubID 1002: Layer 2 schedule (42 bytes)
├─ SubID 1003: Layer 3 schedule (42 bytes)
└─ SubID 1004: Layer 4 schedule (42 bytes)
```

Each layer (SubID) contains a complete 7-day schedule (42 bytes):

```text
[Mon(6)][Tue(6)][Wed(6)][Thu(6)][Fri(6)][Sat(6)][Sun(6)]

Per-day (6 bytes):
[Enabled][Action][Start_H][Start_M][End_H][End_M]
```

#### Why 5 Layers

**Architectural Benefits:**

1. **Storage Efficiency:** Each layer is 42 bytes, total 210 bytes
2. **Independent Management:** Modify one layer without affecting others
3. **Overlay Support:** Multiple layers active simultaneously
4. **Hierarchical Scheduling:** Base + override pattern

**Practical Use Cases:**

```text
Layer 0: Base schedule (weekday mornings)
Layer 1: Additional slots (weekday evenings)
Layer 2: Weekend schedule (different pattern)
Layer 3: Seasonal adjustments (winter/summer)
Layer 4: Temporary overrides (holidays, events)
```

#### Layer Read/Write Protocol

**Read Layer 0:**

```
Request:  [0x27][0x0B][0xE7][0xF8][0x0A][0x03][0x54][0x03][0xE8][CRC]
                                    ││    ││    ││    ││    └└─ SubID: 1000 (Layer 0)
                                    ││    ││    └└────────────── ObjID: 84
                                    ││    └└───────────────────── OpSpec: 0x03 (INFO)
                                    └└─────────────────────────── Class: 10

Response: [0x24][0x31][0xF8][0xE7][0x0A][0x03][0x54][0x03][0xE8][Header(3)][Data(42)][CRC]
                                                                 └──────────┴─────────┘
                                                                    45 bytes total
```

**Write Layer 0:**

```
Request:  [0x27][0x37][0xE7][0xF8][0x0A][0xB3][0x54][0x03][0xE8][0x00][Type(3)][Size(2)][Data(42)][CRC]
                                    ││    ││    ││    ││    └└── ││      └└──────┴────┴─────────┘
                                    ││    ││    ││    ││    │    ││        Type 222 header + data
                                    ││    ││    ││    ││    │    └└────────── Reserved
                                    ││    ││    ││    └└────┴────────────────── SubID: 1000
                                    ││    ││    └└───────────────────────────── ObjID: 84
                                    ││    └└──────────────────────────────────── OpSpec: 0xB3 (SET)
                                    └└─────────────────────────────────────────── Class: 10

Total: 59 bytes  Split into 3 BLE writes (20+20+19)
```

---

## Layer Interaction Example

### Practical Scenario: Weekday + Weekend Scheduling

**User Goal:**

- Weekdays: Pump on 6:30-8:30 (morning) and 18:00-22:00 (evening)
- Weekends: Pump on 8:00-23:00 (all day)

**Implementation Using Layers:**

```python
# Layer 0: Weekday mornings
weekday_morning = [
    ScheduleEntry(
        day="Monday", begin_hour=6, begin_minute=30, end_hour=8, end_minute=30
    ),
    ScheduleEntry(
        day="Tuesday", begin_hour=6, begin_minute=30, end_hour=8, end_minute=30
    ),
    ScheduleEntry(
        day="Wednesday",
        begin_hour=6,
        begin_minute=30,
        end_hour=8,
        end_minute=30,
    ),
    ScheduleEntry(
        day="Thursday", begin_hour=6, begin_minute=30, end_hour=8, end_minute=30
    ),
    ScheduleEntry(
        day="Friday", begin_hour=6, begin_minute=30, end_hour=8, end_minute=30
    ),
]
await client.schedule.write_entries(weekday_morning, layer=0)

# Layer 1: Weekday evenings
weekday_evening = [
    ScheduleEntry(
        day="Monday", begin_hour=18, begin_minute=0, end_hour=22, end_minute=0
    ),
    # ... Tuesday-Friday same pattern
]
await client.schedule.write_entries(weekday_evening, layer=1)

# Layer 2: Weekend all-day
weekend = [
    ScheduleEntry(
        day="Saturday", begin_hour=8, begin_minute=0, end_hour=23, end_minute=0
    ),
    ScheduleEntry(
        day="Sunday", begin_hour=8, begin_minute=0, end_hour=23, end_minute=0
    ),
]
await client.schedule.write_entries(weekend, layer=2)
```

**Protocol Operations:**

1. **3 BLE packets** (each 59 bytes  split into 3 chunks)
2. **3 separate Class 10 SET operations** (OpSpec 0xB3)
3. **3 different SubIDs** (1000, 1001, 1002)
4. **Independent storage** in pump memory

**Result on Pump:**

```
Layer 0 (SubID 1000): Mon-Fri 6:30-8:30, Sat-Sun empty
Layer 1 (SubID 1001): Mon-Fri 18:00-22:00, Sat-Sun empty
Layer 2 (SubID 1002): Mon-Fri empty, Sat-Sun 8:00-23:00
```

**Pump Behavior:**

```
Monday:    ▓▓▓▓▓▓▓▓░░░░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓░░░░░  (Layer 0 + Layer 1)
Saturday:  ░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  (Layer 2)
```

---

## Performance Considerations

### Packet Timing

**Critical Delays:**

- **10ms between BLE chunks:** Prevents buffer overflow
- **200-500ms after keep-alive:** Wakes GENI controller
- **300-500ms after write:** Allows pump to persist data

### Transaction Management

The library uses a **transaction lock** to prevent concurrent operations:

```python
async with self._transaction_lock:
    # Send request
    await self.client.write_gatt_char(...)
    
    # Wait for response
    response = await asyncio.wait_for(self._response_queue.get(), timeout)
```

**Why** BLE characteristics don't support request/response matching. The lock ensures one operation completes before another starts.

### Keep-Alive Burst

Large data reads (schedules, statistics) require a **keep-alive burst**:

```python
# Send 3 keep-alive packets
for _ in range(3):
    await self.send_keep_alive()
    await asyncio.sleep(0.1)

# Wait for GENI controller to wake
await asyncio.sleep(0.3)

# Now send read request
response = await self._read_class10_subid(84, 1000)
```

**Purpose:** Some GENI controllers sleep between operations. The burst wakes them up for complex reads.

---

## Debugging Protocol Issues

### Common Problems

### 1. Schedule Write Fails Silently

- **Symptom:** `set_schedule_entry()` returns True but data unchanged
- **Cause:** Packet splitting broken (only 2 chunks sent instead of 3)
- **Fix:** Use multi-chunk splitting in `_query()` method

### 2. Schedule Read Timeout

- **Symptom:** `get_schedule()` times out or returns None
- **Cause:** GENI controller asleep
- **Fix:** Add keep-alive burst before read

### 3. CRC Errors

- **Symptom:** Pump sends NACK (OpSpec 0x02)
- **Cause:** Wrong CRC calculation or corrupted packet
- **Fix:** Verify CRC algorithm, check packet integrity

### Packet Logging

Enable debug logging to see protocol traffic:

```python
import logging

logging.basicConfig(level=logging.DEBUG)

# Output includes:
# Querying: 2737e7f80ab35403e800de0100002a01020...
# Split-wrote 59 bytes (20 + 20 + 19)
```

---

## Summary

The ALPHA HWR BLE architecture uses:

1. **BLE GATT** for transport (MTU 20 bytes)
2. **GENI framing** for packet structure (Start, Length, CRC)
3. **GENI protocol** for operations (Class 10 DataObjects)
4. **Schedule layers** for application logic (5 independent SubIDs)

**Summary:**

- Schedule layers are **SubIDs within Object 84**, not separate BLE characteristics
- Multi-chunk splitting is **critical** for packets >20 bytes
- Layers allow **complex scheduling** without protocol complexity
- All operations are **synchronous request/response** over a single BLE characteristic

For more details:

- **Schedule Protocol:** See `docs/protocol/schedules.md`
- **Wire Format:** See `docs/protocol/wire_format.md`
- **Control Operations:** See `docs/protocol/control.md`
