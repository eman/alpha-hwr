# Pump Control

Controlling the ALPHA HWR (Start, Stop, Change Mode) involves sending specific Class 10 DataObject commands. Unlike simple registers, these commands require a strict sequence of operations, including packet fragmentation and a "Configuration Commit" step.

## Control Object

All primary control operations target the following GENI object:

*   **Class**: 10 (`0x0A`)
*   **SubID**: `0x5600` (Operation/Control)
*   **ObjID**: `0x0601` (Mode Configuration)
*   **Operation**: SET (`OpSpec` typically `0x90`)

## The Control Sequence (Critical)

Due to hardware limitations and firmware logic, sending a control command is not a simple atomic write. The following three rules must be observed:

### 1. MTU Fragmentation (Split-Writes)
The ALPHA HWR BLE interface has a hard **Maximum Transmission Unit (MTU) of 20 bytes** for write operations.
*   Control packets are typically **24 bytes** long.
*   **Action**: You must split the packet into two writes.
    1.  Write bytes 0-19.
    2.  Wait a small duration (e.g., 10ms).
    3.  Write remaining bytes (20-23).
*   *Failure to split causes the device to silently drop the packet or return a CRC error.*

### 2. Transaction Locking
The pump streams telemetry at ~10Hz. If a telemetry read request or notification is interleaved between the two fragments of your control command, the device's buffer will be corrupted.
*   **Action**: Ensure exclusive access to the BLE characteristic during the split-write sequence.

### 3. Configuration Commit
Even after successfully writing the control command, the pump may revert to its previous state immediately unless the change is "committed".
*   **Action**: Send a specific "Configuration Commit" packet immediately after the control command.

## Remote Control Mode

The ALPHA HWR can be placed in "Remote Control Mode", which changes how it prioritizes external commands over the physical operating panel.

### Overview
- **Override Local Control**: When active, the pump prioritizes commands from the Bluetooth interface and ignores most button presses on the physical panel.
- **Persistence**: Once enabled, the pump stays in Remote Mode until it is explicitly returned to "Auto" (local) control.
- **Command Lock**: This is recommended when an external controller (like a home automation system) is managing the pump's logic to prevent accidental local overrides.

### Technical Implementation
Remote mode uses the legacy **Class 3** (Register) protocol:

- **Enable Remote**: Command ID `7` (`0x03 C1 07`)
- **Disable Remote (Auto)**: Command ID `6` (`0x03 C1 06`)

These commands are sent to the standard GENI Service ID `0xE7` from Source `0xF8`.

## Packet Structure

### Control Command Payload
The payload for `Sub 0x5600, Obj 0x0601` follows this structure:

`2F 01 00 00 07 00 [RunState] [Mode] [Suffix...]`

| Offset | Field | Value | Description |
| :--- | :--- | :--- | :--- |
| 0-1 | **Header** | `2F 01` | Fixed header for this object. |
| 2-5 | **Padding** | `00 00 07 00` | Fixed padding/flags. |
| 6 | **Run State** | `0x00` or `0x01` | `0x00` = **START / RUN**<br>`0x01` = **STOP** |
| 7 | **Mode** | `0x00` - `0xFF` | Control Mode ID (see below). |
| 8-11 | **Suffix** | Variable | Mode-specific parameters (often `45 65 70 00`). |

### Configuration Commit Packet
This packet confirms the changes.
*   **Target**: `Sub 0x5400`, `Obj 0xDA01`
*   **OpSpec**: `0x93`
*   **Full Packet Hex**: `27 17 E7 F8 0A 93 54 00 01 00 DA 01 00 00 0A 02 05 00 05 00 01 00 00 00 00 F1 EE`

## Supported Control Modes

The `Mode` byte determines the regulation behavior.

| ID | Name | Description |
| :--- | :--- | :--- |
| `0` | **Constant Pressure** | Maintains constant differential pressure. |
| `1` | **Proportional Pressure** | Adjusts pressure based on flow. |
| `2` | **Constant Speed** | Runs at a fixed RPM (Default). |
| `5` | **AutoAdapt** | Automatically analyzes system needs (generic). |
| `8` | **Constant Flow** | Maintains a specific flow rate. |
| `13` | **AutoAdapt Radiator** | AutoAdapt optimized for radiator systems. |
| `14` | **AutoAdapt Underfloor** | AutoAdapt optimized for underfloor heating. |
| `15` | **AutoAdapt Combined** | AutoAdapt for combined radiator + underfloor systems. |
| `25` | **DHW On/Off** | Domestic Hot Water control. |

### AutoAdapt Mode Variants

The three AutoAdapt variants (IDs 13, 14, 15) are system-specific optimizations:

*   **Radiator (13)**: Optimized for high-temperature radiator systems with steeper pump curves.
*   **Underfloor (14)**: Optimized for low-temperature underfloor heating with flatter curves.
*   **Combined (15)**: Balanced optimization for mixed radiator and underfloor systems.

Each AutoAdapt mode has dedicated factory configuration Sub-IDs for reading setpoint limits and defaults.

## Example: Start Pump in Constant Speed

To start the pump in Constant Speed mode (Mode `0x02`):

1.  **Construct Payload**:
    *   Run State: `0x00` (Start)
    *   Mode: `0x02`
    *   Payload: `2F 01 00 00 07 00 00 02 45 65 70 00`

2.  **Wrap in GENI Frame**:
    *   Class 10, OpSpec 0x90, Sub 5600, Obj 0601.
    *   Full Packet: `27 14 E7 F8 0A 90 56 00 06 01 2F 01 00 00 07 00 00 02 45 65 70 00 [CRC]`

3.  **Split & Send**:
    *   Write `27 14 ... 00` (20 bytes).
    *   Write `02 45 65 70 00 [CRC]` (Remaining bytes).

4.  **Send Commit**:
    *   Write `27 17 E7 ... F1 EE` (Commit packet).

## Setpoint Configuration

Each control mode has factory-configured minimum, maximum, and default setpoint values stored in the pump's non-volatile memory.

### Factory Configuration Object

Setpoint limits are stored in:

*   **Class**: 10 (`0x0A`)
*   **Object**: 86 (`0x56`)
*   **Sub-IDs**: Mode-specific (see table below)

### Setpoint Limit Sub-IDs

Each control mode maps to a specific Sub-ID in Object 86 for reading its setpoint configuration:

| Control Mode | Sub-ID | Data Format |
| :--- | :--- | :--- |
| **Constant Speed** | 13 | 3x uint16 (min, max, default) in RPM |
| **Constant Pressure** | 15 | 3x uint16 (min, max, default) in Pascals |
| **Proportional Pressure** | 17 | 3x uint16 (min, max, default) in Pascals |
| **AutoAdapt Radiator** | 19 | 3x uint16 (min, max, default) in Pascals |
| **AutoAdapt Underfloor** | 21 | 3x uint16 (min, max, default) in Pascals |
| **AutoAdapt Combined** | 23 | 3x uint16 (min, max, default) in Pascals |
| **Constant Flow** | 39 | 3x uint16 (min, max, default) in m³/h |

### Reading Setpoint Limits

To read limits for Constant Pressure (Sub-ID 15):

1.  **Send Read Request**:
    *   Class 10, OpSpec 0x90, Object 86, Sub-ID 15
    *   Full Packet: `27 0C E7 F8 0A 90 56 00 00 86 00 0F [CRC]`

2.  **Parse Response**:
    *   Response payload contains 6 bytes after header
    *   Bytes 0-1: Minimum setpoint (uint16, big-endian)
    *   Bytes 2-3: Maximum setpoint (uint16, big-endian)
    *   Bytes 4-5: Default setpoint (uint16, big-endian)

3.  **Unit Conversion**:
    *   Pressure modes: Pascals ÷ 9806.65 = meters
    *   Speed modes: RPM (no conversion)
    *   Flow modes: m³/h (no conversion)

**Example:** Response `03 CE 09 8F 06 0A` decodes to:
*   Min: 974 Pa = 0.99 m
*   Max: 2447 Pa = 2.50 m
*   Default: 1546 Pa = 1.58 m

### Validation Workflow

Before setting a new setpoint value:

1.  Read the appropriate factory limits using `read_setpoint_limits(control_mode)`
2.  Validate the desired value is within `[min, max]` range
3.  If valid, proceed with the control command
4.  If invalid, reject and inform the user

The `AlphaHWRClient.validate_setpoint()` method automates this process with two modes:

*   **Non-strict** (default): Logs warning if limits unavailable, allows setpoint anyway
*   **Strict**: Fails validation if limits cannot be read

## Cumulative Statistics

The pump stores cumulative operational statistics in non-volatile memory:

*   **Class**: 10 (`0x0A`)
*   **Object**: 93 (`0x5D`)
*   **Sub-ID**: 1

### Statistics Data Format

The response payload is 31 bytes total (including 3-byte header):

| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0-2 | Header | `00 00 XX` | Fixed header bytes |
| 11-14 | Operating Time | uint32 | Total seconds of operation |
| 15-18 | Start Count | uint32 | Number of motor starts |

Both values are **big-endian** (network byte order).

**Example:** To read statistics:

1.  **Send Read Request**:
    *   Full Packet: `27 0C E7 F8 0A 90 5D 00 00 93 00 01 [CRC]`

2.  **Parse Response**:
    *   Extract bytes 11-14: Operating time in seconds
    *   Extract bytes 15-18: Start count
    *   Convert seconds to hours: `hours = seconds / 3600`

**Example Response:**
*   Bytes 11-14: `00 05 CD E8` = 380,392 seconds = 105.7 hours
*   Bytes 15-18: `00 00 02 70` = 624 starts