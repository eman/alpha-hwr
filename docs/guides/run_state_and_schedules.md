# Run State and Schedules

## The combination that never runs

The pump has two independent flags: a run state and a schedule-enabled flag.
Measured with motor RPM as ground truth:

> The motor runs only when the run state is **AUTO** *and* the schedule is off
> (so it runs continuously) or a schedule window is currently open.

Four combinations, three of which behave the way you would expect:

| Run state | Schedule | `RunState` | What happens |
| :--- | :--- | :--- | :--- |
| Stopped | off | `off` | Idle, and will stay that way |
| Running | off | `engaged` | Follows the control mode continuously |
| Running | on | `scheduled` | Runs inside its windows, idles between |
| **Stopped** | **on** | **`stalled`** | **Nothing will ever run** |

The fourth is the one worth naming. The schedule is armed and the pump ignores
it, so every window opens and closes with the motor at 0 RPM — and **nothing
reports a fault**. It looks healthy from every angle except the water going
cold. It is reachable simply by setting the two flags independently, which
anyone might do.

```python
state = await client.get_run_state()
if state is RunState.STALLED:
    print("schedule is armed but the pump is stopped; it will never run")
```

`is_stalled(enabled, schedule_enabled)` is the same test as a plain function,
if you already have the two flags.

---

## Moving between states

```python
from alpha_hwr import RunState

result = await client.set_run_state(RunState.SCHEDULED)
```

`set_run_state` writes only the flags that differ, **in an order that never
passes through `stalled`**. Arming a schedule over a stopped pump — even for
the fraction of a second between two writes — is a window that can be missed
if a boundary falls in it.

So:

- **Arming a schedule starts the pump first**, then sets the schedule flag.
- **Stopping clears the schedule first**, then stops the pump.

`RunState.STALLED` is refused as a target. It is a diagnosis, not something to
ask for; passing it settles as `invalid`.

The returned `WriteResult` is the most severe of the underlying writes, so a
partial failure surfaces rather than being averaged away. Both flags are read
back from the pump afterwards — each leg only populates the flag it wrote, and
which leg runs last depends on the direction of travel.

---

## Single events

A single event is a one-time window layered over the weekly schedule. It lives
in Object 84, Sub 900 upward, one per slot.

```python
from datetime import datetime

events = await client.single_events.read_all()
for e in events:
    print(e)  # slot 0: 2026-08-10 06:00 -> 2026-08-10 08:00 (run)
```

| Method | Does |
| :--- | :--- |
| `slot_count()` | How many slots this pump has |
| `read(slot)` / `read_all()` | Read one or every slot |
| `find_free_slot()` | A slot that can be written without losing anything |
| `write(slot, begin, end, action=...)` | Write one |
| `clear(slot)` | Clear one |
| `set_vacation(begin, end)` | Hold the pump off across a range |
| `clear_vacation()` | Clear the first enabled hold |

### Slot capacity comes from the pump

Do not assume it. The sub-id range suggests 35; the unit this was written
against exposes **5**, and reading past them simply goes unanswered.
`slot_count()` reads the schedule overview and reports what the pump says.

### `find_free_slot` prefers genuinely empty slots

It reads every slot first — choosing without looking is how slot 0 gets handed
out over a live event, since an unread slot looks empty. It returns a
genuinely empty slot if there is one, and only falls back to a slot whose
window has already passed, logging when it does. Without that fallback the
pool would exhaust and never recover, because the pump does not clear events
once they expire.

---

## Vacations

A vacation is a single event with the `Stop` action: it overrides the weekly
schedule for its window and holds the pump off.

```python
from datetime import datetime

await client.single_events.set_vacation(
    datetime(2026, 8, 10, 0, 0),
    datetime(2026, 8, 17, 0, 0),
)

# ...and afterwards
await client.single_events.clear_vacation()
```

Note the action byte's sense is **the opposite** of the weekly schedule's
`default_action`, where `0x01` means Stop. In a single event, `0x01` is Stop
and `0x02` is Run. This is the pump's own encoding, not a mistake.

---

## Timestamps are local Unix time — and this is invisible if you get it wrong

!!! danger "The failure mode verification cannot catch"

    Single-event timestamps are the **wall clock stamped as though it were
    UTC** — `calendar.timegm(local_fields)` — matching the pump's own RTC,
    which reports bare wall-clock fields with no offset.

    Encoding them as real UTC round-trips **byte-identically**. The write
    settles as accepted, a readback agrees with itself, every test passes, and
    the event opens hours from where it was meant to. Nothing detects it
    except a clock and a running motor.

    This was established by writing an event under this encoding and watching
    the motor start four seconds from the intended wall clock.

`to_pump_time(datetime)` and `from_pump_time(int)` do the conversion. Both
work in naive datetimes deliberately: the pump stores no offset, so attaching
one would invent information.

```python
from alpha_hwr.services.single_event import to_pump_time, from_pump_time

when = datetime(2026, 8, 10, 6, 0)  # 06:00 local, as the user means it
to_pump_time(when)  # what goes on the wire
from_pump_time(...)  # naive, back to the same wall clock
```

Pass naive local datetimes and let the library handle it.

---

## The clock program has to be running

Two conditions that catch people out, both confirmed by watching a window open
with the motor at 0 RPM:

1. **A stopped pump ignores single events entirely.** Same rule as the weekly
   schedule — the run state gates the whole clock program.
2. **Disabling the weekly schedule disables single events too.** They are the
   same program; there is no separate switch.

So a vacation set on a stopped pump does nothing, and neither does one set
while the schedule is off. Check `get_run_state()` first.

### And beware the configuration commit

Every setpoint write is followed by a configuration commit, and that commit
carries the schedule's enabled flag. Older versions of this library sent a
fixed commit blob with that flag set to `0x00`, so **changing any setpoint
silently switched off a live schedule**. If you restored a configuration or
changed a setpoint with an older version, check `schedule list`.

---

## See also

- [verified_writes.md](verified_writes.md) — what a write reports back
- [../protocol/schedules.md](../protocol/schedules.md) — the wire format
- [../protocol/bench_findings.md](../protocol/bench_findings.md) — the
  measurements behind the coupling rules above
