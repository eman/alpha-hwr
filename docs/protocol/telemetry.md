# Telemetry & Monitoring

The ALPHA HWR streams real-time operational data (Flow, Head, RPM, Power, Temperature) using **Class 10 DataObject notifications**.

Unlike traditional Request/Response polling, the pump automatically "pushes" these updates to the client once the connection is established and authenticated. This allows for high-frequency updates (approx. 10Hz) without saturating the BLE bandwidth with read requests.

## Notification Mechanism

Telemetry arrives as **GENI Response** frames on the main characteristic.

* **Frame Start**: `0x24` (Response/Notification)
* **Class**: `0x0A` (Class 10 DataObject)
* **Source**: `0x0A` (Pump)

### Payload Structure

The payload of a telemetry packet identifies *what* data it contains using a **SubID** and **ObjID**.

```text
[Header...] [Class=0x0A] [Byte5] [ID-A (2B)] [ID-B (2B)] [Data Payload...] [CRC]
```

## Telemetry Objects

The library decodes the following specific objects. Note that a single BLE packet usually contains only **one** of these objects at a time. The client must aggregate them to build a complete state.

### 1. Motor State (Detailed)

Contains electrical and mechanical performance data.

* **SubID**: `0x0045` (69)
* **ObjID**: `0x0057` (87)

| Offset | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| +0 | Float32 | Volts | AC Input Voltage (0 - 300) |
| +8 | Float32 | Amps | Current Draw (0 - 10) |
| +16 | Float32 | Watts | DC Power Consumption (0 - 1000) |
| +20 | Float32 | RPM | Motor Speed (0 - 6000) |
| +24 | Float32 | °C | Converter Temperature (-20 to 120) |

### 2. Flow & Head

Contains hydraulic performance data.

* **SubID**: `0x0122` (290)
* **ObjID**: `0x005D` (93)

**Data Offsets:**

| Field | Passive stream, offset | Active query, offset | Type | Unit |
| :--- | :--- | :--- | :--- | :--- |
| **Flow Rate** | +0 | +24 | Float32 | $m^3/h$ |
| **Head Pressure** | +4 | +28 | Float32 | Meters |

*Conversion Factors:*

* $GPM = m^3/h \times 4.4029$
* $Feet = Meters \times 3.2808$
* $PSI = Meters \times 1.422$

### 3. Temperatures

Contains thermal sensor readings from various points in the system.

* **SubID**: `0x012C` (300)
* **ObjID**: `0x005D` (93)

**Data Offsets:**

| Field | Passive stream, offset | Active query, offset | Type | Unit |
| :--- | :--- | :--- | :--- | :--- |
| **Media Temp** | +0 | +0 | Float32 | °C |
| **PCB Temp** | +4 | +4 | Float32 | °C |
| **Ambient Temp** | +8 | +8 | Float32 | °C |

### 4. Alarms and Warnings

Contains active alarm and warning codes reported by the pump's diagnostic system.

* **SubID**: `0x0000` (0) for Alarms, `0x000B` (11) for Warnings
* **ObjID**: `0x0058` (88)

**Query Method:**

Unlike other telemetry that streams automatically, alarms and warnings must be queried explicitly using Class 10 READ operations:

* **Query Alarms**: Register `0x580000`
* **Query Warnings**: Register `0x58000B`

**Response Format:**

The reply carries an array of uint16 alarm/warning codes rather than floats. Its byte 5 reads `0x09` — that is the **payload length**, not an operation specifier; see [wire_format.md](wire_format.md#byte-5-of-a-response-is-a-length-field).

| Offset | Type | Description |
| :--- | :--- | :--- |
| +0 | uint16[] | Array of active alarm/warning codes (big-endian) |

**Data Interpretation:**

* Each code is a 2-byte unsigned integer in big-endian format
* A value of `0x0000` means "no active alarms/warnings" (normal state)
* Non-zero values indicate specific alarm/warning conditions
* Zero values in the array should be filtered out when parsing
* The array is typically terminated with a trailing zero

**Example Codes:**

```
0x0000 = No alarms/warnings (healthy state)
0x002A = Alarm code 42
0x0007 = Alarm code 7
0x0005 = Warning code 5
```

**Polling Recommendations:**

* Poll every 5-10 seconds for proactive monitoring
* Poll immediately after mode changes or error indicators
* Avoid polling faster than 1 second to prevent overwhelming the pump

**See Also:** [Packet Trace: Alarms and Warnings](packet_traces/06_alarms_warnings.md) for detailed wire format and examples.

### 5. Setpoint RPM

Reserved for setpoint notifications (passive stream only, not actively queried).

* **SubID**: `0x0001` (1)
* **ObjID**: `0x012F` (303)

**Note**: This telemetry object is reserved for potential future use. Currently, RPM setpoints are controlled via Class 10 SET operations rather than passively observed.

---

## Active Polling (Modern Approach)

While the pump supports a high-frequency passive stream, the most reliable way to get a single snapshot of the current state is to use **Class 10 INFO Queries**.

### Modern Snapshot Sequence

1.  **Request Motor State**: Query Register `0x570045`.
2.  **Request Flow/Head**: Query Register `0x5D0122`.
3.  **Request Temperatures**: Query Register `0x5D012C`.

Responses will use the "Active Query Response Layout" described in [Wire Format](wire_format.md).

## Legacy Polling (Class 3)

Older firmware or specific integration scenarios might require active polling instead of passive listening. The device supports **Class 3 Register Reads** for this purpose.

* **Command**: `READ` (OpCode `0x03`)
* **Frame Start**: `0x27` (Request)

### Registers

| Register Address | Name | Data Contained |
| :--- | :--- | :--- |
| `0x5E0004` | **ELECTRICAL** | Voltage (AC/DC), Current, Power, RPM |
| `0x5D0122` | **EXTENDED_FLOW** | Flow, Head |
| `0x5D012C` | **TEMPERATURE** | Media, PCB, Control Box Temps |

*Note: The library's `update_telemetry()` method attempts to use Class 10 streams first, but can fallback to Class 3 polling if the stream is undetected.*
