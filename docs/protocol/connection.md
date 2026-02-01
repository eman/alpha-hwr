# Connection & Authentication

To control the ALPHA HWR pump, a client must follow a specific connection sequence. Simply connecting via BLE is not enough; the device requires an application-layer handshake to "unlock" control capabilities and high-frequency telemetry.

## 1. BLE Connection

### Advertising
The pump advertises with the Local Name `Grundfos` or `HWR`.
*   **Service UUID**: `0000fdd0-0000-1000-8000-00805f9b34fb` (GENI Service)

### Characteristic
All communication (commands and telemetry) happens over a single GATT Characteristic:
*   **GENI Characteristic**: `859cffd1-036e-432a-aa28-1a0085b87ba9`
*   **Properties**: `Write`, `Notify`

### Pairing
The device typically requests **Pairing/Bonding** upon connection.
*   **Level**: `Just Works` (No PIN usually required, though some models might prompt).
*   **Requirement**: Bonding is recommended. While some commands might work without it, stable Schedule downloading (HCI layer) and consistent reconnection often rely on a bonded state.

## 2. Authentication Handshake ("Unlock")

After connecting and subscribing to notifications, the client **must** send a specific sequence of "Magic Packets". Without this, the pump may ignore control commands (Start/Stop/Set Mode) and will only stream basic or empty telemetry.

This handshake appears to support both legacy GENI implementations and the newer Class 10 DataObject protocol.

### Sequence

The client should send these packets in bursts to ensure the device receives them despite any radio interference or sleep states.

#### Step A: Legacy Magic Packet (Burst)
Send this packet 3 times with a small delay (~50ms) between writes.

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

#### Step B: Class 10 Unlock Packet (Burst)
Send this packet 5 times with a small delay (~50ms) between writes. This appears to be the primary unlock command for modern HWR firmware.

**Packet**: `27 07 E7 F8 0A 03 56 00 06 C5 5A`

| Byte | Value | Description |
| :--- | :--- | :--- |
| 0 | `0x27` | Frame Start |
| 1 | `0x07` | Length |
| 2 | `0xE7` | Dest |
| 3 | `0xF8` | Src |
| 4 | `0x0A` | Class: 10 (DataObject) |
| 5 | `0x03` | OpSpec: 0x03 (Length 3) |
| 6-7 | `56 00` | SubID (Operation/Unlock) |
| 8 | `0x06` | ObjID (Partial/Short) |
| 9-10 | `C5 5A` | CRC-16 |

#### Step C: Authorization Extend (Sequence)
Send these two packets once each, with a small delay (~100ms) in between.

1.  **Packet 1**: `27 05 E7 F8 05 C1 4B C3 82`
2.  **Packet 2**: `27 05 E7 F8 0B C1 0F D0 C3`

## 3. Keep-Alive

The pump does not require a strict keep-alive packet if telemetry is streaming. However, if the connection goes idle, the device may disconnect. The library implementation relies on the constant stream of Class 10 telemetry notifications to verify the connection is alive.