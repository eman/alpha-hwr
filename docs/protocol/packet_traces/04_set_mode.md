# Packet Trace: Control Mode Setting

This document details how to control the pump mode and setpoint (e.g., set constant pressure to 1.5m).

## Overview

Control operations use **Class 10 SET** commands.
- **Sub ID**: `0x5600` (Control)
- **Obj ID**: `0x0601` (Setpoint) or `0x0600` (Mode)

## 1. Set Constant Pressure Mode

To set the pump to Constant Pressure mode with a setpoint of 1.5 meters.

### Step 1: Calculate Setpoint

1. Convert meters to Pascals:
   ```
   1.5 m * 9806.65 = 14709.975 Pa ≈ 14710.0 Pa
   ```
2. Encode as Float (Big-Endian):
   ```
   14710.0 -> 0x46 E5 B0 00
   ```

### Step 2: Build Command

**Packet Structure:**
```
[Start] [Length] [Dest] [Src] [Class] [OpSpec] [Sub-H] [Sub-L] [Obj-H] [Obj-L] [Data...] [CRC]
```

**OpSpec Calculation:**
- SET Operation: `0x80`
- Data Length: 4 bytes (`0x04`)
- OpSpec = `0x80 | 0x04` = `0x84`

**Full Packet:**
```
27 10 E7 F8 0A 84 56 00 06 01 46 E5 B0 00 XX XX
```

**Breakdown:**
- `27`: Request
- `10`: Length (16 bytes)
- `E7`: Service ID
- `F8`: Source
- `0A`: Class 10
- `84`: OpSpec (SET + 4 bytes)
- `56 00`: Sub ID (Control)
- `06 01`: Obj ID (Setpoint)
- `46 E5 B0 00`: Payload (14710.0)

### Step 3: Receive Acknowledgment

The pump responds with a Class 10 acknowledgment.

```
24 0A 20 E7 0A 34 56 00 06 01 XX XX
```

**Breakdown:**
- `24`: Response
- `34`: OpSpec (SET Response)
- `56 00`: Sub ID
- `06 01`: Obj ID
- No error bits set in OpSpec

## 2. Stop Pump

To stop the pump, set the mode to STOP.

**Packet:**
```
27 10 E7 F8 0A 84 56 00 06 00 00 00 00 00 XX XX
```

- **Obj ID**: `0x0600` (Mode/Command)
- **Value**: `0.0` (Stop)

## 3. Start Pump

To start the pump (return to previous mode).

**Packet:**
```
27 10 E7 F8 0A 84 56 00 06 00 3F 80 00 00 XX XX
```

- **Obj ID**: `0x0600` (Mode/Command)
- **Value**: `1.0` (Start)

## 4. Control Modes

Different modes are selected via Object `0x0600` or `0x0601` depending on firmware version.

| Mode | Value | Sub ID | Obj ID |
| :--- | :--- | :--- | :--- |
| Stop | `0.0` | `0x5600` | `0x0600` |
| Start | `1.0` | `0x5600` | `0x0600` |
| Constant Pressure | Setpoint (Pa) | `0x5600` | `0x0601` |
| Proportional Pressure | Setpoint (Pa) | `0x5600` | `0x0601` |
| Constant Curve | Speed (%) | `0x5600` | `0x0601` |
| AutoAdapt | Special | `0x5600` | `0x0603` |

**Note:** The exact Obj ID can vary. The safest approach is:
1. Use `0x0600` for Start/Stop.
2. Use `0x0601` for setting pressure/flow values.

## 5. Transaction Locking

**Critical:** Because the pump processes one command at a time, you must ensure no other commands are sent while waiting for the ACK.

```python
async with transaction_lock:
    await send_packet(set_mode_packet)
    await receive_ack()
```