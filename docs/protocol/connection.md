# Connection

To control the ALPHA HWR pump, a client bonds over BLE, subscribes to
notifications, and then reads and writes GENIbus frames. That is the whole
sequence.

> **Correction, 2026-08-18.** This document used to say the device "requires an
> application-layer handshake to 'unlock' control capabilities and
> high-frequency telemetry", and described the four packets below as that
> handshake. **Neither claim is supported by any capture in this repository.**
>
> The packets decode as ordinary reads — two GETs and two INFO queries — under
> the GENIbus APDU rule that the second byte is `0booLLLLLL`, operation in the
> top two bits and payload length in the low six. `0x03` is a GET with a 3-byte
> payload, not a SET, and the "unlock code" was a length field misparsed. Reads
> cannot change device state, so an unlock was never something these bytes could
> perform.
>
> A separate client then ran ten connection cycles without sending any of them —
> including two with the BLE bond cleared and re-paired, and five across pump
> power cycles. All ten read every Class 7 device-info string and reached full
> readiness; nine accepted Class 3 START and STOP commands with the motor
> confirmed running. Across 1,019 captured frames there were no Class 2, Class 5
> or Class 11 frames at all.
>
> `bench_findings.md`, this repository's record of measured rather than inferred
> behaviour, has never said anything about a handshake requirement. The claim
> entered in the initial documentation commit, hedged as "may ignore" and "may
> return ... or fail", which is not how an observation gets written down.
>
> **Update, 2026-08-20.** The client no longer sends them. Verified on the
> bench: a bare connect-and-subscribe link, with none of the four packets
> written, answered all five Class 7 string reads, every Class 10 object read
> this client makes, and the three telemetry registers. The 750 ms of
> inter-stage delays went with them — they were transcribed from this client's
> own `sleep()` calls and then written up as pump timing requirements.
>
> The packets are still documented below, and kept as constants in
> `alpha_hwr.core.authentication`, because they are real captures and make
> good frame-assembly vectors. See esphome-alpha-hwr issue #174 for the decode
> and the captures.

## 1. BLE Connection

### Advertising
The pump advertises with the Local Name **`ALPHA_<SERIAL_NUMBER>`** (e.g., `ALPHA_0000479`).

**Important**: The pump advertises its BLE name and manufacturer ID in the advertisement, but NOT the GENI service UUID. The GENI Service UUID is only available in the GATT service table after connection.

*   **Device Name**: `ALPHA_<SERIAL>` (advertised, use this to find pump)
*   **GENI Service UUID**: `0000fdd0-0000-1000-8000-00805f9b34fb` (discovered after connecting, NOT in advertisement)
*   **Company ID**: `0000fe5d-0000-1000-8000-00805f9b34fb` (Grundfos manufacturer ID, in service data)

### Characteristic
All communication (commands and telemetry) happens over a single GATT Characteristic:
*   **GENI Characteristic**: `859cffd1-036e-432a-aa28-1a0085b87ba9`
*   **Properties**: `Write`, `Notify`

### Pairing
The device requires **Pairing/Bonding** for normal use.
*   **Level**: `Just Works` (No PIN usually required, though some models might prompt).
*   **Requirement**: Bonding is recommended. While some commands might work without it, telemetry, control, stable Schedule downloading (HCI layer), and consistent reconnection are much more reliable after bonding.

## 2. Opening Reads (optional)

After connecting and subscribing to notifications, this client sends four
frames. They are reads, their replies are not consumed, and a pump reaches full
readiness and accepts control commands without them. They are retained here as a
record of what this client does, not as a requirement.

### Sequence

The client should send these packets in bursts to ensure the device receives them despite any radio interference or sleep states.

#### Step A: Class 2 identity read
A GET of items 148, 149 and 150 — `unit_family`, `unit_type`, `unit_version`.
The ALPHA HWR answers `52 / 7 / 2`. This client sends it 3 times, ~50ms apart;
one send is sufficient, since the reply is the same every time.

**Packet**: `27 07 E7 F8 02 03 94 95 96 EB 47`

| Byte | Value | Description |
| :--- | :--- | :--- |
| 0 | `0x27` | Frame Start |
| 1 | `0x07` | Length (Dest + Src + Payload) |
| 2 | `0xE7` | Dest (Service) |
| 3 | `0xF8` | Src (Client) |
| 4 | `0x02` | Class: 2 |
| 5 | `0x03` | OpSpec: 0x03 (Length 3) |
| 6-8 | `94 95 96` | Payload (Capabilities/Family Query) |
| 9-10 | `EB 47` | CRC-16 |

#### Step B: Class 10 operation-status read
A GET of Object 86, Sub 6 — the operation-status object, which answers with the
control mode, operation mode and current setpoint. This client sends it 5 times,
~50ms apart. It was described here as "the primary unlock command for modern HWR
firmware"; it is a read, and the same object is polled again in normal
operation.

**Packet**: `27 07 E7 F8 0A 03 56 00 06 C5 5A`

| Byte | Value | Description |
| :--- | :--- | :--- |
| 0 | `0x27` | Frame Start |
| 1 | `0x07` | Length |
| 2 | `0xE7` | Dest |
| 3 | `0xF8` | Src |
| 4 | `0x0A` | Class: 10 (DataObject) |
| 5 | `0x03` | OpSpec: 0x03 (Length 3) |
| 6 | `0x56` | Object 86 |
| 7-8 | `00 06` | Sub 6 |
| 9-10 | `C5 5A` | CRC-16 |

#### Step C: Two INFO queries
INFO asks for a data item's scaling metadata; it reads nothing and changes
nothing, which is why "Authorization Extend" was never an accurate name. The
pump answers both with a one-byte INFO head meaning "unscaled". Sent once each,
~100ms apart.

1.  **Packet 1**: `27 05 E7 F8 05 C1 4B C3 82`
2.  **Packet 2**: `27 05 E7 F8 0B C1 0F D0 C3`

## 3. Keep-Alive

The pump does not require a strict keep-alive packet if telemetry is streaming. However, if the connection goes idle, the device may disconnect. The library implementation relies on the constant stream of Class 10 telemetry notifications to verify the connection is alive.