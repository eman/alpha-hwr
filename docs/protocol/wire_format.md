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

### 2. Active Query Response Layout (OpSpecs 0x30, 0x2B, 0x14, 0x09, etc.)

Used when the client explicitly requests a data object using an INFO query.

**Structure:**
```text
[Class=0x0A] [OpSpec] [Seq (2B)] [ID (2B)] [Res (2B)] [DataLen (1B)] [Value Data...]
```

*   **OpSpec**: Varies by data type (e.g., `0x30` for Motor State, `0x2B` for Flow, `0x09` for Alarms/Warnings).
*   **Seq**: 2-byte sequence number.
*   **ID**: 2-byte Identifier.
*   **Res**: 2-byte Reserved field (often `0x0000`).
*   **DataLen**: 1-byte length of the following data array.
*   **Data**: The raw value data starts at offset 13.

**Data Type by OpSpec:**

* **OpSpec 0x30, 0x2B, 0x14**: Data is an array of IEEE 754 floats (big-endian)
* **OpSpec 0x09**: Data is an array of uint16 values (big-endian) for alarm/warning codes

> **CRITICAL**: In query responses (OpSpec 0x2B), the data is often returned as a large array of floats. Flow rate is typically found at index 6 (offset 24 from the start of the array) rather than index 0.

> **NOTE**: OpSpec 0x09 (alarms/warnings) uses uint16 codes instead of floats. A value of 0x0000 means "no alarms/warnings". See [Alarms and Warnings Packet Trace](packet_traces/06_alarms_warnings.md) for details.

## Data Encoding

*   **Integers**: Big-Endian.
*   **Floats**: IEEE 754 Single Precision (32-bit), Big-Endian.