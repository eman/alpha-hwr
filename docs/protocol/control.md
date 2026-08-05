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
*   **Action**: Split the frame into as many 20-byte chunks as it needs, pacing
    each write. Do not assume two: a 24-byte control packet takes two, but a
    59-byte schedule-layer write takes **three** (20 + 20 + 19).
*   *Failure to split causes the device to silently drop the packet or return a CRC error.*

> A two-chunk implementation looks correct on control packets and silently
> truncates anything over 40 bytes. That shipped here, and the schedule write
> was the casualty — the second "chunk" still exceeded the MTU.

### 2. Transaction Locking
The pump streams telemetry at ~10Hz. If a telemetry read request or notification is interleaved between the two fragments of your control command, the device's buffer will be corrupted.
*   **Action**: Ensure exclusive access to the BLE characteristic during the split-write sequence.

### 3. Configuration Commit
Even after successfully writing the control command, the pump may revert to its previous state immediately unless the change is "committed".
*   **Action**: Send a specific "Configuration Commit" packet immediately after the control command.

## Remote Control Mode — not supported, deliberately

The GENI protocol has a Remote Mode, and this library used to expose it. It is
gone, because on the ALPHA it does the opposite of what its name suggests.

Measured on hardware:

- Engaging Remote **stops the pump acting on commands from the BLE link** for
  roughly 35-45 seconds, until it self-cancels. The pump appears to treat the
  BLE connection as its *local* control source, so claiming Remote priority
  deprioritises the only controller present.
- It does not persist. It reverts on its own after ~35 s unless re-asserted,
  and ordinary telemetry polling does not hold it.
- The pump accepts commands perfectly well in Local, and always has.

So there was demonstrated harm and no demonstrated benefit. `control_source`
is still readable — from Object 86 Sub 7, see below — and reads `1`
(Local/Panel) in normal operation.

For the record, since older versions of this document had it wrong: the
commands were Class 3 IDs `7` (Remote) and `8` (Local), sent as **SET**
(`0x81`). The `0xC1` opcode this document used to specify is INFO, which the
pump answers with a descriptor rather than executing — so the frames it
described would not have done anything even if the feature were wanted.

## Packet Structure

### Control Command Payload

> **This object writes three things at once.** Object 86 sub-id 6 (wire
> `Obj 0x0601`) fuses the run state, the control mode and the setpoint into one
> frame, so anything sent through it necessarily asserts all three. It is used
> **only for setpoint writes** now — start/stop goes through Class 3 and mode
> changes through sub-id 10. See the Object 86 table below.

The payload for `Sub 0x5600, Obj 0x0601` follows this structure:

`2F 01 00 00 07 00 [RunState] [Mode] [Suffix...]`

| Offset | Field | Value | Description |
| :--- | :--- | :--- | :--- |
| 0-1 | **Header** | `2F 01` | Fixed header for this object. |
| 2-5 | **Padding** | `00 00 07 00` | Fixed padding/flags. |
| 6 | **operation_mode** | `0x00`, `0x01`, `0x06` | `0x00` = AUTO, `0x01` = STOP, `0x06` = NoCmd (leave alone) |
| 7 | **Mode** | `0x00` - `0xFF` | Control Mode ID (see below). |
| 8-11 | **set_point** | float32 BE | The setpoint, or `7F FF FF FF` (NaN) to keep the stored one. |

> **Never send `45 65 70 00` here.** That decodes to exactly **3671.0**, which
> is this pump's *maximum speed setpoint* — it appears verbatim in the pump's
> own limits block at Object 86 Sub 13. It was long treated as an inert
> placeholder, so every start command wrote "run at full speed" over whatever
> setpoint the mode had. Where no setpoint is being asserted, send NaN
> (`7F FF FF FF`), which the pump reads as "keep what you have".

### Configuration Commit Packet
This packet confirms the changes.
*   **Target**: Object 84 Sub 1 (`ClockProgramOverview`), type 218 (`0xDA01`)
*   **OpSpec**: `0x93`
*   **Payload**: the pump's current 10-byte overview, read back and rewritten.

> **Do not send a constant here.** The commit carries the *whole*
> ClockProgramOverview, and byte 4 of that structure is the schedule's enabled
> flag. Earlier versions of this document published a fixed packet whose byte 4
> was `0x00` — and because a commit follows every setpoint write, sending it
> switched the user's weekly schedule off every time they changed a setpoint.
>
> Read Object 84 Sub 1, modify only what you mean to change, and write it back.
> If the overview cannot be read, send no commit at all: skipping a flush is
> recoverable, overwriting the schedule state is not.

Frame shape, with `[overview]` being those 10 bytes:

```
27 17 E7 F8 0A 93 54 00 01 00 DA 01 00 00 0A [overview x10] [CRC]
```

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

## Example: Run at 1650 RPM in Constant Speed

Three separate frames, because the three things being asked for are separate
concerns and the fused object cannot express one without asserting the others.
Each is shown whole; each is sent in 20-byte chunks.

1.  **Set the mode** — Object 86 Sub 10, `operation_mode = NoCmd (0x06)`,
    setpoint `7F FF FF FF` (keep):

    ```
    27 14 E7 F8 0A 90 56 00 0A 01 2F 01 00 00 07 00 06 02 7F FF FF FF 0C EC
    ```

    No commit follows. A mode change persists by itself, and the commit
    writes the *schedule*, which has nothing to do with the control mode.

2.  **Set the setpoint** — Object 86 Sub 6 (fused), `operation_mode = AUTO
    (0x00)`, mode `0x02`, setpoint `44 CE 40 00` = 1650.0:

    ```
    27 14 E7 F8 0A 90 56 00 06 01 2F 01 00 00 07 00 00 02 44 CE 40 00 47 63
    ```

    Then send the configuration commit, built from the pump's current
    ClockProgramOverview as described above.

3.  **Start the pump** — Class 3, and nothing else:

    ```
    27 05 E7 F8 03 81 06 E5 87
    ```

    `0x06` = START, `0x05` = STOP. Nine bytes, with no room for a mode or a
    setpoint — which is the point.

**Then read back.** The acknowledgement means the frame was accepted, not
that the value was stored. Request 600 RPM and the pump acknowledges, then
stores 1650: its minimum. Read Object 86 Sub 7 to find out what actually
happened.

## Setpoint Configuration

Each control mode has factory-configured minimum, maximum, and default setpoint values stored in the pump's non-volatile memory.

### Object 86: the control objects

Object 86 carries several sub-objects, and which one you address decides
what a read or write actually does. Getting this wrong is quiet rather than
loud, so the distinction is worth stating plainly:

| Sub | Name | Direction | What it does |
| :--- | :--- | :--- | :--- |
| 5 | `overall_remote_operation_request` | write | Remote operation request |
| 6 | `overall_operation_local_request` | write | **Fused**: run state + control mode + setpoint, all in one frame |
| 7 | `overall_operation_prioritized_request` | read | The pump's state after it has weighed remote, local and alarm influence |
| 10 | `overall_control_mode_local_request` | write | Control mode **only** |
| 13/15/39 | setpoint limits | read | Per-mode limits (see below) |

**Read state from Sub 7, not Sub 6.** Sub 6 is the request object: it
reports what was last written, and its `control_source` byte reads `0`
whatever the pump is doing. Measured side by side on hardware, Sub 6
returned `control_source = 0` while Sub 7 returned `1` (Local/Panel).
Reading remote/local state from Sub 6 can only ever say "undefined".

Response payload, after an optional 3-byte header:

```
[control_source][operation_mode][control_mode][setpoint f32 BE]
```

`control_source`: 1 = Local/Panel, 2 = Remote/Digital.
`operation_mode`: 0 = AUTO, 1 = STOP, 6 = NoCmd (a write sentinel).

**Change the mode through Sub 10, not Sub 6.** Sub 6 writes the setpoint in
the same frame, so a mode change through it either forces the pump on or
overwrites the target mode's stored setpoint with whatever was supplied.
Sub 10 carries no-op sentinels in those fields - `operation_mode = 0x06`
(NoCmd) and `set_point = 0x7FFFFFFF` (NaN) - and applies only the mode.
Reading Sub 10 back returns exactly those sentinels, which is how the
format was confirmed.

Wire form: Sub 10 is addressed as Obj `0x0A01` / Sub `0x5600`; Sub 6 is
Obj `0x0601` / Sub `0x5600`.

### Run state: Class 3, not Object 86

Starting and stopping the pump uses the Class 3 run commands, which carry
no mode and no setpoint and so cannot disturb either:

| Command | Frame |
| :--- | :--- |
| START | `27 05 E7 F8 03 81 06 <CRC>` |
| STOP | `27 05 E7 F8 03 81 05 <CRC>` |

The operation specifier is `0x81` (SET). `0xC1` (INFO) is answered with a
descriptor rather than executed. The pump acknowledges with a bare frame -
`[03 00]` for a command it ran, `[03 01 xx]` for one it only described -
and sends no notification afterwards, so the resulting run state has to be
read back.

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