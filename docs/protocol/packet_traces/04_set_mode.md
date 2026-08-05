# Packet Trace: Control Mode and Setpoint

Changing the mode and changing the setpoint are two different writes to two
different objects. Earlier revisions of this page sent both through the fused
object with a `45 65 70 00` suffix; that suffix is 3671.0, the pump's maximum
speed, and sending it overwrote whatever setpoint the mode actually held.

## The three objects involved

| Purpose | Object | Wire type | OpSpec |
| :--- | :--- | :--- | :--- |
| Mode only | 86 Sub 10 (`overall_control_mode_local_request`) | `0x0A01` | `0x90` |
| Setpoint (fused) | 86 Sub 6 (`overall_operation_local_request`) | `0x0601` | `0x90` |
| Read back state | 86 Sub 7 (`overall_operation_prioritized_request`) | — | `0x03` |

Sub 6 is *fused*: one frame carries the run state, the control mode and the
setpoint. There is no way to write one of the three through it without
asserting all three, which is why the mode has its own object.

---

## 1. Set the control mode

Payload: `2F 01 00 00 07 [source] [operation_mode] [mode] [setpoint×4]`

- `source` — `0x00`, ignored by the pump
- `operation_mode` — `0x06` (**NoCmd**: leave the run state alone)
- `mode` — the mode byte
- `setpoint` — `7F FF FF FF` (NaN, "keep the stored value")

**Example: switch to Constant Pressure**

```
27 14 E7 F8 0A 90 56 00 0A 01 2F 01 00 00 07 00 06 00 7F FF FF FF 48 6F
```

Sent as two chunks: 20 bytes, then 4.

**No configuration commit follows a mode change.** The mode persists on its
own, and the commit writes the *schedule*, which has nothing to do with it.

---

## 2. Set the setpoint

Through the fused object, with `operation_mode = 0x00` (AUTO) and the real
float32 in the last four bytes.

**Example: Constant Pressure, 1.5 m**

1. Convert metres to Pascals: `1.5 × 9806.65 ≈ 14710.0 Pa`
2. Encode big-endian float32: `14710.0 → 46 65 D8 00`

```
27 14 E7 F8 0A 90 56 00 06 01 2F 01 00 00 07 00 00 00 46 65 D8 00 32 A7
```

### Then the configuration commit

The commit carries the pump's whole `ClockProgramOverview`, so it must be
**read first and written back**. With the overview `02 05 00 05 01 01 00 00
00 00`:

```
27 17 E7 F8 0A 93 54 00 01 00 DA 01 00 00 0A 02 05 00 05 01 01 00 00 00 00 B4 4E
```

Three chunks: 20 + 7 bytes.

!!! danger "Never send a fixed commit packet"

    Byte 4 of the overview is the schedule's enabled flag. A hardcoded commit
    blob with `0x00` there switches the user's weekly schedule off — and
    because a commit follows every setpoint write, that happens each time
    anyone changes a setpoint. If the overview cannot be read, send **no**
    commit: skipping a flush is recoverable; overwriting the schedule state
    is not.

---

## 3. Read back — the ack is not the verdict

The pump acknowledges with a short Class 10 frame, opspec `0x01` or `0x81`:

```
24 06 F8 E7 0A 01 00 00
```

**That means the frame was accepted, not that the value was stored.** Ask for
600 RPM and the pump acks, then stores 1650 — its minimum for the mode.
Ask for 4400 and it stores 3671. Clamping is normal and is not an error;
it is simply not what you asked for.

Read Object 86 **Sub 7** to find out what happened:

```
24 12 F8 E7 0A 0E 00 01 2F 01 00 00 07 01 00 1B 39 67 8A C3 F7 DD
```

Sub 6 is the request object — it reports what was last written, and its
`control_source` byte reads `0` whatever the pump is doing. Reading state
from it tells you about your own command, not about the pump.

---

## 4. Mode bytes

| Mode | Byte | Setpoint field |
| :--- | :--- | :--- |
| Constant Pressure | `0x00` | float32 Pa |
| Proportional Pressure | `0x01` | float32 Pa |
| Constant Speed | `0x02` | float32 RPM |
| Constant Flow | `0x08` | float32 **litres/hour** |
| AutoAdapt Radiator / Underfloor / Combined | `0x0D` / `0x0E` / `0x0F` | not implemented |
| DHW Cycle Time | `0x19` | suffix `38 C6 76 EF` |
| Temperature Range | `0x1B` | suffix `39 67 70 00` |

Generic AutoAdapt (mode 5) and Proportional Differential Pressure (mode 26)
have **no wire byte**. See [autoadapt_modes.md](../autoadapt_modes.md).

The four scalar modes carry a real float32 and never a fixed suffix. Only the
two non-scalar modes above have one. Units are in [units.md](../units.md) —
constant flow in particular is litres/hour on the wire, not m³/h, and the
conversion belongs on the write path as much as the read path.

---

## 5. One command at a time

The pump processes one command at a time, and its replies are not tagged with
the request that caused them. Serialise writes and match each reply against
the command that is waiting for it:

```python
async with transaction_lock:
    await send_packet(set_mode_packet)
    await receive_ack()
```

Response matching is `protocol/matcher.py`; the identifiers each object
answers with were measured, not guessed.
