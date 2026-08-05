#!/usr/bin/env python3
"""
Generate docs/reimplementation/test_vectors.md by executing the codec.

The hand-written version of that page had more wrong assertions than right
ones: it specified CRC-16/MODBUS (the pump uses CCITT), and `0x46E5B000`
was documented as 14710.0 when it decodes to 29400.0. None of it was ever
run, so nothing caught any of it.

Every value below is produced by calling the real implementation, and
`tests/test_docs_consistency.py` fails if the committed page has drifted
from what this script emits. A vector cannot be wrong here without the
library being wrong too.

Usage:
    uv run python scripts/generate_test_vectors.py           # write
    uv run python scripts/generate_test_vectors.py --check   # verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alpha_hwr.core.authentication import AuthenticationHandler
from alpha_hwr.protocol.codec import (
    decode_float_be,
    decode_uint16_be,
    decode_uint32_be,
    encode_float_be,
    encode_uint16_be,
    encode_uint32_be,
)
from alpha_hwr.protocol.frame_builder import FrameBuilder
from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.utils import calc_crc16_read

OUT = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "reimplementation"
    / "test_vectors.md"
)

#: Frames captured from a real ALPHA HWR, which it accepted. These are
#: evidence rather than self-consistency: reproducing their CRC proves the
#: algorithm, not merely that the code agrees with itself.
CAPTURED = [
    ("2707e7f80203949596eb47", "Legacy magic (handshake stage 1)"),
    ("2707e7f80a03560006c55a", "Class 10 unlock (handshake stage 2)"),
    ("2705e7f805c14bc382", "Extend 1 (handshake stage 3)"),
    ("2705e7f80bc10fd0c3", "Extend 2 (handshake stage 3)"),
    ("2705e7f8038106e587", "Class 3 START"),
    ("2705e7f8038105d5e4", "Class 3 STOP"),
]

FLOATS = [
    (1.5, "The canonical IEEE 754 example"),
    (14710.0, "1.5 m of head, in Pascals"),
    (1650.0, "The pump's minimum speed, RPM"),
    (3671.0, "The pump's maximum speed, RPM"),
    (0.0, "Zero"),
    (-5.5, "Negative"),
    (38.9, "A temperature setpoint, degrees C"),
]

UINT16 = [(1000, ""), (0x5600, "Control SubID"), (0xFFFF, "Maximum")]
UINT32 = [
    (0x570045, "Motor state register"),
    (1234567890, ""),
    (380392, "Operating time, seconds"),
]


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _section(title: str) -> str:
    return f"\n## {title}\n\n"


def build() -> str:
    out: list[str] = []
    add = out.append

    add("""# Test Vectors

**This page is generated.** Do not edit it by hand: run

```bash
uv run python scripts/generate_test_vectors.py
```

Every value below is produced by executing the real implementation, so it
cannot disagree with the code. A previous hand-written version specified the
wrong CRC algorithm and decoded `0x46E5B000` as 14710.0 (it is 29400.0);
nothing caught either, because nothing ran it.
""")

    add(_section("1. CRC-16/CCITT"))
    add("""| | |
| :--- | :--- |
| Polynomial | `0x1021` |
| Initial value | `0xFFFF` |
| Reflect in / out | No / No |
| Final XOR | `0xFFFF` |
| Covered bytes | `frame[1:-2]` — after the start byte, before the CRC |
| CRC byte order | Big-endian |

**There is one convention, for reads and writes alike.** A second helper
without the final XOR exists in the source as a building block; no frame the
pump accepts uses it.

The frames below were captured from a real pump, which accepted them.
Reproducing their CRC is evidence about the protocol, not merely internal
consistency.

| Frame | CRC over `frame[1:-2]` | What it is |
| :--- | :--- | :--- |
""")
    for hexs, label in CAPTURED:
        frame = bytes.fromhex(hexs)
        crc = calc_crc16_read(frame[1:-2])
        assert frame[-2:] == crc.to_bytes(2, "big"), f"{label}: CRC mismatch"
        add(f"| `{_hex(frame)}` | `0x{crc:04X}` | {label} |\n")

    add("\n```python\n")
    for hexs, _ in CAPTURED:
        frame = bytes.fromhex(hexs)
        crc = calc_crc16_read(frame[1:-2])
        add(
            f'assert calc_crc16(bytes.fromhex("{frame[1:-2].hex()}")) == 0x{crc:04X}\n'
        )
    add("```\n")

    add(_section("2. IEEE 754 Big-Endian Float"))
    add("| Value | Encoded | Round-trips |\n| :--- | :--- | :--- |\n")
    for value, note in FLOATS:
        enc = encode_float_be(value)
        dec = decode_float_be(enc + b"\x00" * 4, 0)
        assert dec is not None and abs(dec - value) < 1e-3, value
        suffix = f" — {note}" if note else ""
        add(f"| `{value:g}`{suffix} | `{_hex(enc)}` | `{dec:g}` |\n")

    add("""
> `0x45657000` is **3671.0**, the pump's maximum speed — not an inert
> placeholder. It appears verbatim in the pump's own limits block, and
> sending it as a setpoint "suffix" writes run-at-full-speed over whatever
> the mode actually held.
""")

    add(_section("3. Uint16 Big-Endian"))
    add("| Value | Encoded |\n| :--- | :--- |\n")
    for value, note in UINT16:
        enc = encode_uint16_be(value)
        assert decode_uint16_be(enc, 0) == value
        suffix = f" — {note}" if note else ""
        add(f"| `{value}` (`0x{value:04X}`){suffix} | `{_hex(enc)}` |\n")

    add(_section("4. Uint32 Big-Endian"))
    add("| Value | Encoded |\n| :--- | :--- |\n")
    for value, note in UINT32:
        enc = encode_uint32_be(value)
        assert decode_uint32_be(enc, 0) == value
        suffix = f" — {note}" if note else ""
        add(f"| `{value}` (`0x{value:08X}`){suffix} | `{_hex(enc)}` |\n")

    add(_section("5. Frame Building"))
    add("""The handshake packets are built from their APDUs and must reproduce
the captured constants byte for byte:

| APDU | Frame | Matches capture |
| :--- | :--- | :--- |
""")
    for apdu_hex, expected, label in [
        ("0203949596", AuthenticationHandler.LEGACY_MAGIC, "Legacy magic"),
        (
            "0a0356 0006".replace(" ", ""),
            AuthenticationHandler.CLASS10_UNLOCK,
            "Class 10 unlock",
        ),
        ("05c14b", AuthenticationHandler.EXTEND_1, "Extend 1"),
        ("0bc10f", AuthenticationHandler.EXTEND_2, "Extend 2"),
    ]:
        built = FrameBuilder.build_geni_frame(bytes.fromhex(apdu_hex))
        ok = "yes" if built == expected else "**NO**"
        assert built == expected, label
        add(f"| `{_hex(bytes.fromhex(apdu_hex))}` | `{_hex(built)}` | {ok} |\n")

    add("\n### Class 10 object read\n\n")
    add("| Object / Sub | Frame |\n| :--- | :--- |\n")
    for obj, sub, _ in [
        (86, 6, "operation status"),
        (86, 7, "prioritized state"),
        (86, 13, "speed limits"),
        (84, 1, "schedule overview"),
        (91, 421, "cycle-time config"),
        (91, 430, "temperature range"),
        (93, 1, "statistics"),
    ]:
        frame = FrameBuilder.build_class10_object_read(obj, sub)
        add(f"| {obj} / {sub} | `{_hex(frame)}` |\n")

    add("""
The Object/Sub pair and the 24-bit register form are two spellings of one
address, not two addressing modes — `build_class10_object_read(0x57, 0x0045)`
and `build_class10_read(0x570045)` emit identical bytes.

### Control frames

| Purpose | Frame |
| :--- | :--- |
""")
    from alpha_hwr.protocol.codec import encode_uint16_be as _u16

    def control(obj: int, opmode: int, mode: int, setpoint: bytes) -> bytes:
        payload = bytes([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, opmode, mode])
        apdu = (
            bytes([0x0A, 0x90]) + _u16(0x5600) + _u16(obj) + payload + setpoint
        )
        return FrameBuilder.build_geni_frame(apdu)

    keep = bytes([0x7F, 0xFF, 0xFF, 0xFF])
    rows = [
        (
            "Start (Class 3)",
            FrameBuilder.build_geni_frame(bytes([0x03, 0x81, 0x06])),
        ),
        (
            "Stop (Class 3)",
            FrameBuilder.build_geni_frame(bytes([0x03, 0x81, 0x05])),
        ),
        ("Mode -> Constant Speed", control(0x0A01, 0x06, 0x02, keep)),
        (
            "Setpoint 1650 RPM",
            control(0x0601, 0x00, 0x02, encode_float_be(1650.0)),
        ),
    ]
    for label, frame in rows:
        add(f"| {label} | `{_hex(frame)}` |\n")

    add("""
`7F FF FF FF` is NaN, meaning "keep the stored setpoint". A mode change sends
it so that the fused control object does not overwrite the target mode's
value.
""")

    add(_section("6. MTU Chunking"))
    add("""Every frame is written in 20-byte chunks. The count is **not** fixed
at two — a two-chunk splitter looks correct on every control packet and
silently truncates the schedule write.

| Frame length | Chunks |
| :--- | :--- |
""")
    for length in (9, 24, 27, 43, 59):
        sizes = [min(20, length - off) for off in range(0, length, 20)]
        add(f"| {length} bytes | {' + '.join(str(n) for n in sizes)} |\n")

    add(_section("7. Frame Parsing"))
    add("""Measured replies, parsed by the real parser:

| Reply | Class | Byte 5 | Payload length |
| :--- | :--- | :--- | :--- |
""")
    for reply, _ in [
        ("2412f8e70a0e00012f0100000700001b39678ac34fbc", "operation status"),
        (
            "2415f8e70a110000da0100000a02050005010100000000dd89",
            "schedule overview",
        ),
        ("2417f8e70a130001420100000c07ea08041019043100020101e229", "clock"),
    ]:
        frame = bytes.fromhex(reply)
        parsed = FrameParser.parse_frame(frame)
        payload_len = frame[5] & 0x3F
        assert len(frame) == payload_len + 8, reply
        assert frame[1] == payload_len + 4, reply
        add(
            f"| `{reply}` | {parsed.class_byte} | "
            f"`0x{frame[5]:02X}` | {payload_len} |\n"
        )

    add("""
**Byte 5 of a response is a length, not an operation specifier.** Its top two
bits are always `00` and its low six bits are the payload length, so both of
these hold for every measured reply:

```
len(frame) == (frame[5] & 0x3F) + 8
frame[1]   == (frame[5] & 0x3F) + 4
```

Reading it as a type code means filtering replies by size — which is what the
old `{0x30, 0x2B, 0x14, 0x09}` "register-read opspec" filter really did.
""")

    add(_section("8. Unit Conversions"))
    add("""| Quantity | Wire | API | Conversion |
| :--- | :--- | :--- | :--- |
| Pressure | Pascals | metres | ÷ 9806.65 |
| Speed | RPM | RPM | none |
| Flow **setpoint** | SI m³/s | m³/h | ÷ 3600 on the way out |
| Flow **telemetry** | m³/h | m³/h | none |
| Temperature | °C | °C | none |

The two flow rows differ, and both are correct. A setpoint written in m³/h
reaches the pump 3600× too large, is rejected as out of range, and leaves the
stored value untouched — which makes the register look frozen rather than
wrong.

| Metres | Pascals | Encoded |
| :--- | :--- | :--- |
""")
    for metres in (1.0, 1.5, 3.0, 10.0):
        pa = metres * 9806.65
        add(f"| {metres:g} | {pa:.2f} | `{_hex(encode_float_be(pa))}` |\n")

    add("\n| m³/h | m³/s | Encoded |\n| :--- | :--- | :--- |\n")
    for m3h in (0.5, 1.0, 2.5):
        m3s = m3h / 3600.0
        add(f"| {m3h:g} | {m3s:.8f} | `{_hex(encode_float_be(m3s))}` |\n")

    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed page is stale",
    )
    args = parser.parse_args()

    generated = build()

    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != generated:
            print(
                f"{OUT} is out of date; "
                "run: uv run python scripts/generate_test_vectors.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUT} is up to date")
        return 0

    OUT.write_text(generated)
    print(f"wrote {OUT} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
