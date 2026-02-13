# Packet Trace: Control Mode Setting

This document details how to control the pump mode and setpoint (e.g., set constant pressure to 1.5m).

## Overview

Control operations use **Class 10 SET** commands.
- **Sub ID**: `0x5600` (Control)
- **Obj ID**: `0x0601` (Setpoint/Mode Setting)

## 1. Set Mode and Setpoint

Setting a mode involves two steps:
1. Setting the Control Mode (Obj `0x0601` with mode-specific payload)
2. Setting the Setpoint value (Obj `0x0601` with float32 value)

### Step 1: Set Control Mode

Payload format: `2F 01 00 00 07 00 [Flag] [ModeByte] [Suffix(4)]`
- **Flag**: `0x00` (Run/Start), `0x01` (Stop)
- **ModeByte**: `0x00` (Pressure), `0x02` (Speed), `0x08` (Flow), `0x19` (DHW), `0x1B` (Temp)

**Example: Set Constant Pressure Mode**
```
27 12 E7 F8 0A 90 56 00 06 01 2F 01 00 00 07 00 00 00 45 65 70 00 [CRC]
```

### Step 2: Set Setpoint

**Example: Set Constant Pressure to 1.5 meters**
1. Convert meters to Pascals: `1.5 m * 9806.65 ≈ 14710.0 Pa`
2. Encode as Float (Big-Endian): `14710.0 -> 0x46 E5 B0 00`

**Packet:**
```
27 10 E7 F8 0A 84 56 00 06 01 46 E5 B0 00 [CRC]
```

### Step 3: Receive Acknowledgment

The pump responds with a Class 10 acknowledgment.

```
24 0A 20 E7 0A 34 56 00 06 01 [CRC]
```

**Breakdown:**
- `24`: Response
- `34`: OpSpec (SET Response)
- `56 00`: Sub ID
- `06 01`: Obj ID
- No error bits set in OpSpec

## 4. Control Mode Identifiers

The `ModeByte` and `Suffix` are used in Step 1 to select the operating mode.

| Mode | ModeByte | Suffix |
| :--- | :--- | :--- |
| Constant Pressure | `0x00` | `45 65 70 00` |
| Constant Speed | `0x02` | `45 65 70 00` |
| Constant Flow | `0x08` | `45 65 70 00` |
| DHW Cycle Time | `0x19` | `38 C6 70 00` |
| Temperature Range | `0x1B` | `39 67 70 00` |

## 5. Transaction Locking

**Critical:** Because the pump processes one command at a time, you must ensure no other commands are sent while waiting for the ACK.

```python
async with transaction_lock:
    await send_packet(set_mode_packet)
    await receive_ack()
```