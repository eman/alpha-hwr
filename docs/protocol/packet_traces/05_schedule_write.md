# Packet Trace: Schedule Write

Writing a weekly schedule layer is the largest single write this protocol
does. It exercises three things nothing else does: a 59-byte frame, three-way
MTU splitting, and a configuration commit that must not be a constant.

## Overview

1. **42-byte payload** — 7 days × 6 bytes, always the whole layer.
2. **Three BLE writes** — 20 + 20 + 19 bytes. Not two.
3. **Class 10 SET**, OpSpec `0xB3`, Object 84, SubID `1000 + layer`.
4. **A commit afterwards**, built from the pump's current overview.

---

## 1. Schedule data structure

A layer is 7 days, Monday first, 6 bytes each — 42 bytes, always sent whole.
There is no partial update: to change one day you read the layer, edit that
day's six bytes, and write all 42 back.

**Day format (6 bytes):**
```
[Enabled] [Action] [Start-H] [Start-M] [End-H] [End-M]
```
- **Enabled**: `0x01` (yes) or `0x00` (no)
- **Action**: `0x01` (start/run) or `0x00` (stop)
- **Times**: hours 0–23, minutes 0–59, as plain bytes

Times are hour and minute bytes. They are **not** minutes-since-midnight;
an implementation that packs them that way writes garbage the pump accepts.

### Example: Monday 06:30–08:30, other days disabled

```
01 01 06 1E 08 1E     Mon   enabled, run, 06:30 → 08:30
00 00 00 00 00 00     Tue
00 00 00 00 00 00     Wed
00 00 00 00 00 00     Thu
00 00 00 00 00 00     Fri
00 00 00 00 00 00     Sat
00 00 00 00 00 00     Sun
```

`0x1E` is 30 minutes.

---

## 2. Build the command

**Target:** Object 84 (`0x54`), SubID `1000 + layer` (layer 0 → `0x03E8`).

**APDU:**

```
[0x0A]              Class 10
[0xB3]              OpSpec: SET, long payload
[0x54]              Object 84
[SubH][SubL]        SubID, big-endian
[0x00]              Reserved
[0xDE][0x01][0x00]  Type 222 header
[0x00][0x2A]        Size: 42
[42 bytes]          The layer
```

**Full frame (59 bytes)** for the example above, layer 0:

| Section | Bytes | Value |
| :--- | :--- | :--- |
| Header | 0–3 | `27 37 E7 F8` |
| APDU head | 4–5 | `0A B3` |
| Object / SubID | 6–8 | `54 03 E8` |
| Reserved | 9 | `00` |
| Type / size | 10–14 | `DE 01 00 00 2A` |
| Data | 15–56 | `01 01 06 1E 08 1E 00 …` |
| CRC | 57–58 | `E6 1E` |

Note the length byte is `0x37` (55), not `0x3B` (59). It is **not** the frame
length: it counts the bytes between itself and the CRC — service ID, source
address and the 53-byte APDU. Total frame = length + 4.

```
27 37 E7 F8 0A B3 54 03 E8 00 DE 01 00 00 2A 01 01 06 1E 08 1E 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 E6 1E
```

---

## 3. BLE packet splitting

59 bytes does not fit the 20-byte MTU. Split into **as many chunks as it
needs** — here, three:

### Chunk 1 (bytes 0–19)
```
27 37 E7 F8 0A B3 54 03 E8 00 DE 01 00 00 2A 01 01 06 1E 08
```

### Chunk 2 (bytes 20–39)
```
1E 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

### Chunk 3 (bytes 40–58)
```
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 E6 1E
```

Pace roughly 50 ms between writes.

!!! danger "Two-chunk splitting silently truncates this frame"

    A splitter written as "first 20 bytes, then the rest" looks correct on
    every 24-byte control packet and fails here: the second "chunk" is 39
    bytes, which exceeds the MTU. That shipped in this library, and the
    schedule write was the only casualty — everything else was small enough
    to hide it. Loop over the frame in 20-byte slices; do not special-case
    two.

---

## 4. Commit

The write does not persist on its own. A configuration commit follows, and it
carries the pump's whole `ClockProgramOverview` — including the schedule's own
enabled flag at byte 4.

**Read Object 84 Sub 1, modify only what you mean to change, write it back.**
A hardcoded commit blob with `0x00` in byte 4 disables the schedule you just
wrote. If the overview cannot be read, send no commit: a lost flush is
recoverable, a fabricated schedule state is not.

See [04_set_mode.md](04_set_mode.md#then-the-configuration-commit) for the
commit frame.

---

## 5. Response

The pump acknowledges with a short Class 10 frame, opspec `0x01` or `0x81`:

```
24 06 F8 E7 0A 01 00 00
```

It does not echo the schedule back. An implementation waiting for a 42-byte
echo waits forever.

---

## 6. Common pitfalls

1. **Assuming two chunks.** Three are needed here. See above.
2. **No pacing.** Chunks sent back to back overflow the pump's buffer.
3. **Length byte.** It describes the whole frame, not the chunk — every chunk
   after the first is raw continuation bytes with no header of its own.
4. **CRC.** Computed over `frame[1:-2]` of the assembled 59 bytes, before
   splitting. CCITT `0x1021`, init `0xFFFF`, final XOR `0xFFFF`.
5. **Forgetting the commit**, or sending a fixed one.
6. **A schedule over a stopped pump.** With the pump stopped and the schedule
   enabled, every window opens with the motor idle and no fault is reported.
   The schedule alone does not start the pump.

---

## 7. Verification

Read the layer back:

```
27 07 E7 F8 0A 03 54 03 E8 [CRC]
```

The reply should contain the same 42 bytes. Verify against what you sent —
this write has no clamping behaviour, so a mismatch is a real failure rather
than the pump exercising judgement.
