# Units on the wire

Two things in this protocol are stored in units the API does not use, and
both were the cause of long-lived bugs. The rule is not "convert
everything" or "convert nothing" - it is per-field, and the table below is
the authority.

Every entry was checked against a real ALPHA HWR; see
[bench findings](bench_findings.md) for the measurements.

## Telemetry: already in physical units

Live readings arrive as IEEE-754 floats in the unit you want. No scaling,
no GENI unit-index lookup, no offset.

| Reading | Unit |
| :--- | :--- |
| Flow | m³/h |
| Head | m |
| Temperature | °C |
| Speed | RPM |
| Power | W |
| Voltage | V |
| Current | A |
| Inlet / outlet pressure | bar |

## Setpoints: SI, and not the same as telemetry

| Setpoint | Wire unit | API unit | Factor |
| :--- | :--- | :--- | :--- |
| Constant / proportional pressure | Pa | m | × 9806.65 writing, ÷ writing back |
| Constant speed | RPM | RPM | none |
| **Constant flow** | **m³/s** | **m³/h** | **÷ 3600 writing, × 3600 reading** |
| Cycle-mode flow (Obj 91 Sub 421) | m³/s | m³/h | ÷ 3600 / × 3600 |
| Temperature range (Obj 91 Sub 430) | °C | °C | none |

### Why flow is the dangerous one

Telemetry flow really is m³/h and the flow *setpoint* really is m³/s. They
are different encodings of the same quantity, not a mismatch to be
reconciled - so a single "flow conversion" applied everywhere is wrong in
one direction or the other.

Writing m³/h straight through sends a commanded 2.5 as 2.5 m³/s, which is
9000 m³/h. The pump rejects it as out of range and keeps its old value, so
the register appears frozen and reads back about 1000× low. That reads like
a broken readback, and was diagnosed as one for a long time; it is a broken
write.

## Limits are the pump's, and it clamps rather than refusing

The library validates against generous ranges and lets the pump decide.
Asking for a value outside its limits is not an error: it stores its own
and reports it back, which surfaces as a `clamped` write result carrying
the stored value.

Measured on one unit - yours may differ, since installer settings in the
Grundfos GO app (pipe size, maximum flow) also clamp:

| Requested | Stored |
| :--- | :--- |
| 600 RPM | 1650 |
| 4400 RPM | 3671 |

Both ends appear verbatim in the pump's own speed-limits block (Object 86
Sub 13). That block is also where the number 3671 came from: it is the
maximum, and it used to be sent as the "default" setpoint suffix on every
start - so a start command was a request to run at full speed.

## Timestamps are local Unix time

Single-event windows (Object 84, Sub 900+) store the wall clock stamped as
though it were UTC - `timegm(local fields)` - matching the pump's RTC,
which reports bare wall-clock fields with no offset.

This one cannot be caught by verification. The value round-trips
byte-identically under either interpretation, so a write settles as
accepted and a readback agrees with itself while the event opens hours from
where it was meant to. It was settled here by writing an event and watching
the motor: it started within a few seconds of the intended wall clock.

## Re-checking any of this

Read the object, decode the raw float, and compare against what the
Grundfos GO app shows for the same setting. A factor-of-3600 or 9806.65
discrepancy is the usual failure, and a value that will not change however
you write it usually means the write is out of range rather than the
register being read-only.
