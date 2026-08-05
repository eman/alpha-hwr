# Verified Writes

## The acknowledgement is not the verdict

Ask this pump for 600 RPM. It acknowledges the frame, and stores **1650**.
Ask for 4400 and it acknowledges, and stores **3671**. Both are the ends of
its own limits block; both are perfectly normal behaviour; and in neither case
did anything on the wire say "no".

That is the problem the 0.7.0 write path exists to solve. The old setters
returned `bool`, and that `bool` meant "the frame was accepted" — which is not
the same as "your value is in the pump". A caller could set a speed, get
`True`, and be running at a completely different speed.

```python
result = await client.control.set_setpoint(ControlMode.CONSTANT_SPEED, 600.0)

result.status           # WriteStatus.CLAMPED
result.value            # 1650.0   <- what the pump holds
result.requested_value  # 600.0    <- what you asked for
result.ok               # True
```

`result.value` comes from **reading the pump back** after the write, not from
the request. So does `mode`, `enabled`, `temp_min`, and every other settled
field. The request survives alongside in the `requested_*` fields, which makes
a `WriteResult` self-contained for a log line or a retry decision.

---

## `WriteStatus`

Every operation reaches exactly one of these.

| Status | Meaning | `ok` |
| :--- | :--- | :--- |
| `accepted` | The pump confirmed the value you asked for | ✔ |
| `clamped` | The pump stored a **different** value; it is in `result.value` | ✔ |
| `rejected` | The pump kept its old value, nacked, or a precondition could not be read | ✘ |
| `invalid` | Malformed or out of range — decided before anything reached the wire | ✘ |
| `timeout` | No confirmation within the budget, or the link dropped | ✘ |
| `superseded` | A newer write to the same resource replaced this one while it queued | ✘ |

### Clamping is a success

`result.ok` is `True` for `clamped`. The pump took your command and exercised
judgement; that is a different thing from refusing it. Treating a clamp as a
failure produces retry loops that can never converge, because the second
attempt gets clamped to exactly the same value.

What a caller *should* do is notice:

```python
if result.status is WriteStatus.CLAMPED:
    log.info("pump stored %s, not %s", result.value, result.requested_value)
```

### `invalid` versus `rejected` — the retry signal

This is the distinction that decides whether retrying can possibly help.

- **`invalid`** is a property of your request. Nothing was sent. Retrying it
  unchanged cannot succeed — fix the request.
- **`rejected`** means the pump, or the pump's current state, refused. A later
  attempt might not hit the same condition.

```python
result = await client.control.set_setpoint(ControlMode.CONSTANT_SPEED, 99.0)
result.status   # INVALID: 99 RPM is outside the 500-4500 this mode accepts
result.detail   # says exactly that
```

`detail` is always populated for the non-accepted statuses. Log it.

---

## The verified API

These live on `client.control` and all return `WriteResult`.

| Method | Writes |
| :--- | :--- |
| `set_enabled(enabled)` | Run state (start/stop) |
| `set_mode_verified(mode)` | Control mode only |
| `set_setpoint(mode, value)` | Mode **and** its setpoint |
| `set_temperature_range(min, max, autoadapt=None)` | Mode 27's range |
| `set_cycle_times(on_minutes, off_minutes)` | Mode 25's cycle periods |

And on the client itself:

| Method | Writes |
| :--- | :--- |
| `set_run_state(target)` | Run state and schedule flag, in a safe order |

### `set_setpoint` also switches the mode

It has to. The pump's setpoint object is *fused*: one frame carries the run
state, the control mode and the setpoint, so a setpoint write necessarily
asserts a mode. Rather than hide that, `set_setpoint(mode, value)` takes the
mode explicitly — there is no way to edit a mode's stored value in the
background without selecting it.

### `autoadapt=None` means "keep what you have"

`set_temperature_range` writes three fields in one frame. Passing `None` for
`autoadapt` preserves the pump's current setting; a default value there would
silently change something the caller never mentioned.

---

## The primitive setters still exist

`set_constant_speed()`, `set_constant_pressure()`, `set_constant_flow()`,
`set_proportional_pressure()` and friends return `bool` and do not read back.

```python
ok = await client.control.set_constant_speed(600.0)   # True
# ...and the pump is running at 1650.
```

They are the frame-level building blocks the verified path drives, and they
are still there for callers who genuinely want one frame and no readback. For
anything user-facing, use the verified API — the whole point is that `True`
was never enough information.

---

## Readiness: wait before the first write

Several writes carry fields the caller did not set — the fused setpoint object
carries a run state, the temperature-range struct carries an autoadapt flag,
the commit carries the whole schedule overview. Those fields have to come from
somewhere, and the only correct source is the pump.

So the client reads its state into a cache on connect, and **writes that need
that cache are refused until it is valid**:

```python
async with AlphaHWRClient(address) as client:
    await client.wait_until_ready()          # blocks until the cache is good
    result = await client.control.set_setpoint(ControlMode.CONSTANT_SPEED, 2000.0)
```

`client.is_ready` is the non-blocking form. `wait_until_ready(timeout=30.0)`
returns `False` rather than raising if the pump never becomes readable.

Writing before the cache is valid settles as `rejected` with a `detail`
explaining why — it does not send a frame built from guesses. That guard is
there because the failure mode it prevents is silent: a write assembled from
defaults zeroes a schedule or resets an autoadapt flag, and nothing reports it.

Reads need no readiness gate. Only writes.

---

## One at a time, last write wins

Every write goes through one serialized queue. The pump processes one command
at a time and its replies are not tagged with the request that caused them, so
overlapping writes cannot be attributed correctly.

Two consequences worth knowing:

**A newer write to the same resource supersedes an older one that has not
started yet.** A UI slider that fires ten setpoint writes as it drags does not
queue ten round-trips: the first one is already on the wire and runs to its
own verdict, the middle eight settle as `superseded` without sending
anything, and the last one runs.

```python
first, middle, last = await asyncio.gather(
    client.control.set_setpoint(ControlMode.CONSTANT_SPEED, 1700.0),
    client.control.set_setpoint(ControlMode.CONSTANT_SPEED, 1800.0),
    client.control.set_setpoint(ControlMode.CONSTANT_SPEED, 1900.0),
)
# first  ran (it had already started)
# middle is SUPERSEDED
# last   ran - last write wins
```

**A write already on the wire is never interrupted**, because a half-written
fused object is worse than a stale one. That is why `first` above still gets
a real verdict rather than being cancelled.

Resources are per-target: a setpoint write supersedes only other setpoint
writes *for the same mode*, and never a run-state or schedule write.

---

## When the link drops

Everything pending settles as `timeout`. No write is left awaiting a
confirmation that can no longer arrive, and the cache is invalidated — a
command issued on one connection must not be treated as confirmed by a reading
taken on the next.

---

## Worked example

```python
import asyncio
from alpha_hwr import AlphaHWRClient, ControlMode, WriteStatus


async def main() -> None:
    async with AlphaHWRClient() as client:
        if not await client.wait_until_ready():
            raise SystemExit("pump never became readable")

        result = await client.control.set_setpoint(
            ControlMode.CONSTANT_SPEED, 600.0
        )

        match result.status:
            case WriteStatus.ACCEPTED:
                print(f"running at {result.value:g} RPM")
            case WriteStatus.CLAMPED:
                print(
                    f"asked for {result.requested_value:g}, "
                    f"pump stored {result.value:g} RPM"
                )
            case WriteStatus.INVALID:
                print(f"bad request: {result.detail}")
            case _:
                print(f"{result.status}: {result.detail}")


asyncio.run(main())
```

---

## See also

- [run_state_and_schedules.md](run_state_and_schedules.md) — the run state and
  the schedule, which interact in a way that can stop the pump silently
- [../protocol/units.md](../protocol/units.md) — what units each setpoint uses
  on the wire
- [../protocol/bench_findings.md](../protocol/bench_findings.md) — the
  measurements behind the clamping behaviour
