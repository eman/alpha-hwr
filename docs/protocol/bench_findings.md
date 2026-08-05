# Bench findings

Measured against an ALPHA HWR (BLE `EF159DD1-…`, firmware reporting
2026-08-04) rather than inferred from code or captures. Each entry says what
was measured and how, so a future disagreement can be settled by repeating
the measurement instead of re-reading the source.

## The second byte of a response is a length field

Not an operation specifier. Across 13 objects and 10 distinct values the
operation bits are always `00`, and both of these hold without exception:

    len(frame)  == (byte5 & 0x3F) + 8
    frame[1]    == (byte5 & 0x3F) + 4

This retired an inherited filter. The set `{0x30, 0x2B, 0x14, 0x2E, 0x2D,
0x09}`, carried in the code as "register-read operation specifiers", is
really the payload sizes 48, 43, 20, 46, 45 and 9 — so it rejected replies
*by length*. That is why the event log, whose entries carry a 20-byte
payload, had to be exempted from it by hand.

## Replies are identified by a per-object type code

The pump does not echo the Object/Sub it was asked for. It answers with a
type code, stable per object, in the identifier fields at bytes 6-9. The
measured table lives in `protocol/matcher.py::RESPONSE_IDENTIFIERS`; range
ends were checked rather than extrapolated, which is how the power-on-time
trend (`53/454`) turned out to use a different type from the other three.

Two objects share a type code and differ only in the first field:

| Object | Identifiers |
| --- | --- |
| 91/430 temperature range | `0x0003, 0xF402` |
| 88/10200+ event log entry | `0x0000, 0xF402` |

so the "Sub-ID 0 is a wildcard" rule that used to discard the first field
made each a valid answer to the other's read.

## Object 86: which sub-id reports what

| Sub | Role | Measured |
| --- | --- | --- |
| 6 | operation request | `control_source = 0` regardless of state |
| 7 | prioritized state | `control_source = 1` (Local/Panel) |
| 10 | mode request | reads back `operation_mode = NoCmd`, `set_point = NaN` |

Sub 7 is the one worth reading. Sub 10 reading back its own no-op sentinels
is what confirmed the unfused mode-change payload.

## 3671.0 is the pump's maximum speed setpoint

Requesting 600 RPM stored 1650; requesting 4400 stored **3671.0**. It also
appears verbatim in the speed-limits block (`86/13`), alongside 1650 as the
minimum. So the old default suffix `45 65 70 00` was not an arbitrary
constant — every `start()` that fell back to it was commanding *maximum
speed*.

The pump clamps rather than rejecting, which is what makes a `clamped`
verdict meaningful: the write succeeds and stores a different value.

## Flow setpoints are SI m³/s; telemetry flow is m³/h

Both are correct, and they are different encodings rather than a mismatch.
A setpoint written in m³/h reaches the pump 3600× too large and is rejected
as out of range, leaving the stored value untouched — which is why the
register looked frozen.

## Object 91: Sub 421 holds the live cycle configuration

`[flow setpoint f32 m³/s][on minutes][off minutes]`, measured as
`0.227 m³/h, 5, 15`. Sub 430 is `TemperatureRangeControlUserSettings`,
whose trailing bytes are the on/off-time *limits*: measured `0f 3c 02 05 01`,
not the `00 00 00 16 00` the code used to send as a constant.

## A setpoint write while stopped turns the pump on

Measured directly: stopped, wrote a Constant Speed setpoint, pump came on.
The control frame fuses the run state with the setpoint, so a write has to
carry *some* run state — which is why it must be resolved from the pump
rather than assumed.

## The configuration commit carries the schedule's enabled flag

The commit writes the whole ClockProgramOverview. The hardcoded APDU the
code used to send had `clock_program_enabled = 0x00`, so — because a commit
follows every setpoint write — changing a setpoint switched a live schedule
off. Observed on a real schedule.

## The clock program only acts when the pump is AUTO

A stopped pump ignores it: a weekly window opened with the motor at 0 RPM
throughout. Combined with the rule that the motor runs only inside a window
when the schedule is enabled, `STOP` + schedule-enabled is a state that can
never run.

Disabling the weekly schedule also disables single events — they are part of
the same clock program.

## Single-event timestamps are local Unix time

Wall-clock fields stamped as though they were UTC (`timegm(local fields)`),
not a true UTC epoch. Measured behaviourally: with the pump AUTO, the
schedule enabled and no weekly window competing, an event written under this
encoding started the motor **4 seconds** after the intended wall clock. The
two candidate encodings are a UTC offset apart, so the result is unambiguous.

This cannot be caught by verification: the value round-trips byte-identically
either way, so the write settles as accepted and a readback agrees with
itself while the event opens hours from where it was meant to.

## This pump exposes 5 single-event slots, not 35

`ClockProgramOverview` byte 1 (`max_nof_single_events`) reads `0x05`, and
Object 84 Sub 905 does not answer. The slot count should be taken from the
overview rather than assumed.
