# Packet Trace: Schedule Write

This document details the complex operation of writing a schedule to the pump.

## Overview

Writing a schedule involves:
1.  **Large Payload**: A full schedule layer is 42 bytes.
2.  **Packet Splitting**: BLE limits mean we must split the 59-byte command into 3 writes.
3.  **Class 10 SET**: Using OpSpec `0xB3` (SET with long payload).

## 1. Schedule Data Structure

A schedule layer consists of 7 days (Monday-Sunday), 6 bytes per day.

**Total Size:** 7 * 6 = 42 bytes.

**Day Format (6 bytes):**
```
[Enabled] [Action] [Start-H] [Start-M] [End-H] [End-M]
```
- **Enabled**: `0x01` (Yes) or `0x00` (No)
- **Action**: `0x01` (Start/Run) or `0x00` (Stop)
- **Time**: Hours (0-23) and Minutes (0-59)

### Example Schedule
- **Monday**: Run 06:30 to 08:30
- **Other Days**: Disabled

**Monday Bytes:**
```
01 01 06 1E 08 1E
```
- `01`: Enabled
- `01`: Action (Run)
- `06 1E`: Start 06:30
- `08 1E`: End 08:30

**Payload (42 bytes):**
```
01 01 06 1E 08 1E (Mon)
00 00 00 00 00 00 (Tue)
00 00 00 00 00 00 (Wed)
... (Thu-Sun)
```

## 2. Build Command

**Target:**
- **Sub ID**: `1000` (`0x03E8`) - Layer 0
- **Obj ID**: `84` (`0x0054`) - Schedule

**Header Structure:**
```
[Start] [Length] [Dest] [Src] [Class] [OpSpec] [Sub-H] [Sub-L] [Obj-H] [Obj-L] ...
```

**OpSpec:**
- SET (Long): `0xB3`

**Type Header (Specific to Object 84):**
- Before the data, we need a 3-byte type header and 2-byte size.
- `00 DA 01` (Type 218)
- `00 2A` (Size 42 bytes)

**Full Packet Construction (59 bytes):**

| Section | Bytes | Value | Description |
| :--- | :--- | :--- | :--- |
| **Header** | 0-3 | `27 3B E7 F8` | Req, Len 59, Dest, Src |
| **APDU** | 4-5 | `0A B3` | Class 10, OpSpec SET |
| **IDs** | 6-9 | `00 54 03 E8` | Obj 84, Sub 1000 |
| **Type** | 10-12 | `00 DA 01` | Type Header |
| **Size** | 13-14 | `00 2A` | Data Size (42) |
| **Data** | 15-56 | `01 01 ...` | 42 bytes of schedule |
| **CRC** | 57-58 | `XX XX` | CRC-16 |

## 3. BLE Packet Splitting

The 59-byte packet **cannot** be sent in one go. It must be split into 20-byte chunks.

### Chunk 1 (Bytes 0-19)
```
27 3B E7 F8 0A B3 00 54 03 E8 00 DA 01 00 2A 01 01 06 1E 08
```

### Chunk 2 (Bytes 20-39)
```
1E 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

### Chunk 3 (Bytes 40-58)
```
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 XX XX
```

### Sending Sequence
1. Write Chunk 1
2. **Wait 10ms** (Critical!)
3. Write Chunk 2
4. **Wait 10ms**
5. Write Chunk 3

## 4. Response

The pump reassembles the chunks and, if valid, sends an acknowledgment.

```
24 0A 20 E7 0A 34 00 54 03 E8 XX XX
```

**Breakdown:**
- `24`: Response
- `34`: OpSpec (SET Response)
- `00 54`: Obj ID
- `03 E8`: Sub ID
- Success!

## 5. Common Pitfalls

1.  **No Splitting**: Sending 59 bytes at once will be ignored by the pump.
2.  **No Delays**: Sending chunks too fast will overflow the pump's buffer.
3.  **Wrong Length**: The length byte in Chunk 1 must be `0x3B` (59), describing the **total** packet, not just the chunk.
4.  **CRC**: Calculated over the **full** 59 bytes.

## 6. Verification

After writing, read back the schedule to verify.

**Read Request:**
```
27 0D E7 F8 0A 03 00 54 03 E8 00 XX XX
```

**Response:**
Should contain the same 42 bytes of data.