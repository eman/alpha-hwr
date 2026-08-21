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

## The temperature-range object validates nothing

Measured 2026-08-05, writing through `set_temperature_range_control` and
reading back each time. The pump stored **every** value offered, including
ones no hot-water system could mean:

| Asked | Stored |
| :--- | :--- |
| 20.0 – 25.0 | 20.0 – 25.0 |
| 55.0 – 60.0 | 55.0 – 60.0 |
| 60.0 – 65.0 | 60.0 – 65.0 |
| 62.0 – 70.0 | 62.0 – 70.0 |
| 15.0 – 25.0 | 15.0 – 25.0 |
| 0.0 – 5.0 | 0.0 – 5.0 |
| −10.0 – 0.0 | −10.0 – 0.0 |
| 90.0 – 99.0 | 90.0 – 99.0 |
| 100.0 – 120.0 | 100.0 – 120.0 |

No clamping, no rejection, no lower or upper bound anywhere in the range
tried. This is the opposite of the setpoint objects, which clamp silently
(600 RPM → 1650), and it matters for two reasons:

1. **The client's 20–70 °C guard is the only guard there is.** It is not a
   mirror of a firmware limit — nothing on the pump will stop a caller
   storing −10 °C. Ports that omit their own validation have none.
2. **A `clamped` result is impossible for this object**, so an `accepted`
   here really does mean the pump holds what you asked for.

The pump was restored to its original 35.0 / 38.9 / autoadapt-on afterwards.

## Setpoint clamping, re-confirmed

Measured again 2026-08-05 through the verified write path, on the same unit:

| Asked | Status | Stored |
| :--- | :--- | :--- |
| 600 RPM | `clamped` | 1650.0 |
| 4400 RPM | `clamped` | 3671.0 |
| 2000 RPM | `accepted` | 2000.0 |

Identical to the first measurement, and identical to the pump's own limits
block at Object 86 Sub 13. The schedule was still enabled afterwards, which
is the configuration-commit fix holding.

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

---

# 2026-08-20 session

Measured against the same ALPHA HWR, reported by its own Class 7 strings as
product `ALPHA HWR`, serial `10000479`, software `92601618V04.02.01.02539`,
hardware `92601617V01.03.00.00469`, BLE `92811431V06.00.01.00001`. Its
advertisement reports family 52, type 7, version 2.

## The Class 7 header is six bytes, and byte 5 is a byte count

The reply is `[STX][LEN][DST][SRC][0x07][Count][...STRING...][CRC16]`. The
first character is at offset **6**, and there is no echoed string ID.

    24 0E F8 E7 07 0A 41 4C 50 48 41 20 48 57 52 00 83 8D
                    ^^ count = 10        ^^ "ALPHA HWR\0"

Reading from offset 7 dropped the first character of every string. The two
most-read strings were patched up afterwards and so looked correct — an "A"
prepended to `LPHA HWR`, and a "1" prepended to a serial reading `0000479`.
The second was right for this unit only by coincidence; a serial beginning
`20` would have been corrupted. The version strings had no such patch and
were short. Before and after, on the same pump:

    software  2601618V04.02.01.02539  ->  92601618V04.02.01.02539
    hardware  2601617V01.03.00.00469  ->  92601617V01.03.00.00469
    BLE       2811431V06.00.01.00001  ->  92811431V06.00.01.00001

## Class 7 needs no handshake at all

Five string reads answered on a link that had sent **no** opening packets —
connect, subscribe, read. This is the same conclusion `connection.md`
reached from the captures, now confirmed by not sending them.

## The type numbers, and a naming trap in this client

Bytes 6-9 of a reply are `[00][TypeH][TypeL][Version]`, so the type spans
bytes 7-8 and the version is byte 9. Decoded that way, and confirmed
against `geni_profile_52_7.xml`:

| bytes 6-9 | type / version | profile name |
|---|---|---|
| `00 01 00 03` | 256 v3 | `ProtectedMotorStateDetails` |
| `00 02 35 02` | 565 v2 | `PumpedMediaRelatedProcessValuesExtended` |
| `00 02 16 02` | 534 v2 | `MediaTemperatureInfo` |
| `00 02 3a 01` | 570 v1 | `FaultsByArrayExtended` |
| `00 01 2f 01` | 303 v1 | operation status |
| `00 01 2d 01` | 301 v1 | setpoint factory config |
| `00 00 da 01` | 218 v1 | `ClockProgramOverview` |
| `00 01 42 01` | 322 v1 | `DateTimeActual` |
| `00 03 f4 02` | 1012 v2 | temperature range config |

**The trap.** This client's `type_high` and `type_low_ver` split those same
four bytes into two 16-bit halves *one byte off* the real boundary - a
convention inherited from the ESPHome port, which kept it deliberately
because comparing both halves is equivalent to comparing type and version
together. That is true, and the matcher relies on it. But the names read as
though they were the type's own halves, and they are not: "type_low_ver
0x2F01" is not a type, it is the second byte of type 303 and its version.

Quote `object_type` / `object_version` in prose, and leave the pair form to
the matcher. The table above is the vocabulary the vendor's own profile
uses.

## A response's bytes 6-9 are `[00][TypeH][TypeL][Version]`

Measured by reading each object and recording the answer:

| read | reply bytes 6-9 | type |
|---|---|---|
| 86/7 operation status | `00 01 2f 01` | 303 v1 |
| 86/13, 86/15, 86/17, 86/39 | `00 01 2d 01` | 301 v1 — **all four** |
| 84/1 schedule overview | `00 00 da 01` | 218 v1 |
| 94/101 clock | `00 01 42 01` | 322 v1 |
| 91/430 temperature range | `00 03 f4 02` | 1012 v2 |
| motor state | `00 01 00 03` | 3 v1 |
| flow / head | `00 02 35 02` | 0x3502 v2 |
| temperatures | `00 02 16 02` | 0x1602 v2 |
| 88/0 alarms and 88/11 warnings | `00 02 3a 01` | 0x3A01 v2 — **both** |

Two collisions matter. The four setpoint ranges are indistinguishable in a
reply, so a chain reading them must be sequential and stop at the first
failure. Alarms and warnings are indistinguishable too, so only the caller
that issued the read knows which list came back.

`byte5 == len(frame) - 8` held for every frame recorded in this session.

## The pump publishes its own setpoint ranges

Object 86, type 301 v1, three big-endian floats at offsets 0, 4 and 8 of the
struct: default, minimum, maximum.

| sub | mode | default | min | max | native |
|---|---|---|---|---|---|
| 13 | constant speed | 2800 | **1650** | **3671** | RPM |
| 15 | constant pressure | 1.632 | **1.000** | **2.450** | Pa ÷ 9806.65 |
| 17 | proportional pressure | 3.649 | **2.599** | **4.569** | Pa ÷ 9806.65 |
| 39 | constant flow | 0.228 | **0.114** | **2.498** | m³/s × 3600 |

Every one of these contradicts the constants this client validated against
(500–4500 RPM, 0.5–10 m, 0.5–10 m, 0.1–10 m³/h), in both directions and on
every mode. Proportional pressure is the worst: a 0.5 m floor against a real
one of 2.6 m, a range that does not even overlap constant pressure's.

## A Class 10 reply carries a second acknowledgement

Confirmed by accident while probing the limiter objects. Reading a sub-id
the pump does not implement returns

    24 05 F8 E7 0A 01 04 EE 26

whose APDU head `0x01` is ack **OK** with one payload byte — and that byte
is `0x04`. That is the Class 10 status `OPERATION_FAILED`, from the
decompiled GO app's `GeniAPDU.CLASS10_ACK_*` (0 OK, 2 BUSY, 4
OPERATION_FAILED). So the head ack alone is not the verdict: an unimplemented
object answers "understood, and it failed".

The status byte must only be read at `len >= 9`. In an eight-byte frame
declaring one payload byte, `data[6]` is the CRC's high byte.

## The limiters: two of them, both disabled (ESPHome issue #274)

`geni_profile_52_7.xml` describes `limiter_user_config` (type 895, Obj 86 sub
600–619), `limiter_factory_config` (897, 620–639), `limiter_status` (896,
640–659) and `limitation_manager_status` (896, 660). The capture corpus stops
at 86/601 and 86/621, so this could only be settled on hardware.

Sub-ids 602–619, 622–639 and 642–659 **do not exist**: every one answers
`OPERATION_FAILED`. Only indices 1 and 2 are implemented, and the name enum
at `geni_profile_52_7.xml:1386` gives `MaxFlow = 1`, `MinFlow = 2`. So the
instances are per *limiter*, not per mode.

    user config 895, 18 bytes: [name][enable][limit f32 m³/s][kp][ti][td]
      600  01 00 38c676f1 3f19999a 3fcccccd 3ecccccd   MaxFlow disabled, 0.341 m³/h (1.50 gpm)
      601  02 00 3925631d 3f19999a 3fcccccd 3ecccccd   MinFlow disabled, 0.567 m³/h (2.50 gpm)

    factory config 897, 9 bytes: [name][lower f32][upper f32]
      620  01 38044f4b 3a35ed8d    MaxFlow  0.114 - 2.498 m³/h
      621  02 38844f4b 3a5700d9    MinFlow  0.227 - 2.952 m³/h

    status 896, 6 bytes: [name][limiting][reference f32]
      640  01 00 00000000    MaxFlow not limiting
      641  02 00 00000000    MinFlow not limiting
      660  00 00 00000000    manager not limiting

MaxFlow's factory bounds are exactly the constant-flow setpoint range read
from 86/39, which is what makes the type-301 range the *factory* range: it
does not account for a limiter that is enabled. On this unit neither is, so
a setpoint here is delivered as written. On a unit with MaxFlow enabled it
would not be, and nothing in the type-301 range would say so.

## Class 10 SETs *are* acknowledged, in 90-120 ms

Measured through this client against an ALPHA HWR, capturing every inbound
frame during a temperature-range write:

    Object 86 Sub 10   +119.6 ms   24 05 F8 E7 0A 01 00 AE A2
    Object 91 Sub 430  +119.8 ms   24 05 F8 E7 0A 01 00 AE A2
    Object 84 Sub 1     +89.8 ms   24 05 F8 E7 0A 01 00 AE A2

Consistent with the capture corpus, which puts SET latency at 36-193 ms and
nothing anywhere over 295 ms. `SET_ACK_TIMEOUT = 0.4` clears all of it.

The acknowledgement is not the verdict. This pump clamps values it dislikes
rather than refusing them, so only a readback says what was stored.

### The measurement that said otherwise, and why it was wrong

An earlier entry here claimed the opposite - that a Class 10 SET draws no
reply at all, and that the pump then answers nothing for 200-400 ms. Both
came from a raw probe that wrote each GENI frame in a single
`write_gatt_char` call, and **this pump ignores a frame that is not split
into 20-byte GATT writes**, whatever the ATT MTU has been negotiated to.

The negotiated MTU on this link is 65, so 27 bytes fits comfortably at the
ATT layer. It still does not work:

    Object 84 Sub 1 SET, one 27-byte write   -> no reply
    the same bytes, chunked at 20            -> acked in 111 ms
    Object 84 Sub 1 GET, 11 bytes, one write -> answered in 69 ms

Reads are 11 bytes and fit, which is why every read in that probe worked
and every write did not. The writes were never arriving, so nothing
answered them, and the "deaf window" was the pump's own reassembly timer
recovering from a truncated frame - the same mechanism as
esphome-alpha-hwr #200, seen from the other side.

Two lessons worth keeping. A negative result from a hand-rolled probe is
only as good as the probe: check it can do something you know works before
believing what it says is impossible. And `BLE_MTU_LIMIT = 20` in the
transport is a pump requirement, not a guess about the radio.

## An Object 91 Sub 430 write is visible ~450 ms after it is issued

Through the full write sequence — mode request, limits-tail read, Obj 91
SET, overview commit — polling the readback as fast as the link allows:

| run | target | visible after |
|---|---|---|
| 1 | 39.0 °C | 449 ms |
| 2 | 38.9 °C | 459 ms |
| 3 | 39.0 °C | 486 ms |
| 4 | 38.9 °C | 456 ms |

So the 1.2 s confirm delay is about 2.5× the settle time. Most of the
450 ms is the deaf window above: the commit is the last SET in the
sequence, and the readback cannot be answered until the pump returns.

A consequence worth stating, because it removes a failure mode rather than
adding one: reading *too early* does not return a stale value, it returns
nothing. The confirm already retries an unanswered read.

## The GO app sends consecutive SETs back to back

Recorded while chasing a window that turned out not to exist (above). It
still says something true about pacing.

**Consecutive SETs are not spaced.** Across the corpus there
are 289 consecutive SET-to-SET pairs:

    min 43 ms   p50 62   p90 121
    under 200 ms: 267 of 289

The tightest include `84/1000 -> 84/1001` at 43 ms - a schedule layer
upload - and `86/10 -> 91/430` at 54 ms, the mode-request-then-write pair.
Those uploads write five layers and then commit, and they work: if a SET
inside the window were dropped, every upload would lose four of its five
layers, and every single-event save would lose four of its five slots.

**The app's 2500 ms pause is armed only before a non-SET.** From
``DongleHelper.handleOutgoingQueue``:

    } else if (isSetOperation(t) && !isSetOperation(peekNextTelegramInQueue())) {
        this.noSentBefore = SystemClock.uptimeMillis() + getAfterSetPause();
    } else {
        this.noSentBefore = 0L;
    }

The ``else`` branch clears the pause outright, so consecutive writes are
deliberately not spaced. The 2500 ms is a read guard, not a write guard.

**GENIbus agrees.** The Application Programming Manual promises a reply per
request and says "the SET operation never returns anything but the APDU
Head" - which is exactly the nine-byte frame measured above.

## The raw Obj 91 write does not take on its own

Writing Object 91 Sub 430 directly — with a correct frame, a valid CRC,
and the overview commit after it — leaves the stored value unchanged,
whether the commit is sent 50 ms or 600 ms later (2 attempts each). The
same value written through the client's sequence, which sends the Object
86 Sub 10 mode request first, takes every time.

So the mode request is not optional dressing around the temperature-range
write; it is load-bearing. What exactly it enables was not established
here — only that the write does not persist without it.

## Frame-drop baseline: 23,579 frames, none dropped

Twenty-five minutes reading Object 84 Sub 1 as fast as the transport's
pacing allows, 15.7 frames per second. Sustained polling is normal for this
device - the GO app issues 2,516 GETs of Object 86 Sub 6 in the capture
corpus.

    duration        25.0 min
    reads issued    23,579
    unanswered      0
    frames received 23,579
    errors          0

    crc_failures           0
    stale_partials         0
    unsolicited_fragments  0
    runt_length_drops      0
    overflow_drops         0
    queue_full_drops       0

With zero events in 23,579 frames the 95% upper bound on the drop rate is
3/23,579 - better than **one in 7,860**. If the true rate were the one in
5,900 the ESPHome port saw, four drops would have been expected here and
seeing none has probability 0.018.

Two things this does *not* say. The ESPHome figure counts one occurrence
per 5,900 **log lines**, not per frame, so the two are not directly
comparable and the comparison above is indicative rather than a
contradiction. And this bounds *this* link - a macOS host a few metres from
the pump - not an ESP32's. A radio result does not travel between radios.

What it does establish is that the frame path is clean enough that a
timeout on this bench is not a silently corrupted frame, which is what the
counters exist to tell you. An earlier version of this note recorded 167
frames, which could not distinguish zero from one in 5,900.

## The pump keeps local wall clock, and has no idea UTC exists

This decides how every client must write the pump's clock, so it matters
beyond this codebase: the GO app, the ESPHome component and this library
all write the same register, and the pump cannot say which time base a
value arrived in.

Read from the bench unit:

    DateTimeActual  (94/101, type 322 v1)   07ea08140f221b0100040101
      year 2026  month 8  day 20  hour 15  min 34  sec 27
      day_w Thu   dst_status 1 = SummerTime
      -> 2026-08-20 15:34:27, against a host local clock of 15:34:28

    DaylightSavingTime (94/102, type 323 v1)  01030702020b0701023c
      enabled                 1
      start  Mar, Sunday, occurrence 2, hour 2
      end    Nov, Sunday, occurrence 1, hour 2
      time_offset             60

Three things follow, and the third is the one that settles the timestamps:

1. The clock is **local**. A device that reports whether it is currently in
   summer time is not keeping UTC.
2. The pump applies DST **itself** - enabled, with the US rule and a
   60-minute offset - so it shifts its own clock twice a year.
3. **There is no timezone or UTC-offset field anywhere in the GENI
   profile.** Searching the whole of `geni_profile_52_7.xml` for timezone,
   UTC, GMT or offset returns only electrical offsets and alarm names. The
   pump therefore cannot convert between bases even in principle.

So a 32-bit timestamp the pump stores - `ClockProgramSingleEvent`'s begin
and end, the event log's entries, the cycle timestamps - must be in the
same base as its clock, because the pump compares them against it and has
no offset to relate the two. That base is local. The stored value is the
local wall clock stamped as though it were UTC, which is what
`calendar.timegm` on naive local fields produces.

This agrees with the earlier behavioural measurement, where an event
written under this encoding started four seconds from its intended wall
clock - and it explains *why*, rather than leaving it as a lucky guess.

### What this client had wrong

`set_clock` and the single-event encoding were already right. The event log
and the trend history decoded their timestamps with
`datetime.fromtimestamp(ts, tz=UTC)`, which produces the correct digits
attached to the wrong instant: calling `.astimezone()` on one shifted it by
the local offset. All four surfaces now go through `alpha_hwr.pump_time`.

### A consequence worth knowing

Because the pump shifts its own clock at a DST transition, a stored event
keeps its *wall clock* across the boundary - an 07:00 event stays at 07:00.
That is almost certainly the intent, and it is another thing true-UTC
storage would break.

## The pump clamps a setpoint rather than refusing it

Measured through the client, constant speed, whose published range is
1650-3671 RPM:

    4000 RPM -> clamped   stored 3671
    2000 RPM -> accepted  stored 2000
     600 RPM -> clamped   stored 1650

Which reproduces the 0.7.0 note ("600 RPM is stored as 1650 and 4400
stores 3671") from a separate run, and settles how the client should
behave: it does not pre-refuse a value outside the published range. The
pump answers with what it stored, and that answer is more informative than
a refusal.

There is a second reason it must not, raised by @jfriend00 on
esphome-alpha-hwr #276 and worth recording here because it is not
recoverable from the range alone. **With a flow limiter enabled there is
no maximum speed.** The pump accepts a speed setpoint and then manages the
actual run speed to hold the flow bound, and where it settles is a property
of the installation's hydraulics rather than of the pump - on one reported
loop a 3000 RPM request delivered 1885 RPM. No number is the bound there,
so any check that looked authoritative would be wrong in a way the client
cannot detect.

So the published range is an *explanation*, not a gate. It goes in the
settle detail when the pump clamps, and only when it came from the pump:

    4000 RPM -> clamped: pump stored 3671; its range for this mode is
                         1650-3671 RPM

The one thing still refused before the wire is a value that is not a
number. There is nothing there for the pump to clamp to, and the all-ones
float doubles as the SETPOINT_KEEP sentinel, so a NaN would read as "leave
the setpoint alone" - a write that silently does nothing rather than one
that fails.
