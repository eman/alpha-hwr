# Packet Trace: Telemetry Stream

This document shows the telemetry stream from the pump, which provides real-time data about motor state, flow, pressure, and temperature.

## Overview

The ALPHA HWR uses **Class 10 DataObjects** for telemetry. Unlike older pumps that required polling registers (Class 3), this pump streams data automatically as notifications.

## 1. Enable Telemetry

After authentication, the pump automatically starts sending notifications. If it stops, you can request it or just wait.

### Packet Structure

Notifications use OpSpec `0x0E` (Notification).

```
[Start] [Length] [Src] [Dest] [Class] [OpSpec] [Sub-H] [Sub-L] [Obj-H] [Obj-L] [Payload...] [CRC]
```

## 2. Motor State (Sub 0x0045, Obj 0x0057)

This object contains electrical and mechanical motor data.

### Sample Packet

```
24 34 20 E7 0A 0E 00 45 00 57 43 66 00 00 3E CC CC CD 42 48 00 00 44 BB 80 00 42 28 00 00 ... XX XX
```

**Breakdown:**
- `24`: Response start
- `34`: Length (52 bytes)
- `20`: Source (Pump)
- `E7`: Dest (Client)
- `0A`: Class 10
- `0E`: OpSpec (Notification)
- `00 45`: Sub ID (Motor)
- `00 57`: Obj ID (State)
- `Payload`: 44 bytes of data

### Payload Decoding

All values are IEEE 754 Big-Endian floats.

| Offset | Field | Value (Hex) | Decoded | Unit |
| :--- | :--- | :--- | :--- | :--- |
| 0-3 | Grid Voltage | `43 66 00 00` | 230.0 | Volts |
| 4-7 | Reserved | `...` | - | - |
| 8-11 | Current | `3E CC CC CD` | 0.4 | Amps |
| 12-15 | Reserved | `...` | - | - |
| 16-19 | Power | `42 48 00 00` | 50.0 | Watts |
| 20-23 | Speed | `44 BB 80 00` | 1500.0 | RPM |
| 24-27 | Temperature | `42 28 00 00` | 42.0 | °C |

**Note:** There are gaps (reserved bytes) between some fields. Always verify offsets.

## 3. Flow & Pressure (Sub 0x0122, Obj 0x005D)

This object contains hydraulic data.

### Sample Packet

```
24 18 20 E7 0A 0E 01 22 00 5D 3F 00 00 00 3F C0 00 00 40 00 00 00 40 40 00 00 XX XX
```

**Breakdown:**
- `01 22`: Sub ID (Hydraulic)
- `00 5D`: Obj ID (Process Values)
- `Payload`: 16 bytes

### Payload Decoding

| Offset | Field | Value (Hex) | Decoded | Unit |
| :--- | :--- | :--- | :--- | :--- |
| 0-3 | Flow Rate | `3F 00 00 00` | 0.5 | m³/h |
| 4-7 | Head Pressure | `3F C0 00 00` | 1.5 | m |
| 8-11 | Inlet Pressure | `40 00 00 00` | 2.0 | bar |
| 12-15 | Outlet Pressure | `40 40 00 00` | 3.0 | bar |

## 4. Temperature (Sub 0x012C, Obj 0x005D)

This object contains thermal sensor data.

### Sample Packet

```
24 11 20 E7 0A 0E 01 2C 00 5D 42 34 00 00 42 10 00 00 42 1A 00 00 XX XX
```

### Payload Decoding

| Offset | Field | Value (Hex) | Decoded | Unit |
| :--- | :--- | :--- | :--- | :--- |
| 0-3 | Media Temp | `42 34 00 00` | 45.0 | °C |
| 4-7 | PCB Temp | `42 10 00 00` | 36.0 | °C |
| 8-11 | Box Temp | `42 1A 00 00` | 38.5 | °C |

## 5. Polling Telemetry (Requesting Updates)

If notifications stop, you can poll for updates using an INFO command.

### Request

```
27 0D E7 F8 0A 03 00 45 00 57 00 XX XX
```

**Breakdown:**
- `0A`: Class 10
- `03`: OpSpec (INFO/Read)
- `00 45`: Sub ID (Motor)
- `00 57`: Obj ID (State)
- `00`: Extra byte (often required)

### Response

A poll may be answered by the unsolicited notification stream (byte 5 = `0x0E`) or by a direct read response, whose byte 5 is the **payload length** rather than a type code. Match the reply by its identifier pair — see [Wire Format](../wire_format.md#matching-a-reply-to-a-request).

## 6. Implementation Notes

1. **Passive vs Active**: Prefer listening to passive notifications (OpSpec 0x0E) to save battery and bandwidth.
2. **Missing Data**: Some fields might be `NaN` (`0x7FC00000`) if the sensor is not available.
3. **Frequency**: Updates typically arrive at **~10 Hz** when the pump is running.
4. **Filtering**: Always check Sub ID and Obj ID to know which decoder to use.

```python
if frame.sub_id == 0x0045 and frame.obj_id == 0x0057:
    decode_motor_state(frame.payload)
elif frame.sub_id == 0x0122 and frame.obj_id == 0x005D:
    decode_flow_pressure(frame.payload)
```