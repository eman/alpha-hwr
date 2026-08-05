# Wire Protocol Format

The Grundfos ALPHA HWR communicates using the **GENI** (Grundfos Equipment Network Interface) protocol encapsulated in Bluetooth Low Energy (BLE) packets.

## GENI Frame Structure

Each packet sent or received over the BLE Characteristic follows this structure:

| Offset | Field | Length | Description |
| :--- | :--- | :--- | :--- |
| 0 | **Start Delimiter** | 1 byte | Marker byte indicating the start of a frame. |
| 1 | **Length** | 1 byte | Length of the remaining packet **excluding** the Start Byte and CRC. (Len = Dest + Src + APDU) |
| 2 | **Destination** | 1 byte | Target address. |
| 3 | **Source** | 1 byte | Sender address. |
| 4...N | **APDU** | Variable | Application Protocol Data Unit (The payload). |
| N+1 | **CRC High** | 1 byte | CRC-16 Checksum (High Byte). |
| N+2 | **CRC Low** | 1 byte | CRC-16 Checksum (Low Byte). |

### Start Delimiter
*   **Request (Client -> Pump)**: `0x27`
*   **Response (Pump -> Client)**: `0x24`

### Addresses
*   **Service/Pump (Dest)**: `0xE7` (Commonly used service ID)
*   **Client (Src)**: `0xF8` (Standard client ID) or `0x0A` (Device/Pump itself in responses)

### CRC Calculation
The checksum is a **CRC-16-CCITT** (Polynomial `0x1021`).
*   **Scope**: Calculated over bytes from `Length` up to the end of `APDU` (excludes Start Delimiter).
*   **Initial Value**: `0xFFFF` (typically).

## APDU Structure

The payload (APDU) determines the command or data being exchanged.

```text
[Class Byte] [Operation Specifier] [Data Payload...]
```

### 1. Class Byte
Defines the category of the command.
*   **Class 3**: Register Operations (Read/Write specific memory addresses).
*   **Class 10 (`0x0A`)**: Data Object Operations (Complex structures, Control, Telemetry).

### 2. Operation Specifier (OpSpec)
A single byte that encodes the **Operation Type** (bits 7-6) and the **Data Length** (bits 5-0).

#### Class 3 OpSpec (Register Info)
Used when requesting register data.
*   **Formula**: `(0x03 << 6) | Length` = `0xC0 | Length`
*   **Example**: For a 3-byte register address, OpSpec = `0xC3` (`11000011`).

#### Class 10 OpSpec (Set/Command)
Used when sending control commands (e.g., Start/Stop).
*   **Formula**: `0x80 | (PayloadLength - 4)`
*   *Note: Class 10 usually consumes 4 bytes for SubID and ObjID headers, so the length bits represent the actual value data length.*

## Class 10 Data Objects

Class 10 is the primary protocol for modern control and telemetry on the ALPHA HWR. There are two distinct layouts depending on whether the frame is a passive notification or a response to an active query.

### 1. Passive Notification Layout (OpSpec 0x0E)

Used for the 10Hz high-frequency telemetry stream.

**Structure:**
```text
[Class=0x0A] [OpSpec=0x0E] [SubID (2B)] [ObjID (2B)] [Value Data...]
```

*   **SubID**: 2 bytes, Big-Endian. Identifies the functional block (e.g., `0x0045` for Motor State).
*   **ObjID**: 2 bytes, Big-Endian. Identifies the specific parameter (e.g., `0x0057`).
*   **Data**: The raw value data starts immediately at offset 10 (after the 4-byte ID header).

### 2. Active Query Response Layout

Used when the client explicitly requests a data object with an INFO query.

**Structure:**
```text
[Class=0x0A] [Length] [ID-A (2B)] [ID-B (2B)] [Value Data...]
```

*   **Length**: byte 5. See below — this is a *length*, not an operation
    specifier.
*   **ID-A, ID-B**: the two 16-bit identifiers the pump answers with. They
    encode the *type* of object, not the address that was requested.
*   **Data**: starts at offset 10.

#### Byte 5 of a response is a length field

Measured across 13 objects and 10 distinct values on real hardware. The top
two bits (the operation code) are always `00`, and the low six bits equal
the payload length exactly:

```
len(frame) == (frame[5] & 0x3F) + 8
frame[1]   == (frame[5] & 0x3F) + 4
```

Both hold without exception.

> Earlier revisions of this document described byte 5 as an OpSpec that
> "varies by data type" — `0x30` for Motor State, `0x2B` for Flow, `0x14`,
> `0x09` and so on. Those values are the payload **sizes** 48, 43, 20 and 9.
>
> This was not merely a naming error. Treating that set as "the register-read
> operation specifiers" and filtering replies against it filtered by
> *length*, which is why the event log — whose entries carry a 20-byte
> payload — had to be exempted from the filter by hand. The filter is gone.

#### Matching a reply to a request

The pump does not echo the address you asked for. It answers with a pair of
identifiers that name the object's **type**, so several distinct sub-ids share
one pair, and the pair is what a reply must be matched on.

These are measured — captured from an ALPHA HWR, identical across two runs:

| Object / Sub range | ID-A | ID-B | What |
| :--- | :--- | :--- | :--- |
| 86 / 5–10 | `0x0001` | `0x2F01` | Operation status request |
| 86 / 13–39 | `0x0001` | `0x2D01` | Setpoint limits |
| 91 / 421 | `0x0003` | `0xD901` | Cycle-time config |
| 91 / 430 | `0x0003` | `0xF402` | Temperature range config |
| 84 / 1 | `0x0000` | `0xDA01` | Schedule overview |
| 84 / 900+ | `0x0000` | `0xDC01` | Single events |
| 84 / 1000–1004 | `0x0000` | `0xDE01` | Schedule layers |
| 93 / 1 | `0x0000` | `0xF802` | Operating statistics |
| 94 / 101 | `0x0001` | `0x4201` | Clock |
| 88 / 10199 | `0x0000` | `0xF301` | Event log metadata |
| 88 / 10200+ | `0x0000` | `0xF402` | Event log entries |
| 88 / 13300–13301 | `0x0003` | `0xE801` | Cycle timestamps |
| 53 / 451–453 | `0x0003` | `0xB201` | Trends: flow, head, temp |
| 53 / 454 | `0x0003` | `0xB301` | Trend: power-on time |

Three rules that fall out of this, each of which cost something to learn:

1.  **The two identifiers are not placed consistently.** Several reads only
    work because matching accepts them swapped — the Object 86 status read
    among them.

2.  **A zero in ID-A is a real value, not a wildcard.** Reading it as one made
    an event log entry (`0x0000, 0xF402`) a valid answer to a temperature
    range read (`0x0003, 0xF402`): they share a type code and differ only in
    the field a wildcard would discard.

3.  **An unmeasured object gets a class match, not a guess.** Inventing an
    identifier for an object nobody has captured would reject the real reply,
    which is worse than matching loosely.

The table lives in `protocol/matcher.py` as `RESPONSE_IDENTIFIERS`, and
`tests/unit/protocol/test_matcher.py` asserts each entry against the actual
captured frame — and against every read it does *not* belong to, so that
matching by type code buys something over a wildcard.

#### Payload contents

*   Most objects carry an array of IEEE 754 big-endian floats.
*   Alarms and warnings carry uint16 codes; `0x0000` means none. See
    [Alarms and Warnings](packet_traces/06_alarms_warnings.md).

> **Note**: in the flow/head response the flow rate sits at float index 6
> (offset 24 into the array), not index 0.

## Data Encoding

*   **Integers**: Big-Endian.
*   **Floats**: IEEE 754 Single Precision (32-bit), Big-Endian.