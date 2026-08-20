# Test Vectors

**This page is generated.** Do not edit it by hand: run

```bash
uv run python scripts/generate_test_vectors.py
```

Every value below is produced by executing the real implementation, so it
cannot disagree with the code. A previous hand-written version specified the
wrong CRC algorithm and decoded `0x46E5B000` as 14710.0 (it is 29400.0);
nothing caught either, because nothing ran it.

## 1. CRC-16/CCITT

| | |
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
| `27 07 E7 F8 02 03 94 95 96 EB 47` | `0xEB47` | Class 2 GET of unit family/type/version |
| `27 07 E7 F8 0A 03 56 00 06 C5 5A` | `0xC55A` | Class 10 GET of Object 86 Sub 6 |
| `27 05 E7 F8 05 C1 4B C3 82` | `0xC382` | INFO query, Class 5 item 0x4B |
| `27 05 E7 F8 0B C1 0F D0 C3` | `0xD0C3` | INFO query, Class 11 item 0x0F |
| `27 05 E7 F8 03 81 06 E5 87` | `0xE587` | Class 3 START |
| `27 05 E7 F8 03 81 05 D5 E4` | `0xD5E4` | Class 3 STOP |

```python
assert calc_crc16(bytes.fromhex("07e7f80203949596")) == 0xEB47
assert calc_crc16(bytes.fromhex("07e7f80a03560006")) == 0xC55A
assert calc_crc16(bytes.fromhex("05e7f805c14b")) == 0xC382
assert calc_crc16(bytes.fromhex("05e7f80bc10f")) == 0xD0C3
assert calc_crc16(bytes.fromhex("05e7f8038106")) == 0xE587
assert calc_crc16(bytes.fromhex("05e7f8038105")) == 0xD5E4
```

## 2. IEEE 754 Big-Endian Float

| Value | Encoded | Round-trips |
| :--- | :--- | :--- |
| `1.5` — The canonical IEEE 754 example | `3F C0 00 00` | `1.5` |
| `14710` — 1.5 m of head, in Pascals | `46 65 D8 00` | `14710` |
| `1650` — The pump's minimum speed, RPM | `44 CE 40 00` | `1650` |
| `3671` — The pump's maximum speed, RPM | `45 65 70 00` | `3671` |
| `0` — Zero | `00 00 00 00` | `0` |
| `-5.5` — Negative | `C0 B0 00 00` | `-5.5` |
| `38.9` — A temperature setpoint, degrees C | `42 1B 99 9A` | `38.9` |

> `0x45657000` is **3671.0**, the pump's maximum speed — not an inert
> placeholder. It appears verbatim in the pump's own limits block, and
> sending it as a setpoint "suffix" writes run-at-full-speed over whatever
> the mode actually held.

## 3. Uint16 Big-Endian

| Value | Encoded |
| :--- | :--- |
| `1000` (`0x03E8`) | `03 E8` |
| `22016` (`0x5600`) — Control SubID | `56 00` |
| `65535` (`0xFFFF`) — Maximum | `FF FF` |

## 4. Uint32 Big-Endian

| Value | Encoded |
| :--- | :--- |
| `5701701` (`0x00570045`) — Motor state register | `00 57 00 45` |
| `1234567890` (`0x499602D2`) | `49 96 02 D2` |
| `380392` (`0x0005CDE8`) — Operating time, seconds | `00 05 CD E8` |

## 5. Frame Building

The opening packets are built from their APDUs and must reproduce
the captured constants byte for byte:

| APDU | Frame | Matches capture |
| :--- | :--- | :--- |
| `02 03 94 95 96` | `27 07 E7 F8 02 03 94 95 96 EB 47` | yes |
| `0A 03 56 00 06` | `27 07 E7 F8 0A 03 56 00 06 C5 5A` | yes |
| `05 C1 4B` | `27 05 E7 F8 05 C1 4B C3 82` | yes |
| `0B C1 0F` | `27 05 E7 F8 0B C1 0F D0 C3` | yes |

### Class 10 object read

| Object / Sub | Frame |
| :--- | :--- |
| 86 / 6 | `27 07 E7 F8 0A 03 56 00 06 C5 5A` |
| 86 / 7 | `27 07 E7 F8 0A 03 56 00 07 D5 7B` |
| 86 / 13 | `27 07 E7 F8 0A 03 56 00 0D 74 31` |
| 84 / 1 | `27 07 E7 F8 0A 03 54 00 01 DB DD` |
| 91 / 421 | `27 07 E7 F8 0A 03 5B 01 A5 31 B3` |
| 91 / 430 | `27 07 E7 F8 0A 03 5B 01 AE 80 D8` |
| 93 / 1 | `27 07 E7 F8 0A 03 5D 00 01 45 4C` |

The Object/Sub pair and the 24-bit register form are two spellings of one
address, not two addressing modes — `build_class10_object_read(0x57, 0x0045)`
and `build_class10_read(0x570045)` emit identical bytes.

### Control frames

| Purpose | Frame |
| :--- | :--- |
| Start (Class 3) | `27 05 E7 F8 03 81 06 E5 87` |
| Stop (Class 3) | `27 05 E7 F8 03 81 05 D5 E4` |
| Mode -> Constant Speed | `27 14 E7 F8 0A 90 56 00 0A 01 2F 01 00 00 07 00 06 02 7F FF FF FF 0C EC` |
| Setpoint 1650 RPM | `27 14 E7 F8 0A 90 56 00 06 01 2F 01 00 00 07 00 00 02 44 CE 40 00 47 63` |

`7F FF FF FF` is NaN, meaning "keep the stored setpoint". A mode change sends
it so that the fused control object does not overwrite the target mode's
value.

## 6. MTU Chunking

Every frame is written in 20-byte chunks. The count is **not** fixed
at two — a two-chunk splitter looks correct on every control packet and
silently truncates the schedule write.

| Frame length | Chunks |
| :--- | :--- |
| 9 bytes | 9 |
| 24 bytes | 20 + 4 |
| 27 bytes | 20 + 7 |
| 43 bytes | 20 + 20 + 3 |
| 59 bytes | 20 + 20 + 19 |

## 7. Frame Parsing

Measured replies, parsed by the real parser:

| Reply | Class | Byte 5 | Payload length |
| :--- | :--- | :--- | :--- |
| `2412f8e70a0e00012f0100000700001b39678ac34fbc` | 10 | `0x0E` | 14 |
| `2415f8e70a110000da0100000a02050005010100000000dd89` | 10 | `0x11` | 17 |
| `2417f8e70a130001420100000c07ea08041019043100020101e229` | 10 | `0x13` | 19 |

**Byte 5 of a response is a length, not an operation specifier.** Its top two
bits are always `00` and its low six bits are the payload length, so both of
these hold for every measured reply:

```
len(frame) == (frame[5] & 0x3F) + 8
frame[1]   == (frame[5] & 0x3F) + 4
```

Reading it as a type code means filtering replies by size — which is what the
old `{0x30, 0x2B, 0x14, 0x09}` "register-read opspec" filter really did.

## 8. Unit Conversions

| Quantity | Wire | API | Conversion |
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
| 1 | 9806.65 | `46 19 3A 9A` |
| 1.5 | 14709.97 | `46 65 D7 E6` |
| 3 | 29419.95 | `46 E5 D7 E6` |
| 10 | 98066.50 | `47 BF 89 40` |

| m³/h | m³/s | Encoded |
| :--- | :--- | :--- |
| 0.5 | 0.00013889 | `39 11 A2 B4` |
| 1 | 0.00027778 | `39 91 A2 B4` |
| 2.5 | 0.00069444 | `3A 36 0B 61` |
