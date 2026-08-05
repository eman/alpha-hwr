# AutoAdapt Modes — Support Status

The GENI control-mode table includes four AutoAdapt entries. Only three of
them can be addressed on the ALPHA HWR's wire, and none of them has a working
setpoint path in this library.

Earlier revisions of this page had this backwards — mode 5 was described as
usable with a warning, and modes 13/14/15 as "fully supported" with per-mode
SubIDs and setpoint registers that were invented. What follows is what the
code does.

| Mode | Name | Mode can be set? | Setpoint can be set? |
| :--- | :--- | :--- | :--- |
| 5 | AUTO_ADAPT (generic) | **No** — raises `ValueError` | n/a |
| 13 | AUTO_ADAPT_RADIATOR | Yes | **No** |
| 14 | AUTO_ADAPT_UNDERFLOOR | Yes | **No** |
| 15 | AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR | Yes | **No** |
| 26 | PROPORTIONAL_DIFF_PRESSURE | **No** — raises `ValueError` | n/a |

---

## Mode 5: AUTO_ADAPT (generic) — not addressable

**The pump has no wire byte for generic AutoAdapt.** It is absent from
`_MODE_BYTE_MAP` in `services/control.py`, and asking for it raises:

```python
await client.control.set_mode(ControlMode.AUTO_ADAPT)
# ValueError: Control mode 5 is not supported over this protocol;
#             supported modes are [0, 1, 2, 8, 13, 14, 15, 25, 27]
```

### Why raising is the right behaviour

The mode map used to fall through to a default of Constant Speed. A caller
asking for AutoAdapt got **Constant Speed** and a `True` return value: the
pump ran in a mode nobody asked for, and nothing reported it. Raising is
loud; silently running the wrong mode is not.

### If you want adaptive behaviour

Use Mode 1 (`PROPORTIONAL_PRESSURE`), which is genuinely supported:

```python
await client.control.set_proportional_pressure(3.0)  # meters
```

```bash
alpha-hwr control set-proportional 3.0
```

---

## Mode 26: PROPORTIONAL_DIFF_PRESSURE — not addressable

Same reason: no entry in the mode map, so `set_mode()` raises. No SubID for it
was found anywhere in Object 86 (0–65 were probed), and there is no evidence
the ALPHA HWR firmware implements it at all. It is plausibly an ALPHA3/MAGNA3
feature requiring a differential-pressure sensor this pump does not have.

Use Mode 1 instead, as above.

---

## Modes 13, 14, 15 — the mode switches, the setpoint does not

These three have real wire bytes (`0x0D`, `0x0E`, `0x0F`) and switching to
them works:

```python
await client.control.set_mode(ControlMode.AUTO_ADAPT_RADIATOR)   # works
```

What does **not** work is setting their setpoint.

### The deprecated pressure setters

`set_autoadapt_radiator()`, `set_autoadapt_underfloor()` and
`set_autoadapt_combined()` still exist and emit a deprecation warning. They
push a pressure setpoint through a Class 3 command, which is not how these
modes are configured — the library's own docstrings call them "incorrect
pressure-based setpoints". Do not build on them.

### `set_temperature_control()` switches the mode, then gives up

```python
ok = await client.control.set_temperature_control(35.0, 39.0, "radiator")
# ok is False
```

It sets the mode, logs that temperature setpoints for modes 13/14/15 are not
implemented, and returns `False`. **The mode change has already happened by
then** — a `False` return here does not mean nothing changed.

### There are no CLI commands for these modes

`control set-autoadapt`, `set-autoadapt-radiator`, `set-autoadapt-underfloor`
and `set-autoadapt-combined` do not exist and never did. The real list is
`alpha-hwr control --help`.

---

## For ALPHA HWR, use Mode 27

The AutoAdapt family targets space-heating circulators. The ALPHA HWR is a hot
water recirculation pump, and its temperature control is **Mode 27**
(`TEMPERATURE_RANGE_CONTROL`) — fully implemented and bench-verified:

```bash
alpha-hwr control set-temperature --min 35 --max 39
```

---

## Comparison with the modes that work

| Mode | Name | Support | Typical use |
| :--- | :--- | :--- | :--- |
| 0 | CONSTANT_PRESSURE | Full | Fixed differential pressure |
| 1 | PROPORTIONAL_PRESSURE | Full | Flow-dependent pressure |
| 2 | CONSTANT_SPEED | Full | Fixed RPM operation |
| 5 | AUTO_ADAPT | **None** | Raises; no wire byte |
| 8 | CONSTANT_FLOW | Full | Fixed flow rate |
| 13 | AUTO_ADAPT_RADIATOR | Mode only | Setpoint not implemented |
| 14 | AUTO_ADAPT_UNDERFLOOR | Mode only | Setpoint not implemented |
| 15 | AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR | Mode only | Setpoint not implemented |
| 25 | DHW_ON_OFF_CONTROL | Full | Cycle-time control |
| 26 | PROPORTIONAL_DIFF_PRESSURE | **None** | Raises; not in firmware |
| 27 | TEMPERATURE_RANGE_CONTROL | Full | **The HWR mode** |

---

## Related Documentation

- [control_modes.md](control_modes.md) — the modes that work, and their units
- [control.md](control.md) — how a mode change is framed on the wire
- [units.md](units.md) — setpoint units, per mode
- [bench_findings.md](bench_findings.md) — what was measured on hardware
- [CLI Guide](../guides/cli_guide.md) — command-line usage
