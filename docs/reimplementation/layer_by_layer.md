# Layer-by-Layer Implementation Guide

This guide walks through implementing the ALPHA HWR protocol step-by-step, from lowest to highest layer. Follow this order to build a working implementation incrementally.

## Table of Contents

1. [Layer 0: Prerequisites](#layer-0-prerequisites)
2. [Layer 1: BLE Transport](#layer-1-ble-transport)
3. [Layer 2: Protocol Codec](#layer-2-protocol-codec)
4. [Layer 3: Frame Building & Parsing](#layer-3-frame-building-parsing)
5. [Layer 4: Authentication](#layer-4-authentication)
6. [Layer 5: Session Management](#layer-5-session-management)
7. [Layer 6: Services](#layer-6-services)
8. [Layer 7: Client Facade](#layer-7-client-facade)
9. [Testing Strategy](#testing-strategy)

---

## Layer 0: Prerequisites

Before starting implementation, ensure you have:

### Required Knowledge
- **BLE Basics**: GATT services, characteristics, notifications
- **Binary Data**: Byte arrays, endianness, bit manipulation
- **Async Programming**: Your language's async/await or callback patterns
- **CRC Checksums**: CRC-16/CCITT calculation

### Development Tools
- BLE debugging tool (nRF Connect, LightBlue, etc.)
- Hex editor for inspecting packets
- ALPHA HWR pump for testing
- BLE-capable development machine

## Reference Materials

- [Test Vectors](test_vectors.md) - Validation data
- [Common Pitfalls](common_pitfalls.md) - Known issues
- [Architecture](architecture.md) - System design
- [Packet Traces](../protocol/packet_traces/01_connection.md) - Real examples
- Python Reference: `src/alpha_hwr/` - Complete working implementation

Good luck with your implementation!

---

<a name="testing-strategy"></a>
## Testing Strategy

For details on the testing methodology used in this project, see [TESTING_STRATEGY.md](../TESTING_STRATEGY.md).

## Layer 1: BLE Transport

**Goal**: Establish BLE connection and send/receive raw bytes.

### 1.1 Discover Pump

The pump advertises as `ALPHA_<serial>` via BLE.

**Implementation**:
```python
# Pseudocode - adapt to your BLE library
import ble_library


async def discover_pump(serial_number=None):
    """
    Scan for ALPHA HWR pumps.

    Returns device address/object.
    """
    devices = await ble_library.scan(timeout=10.0)

    for device in devices:
        if device.name and device.name.startswith("ALPHA"):
            if serial_number is None or serial_number in device.name:
                return device

    raise Exception("Pump not found")
```


---

### 1.2 Connect to Pump

Connect via BLE and discover the GENI service.

**GENI GATT layout** — one service, **one characteristic**, used for both
directions:

```python
GENI_SERVICE_UUID = "0000fdd0-0000-1000-8000-00805f9b34fb"
GENI_CHAR_UUID = "859cffd1-036e-432a-aa28-1a0085b87ba9"
```

> Earlier revisions of this guide described a two-characteristic topology
> (`0000fdd1` for writes, `0000fdd2` for notifications). **Neither
> characteristic exists on this device.** You write to `859cffd1…` and you
> subscribe to notifications on the same handle. A port looking for a
> separate RX characteristic fails at service discovery.

**Implementation**:
```python
async def connect_to_pump(device_address):
    """Connect to the pump and resolve the single GENI characteristic."""
    client = await ble_library.connect(device_address)
    await client.discover_services()

    service = client.get_service(GENI_SERVICE_UUID)
    char = service.get_characteristic(GENI_CHAR_UUID)

    return (client, char)
```

Note also that **the pump drops an idle connection at about 1.8 seconds**
unless it is bonded. If your connection dies almost immediately and always at
the same moment, the problem is pairing, not your frames.


---

### 1.3 Setup Notifications

Subscribe on the same characteristic you write to.

**Implementation**:
```python
response_queue = []


def notification_handler(sender, data):
    """Handle incoming notifications from pump."""
    response_queue.append(data)


async def enable_notifications(client):
    """Enable BLE notifications on the GENI characteristic."""
    await client.start_notify(GENI_CHAR_UUID, notification_handler)
```


---

### 1.4 Send/Receive Raw Bytes

Implement basic send/receive functions.

**Implementation**:
```python
async def send_packet(client, data: bytes):
    """Send bytes to the pump, in 20-byte chunks."""
    for i in range(0, len(data), 20):
        await client.write_gatt_char(
            GENI_CHAR_UUID, data[i : i + 20], response=False
        )
        await asyncio.sleep(0.05)  # the pump needs the pacing


async def receive_packet(timeout=5.0):
    """Wait for response from pump."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        if response_queue:
            return response_queue.pop(0)
        await asyncio.sleep(0.01)

    raise TimeoutError("No response from pump")
```


---

## Layer 2: Protocol Codec

**Goal**: Encode and decode primitive data types (floats, integers).

### 2.1 CRC-16/CCITT

Implement CRC calculation for packet integrity.

**Algorithm**:
```python
def calc_crc16(data: bytes) -> int:
    """
    CRC-16/CCITT-FALSE.

    Polynomial: 0x1021
    Initial value: 0xFFFF
    Final XOR: 0xFFFF
    Reflect input/output: False

    Computed over frame[1:-2] - everything after the start byte, up to
    but not including the two CRC bytes. The CRC itself is big-endian.
    """
    crc = 0xFFFF

    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    return crc ^ 0xFFFF
```

> Earlier revisions of this guide specified CRC-16/MODBUS here. That was
> wrong, and it is the single most expensive error a port can inherit - no
> frame is accepted and no response arrives, so there is nothing to debug
> against. See [common_pitfalls.md](common_pitfalls.md#2-crc-calculation).

**Test Vectors** - captured frames the pump accepted:
```python
assert calc_crc16(bytes.fromhex("05e7f805c14b")) == 0xC382  # Extend 1
assert calc_crc16(bytes.fromhex("07e7f80203949596")) == 0xEB47  # Legacy magic
assert calc_crc16(bytes.fromhex("05e7f8038106")) == 0xE587  # Class 3 START
```


---

### 2.2 IEEE 754 Float Encoding

Encode floats as big-endian IEEE 754.

**Implementation**:
```python
import struct


def encode_float_be(value: float) -> bytes:
    """
    Encode float as big-endian IEEE 754 (4 bytes).

    Example:
        1.5 → [0x3F, 0xC0, 0x00, 0x00]
    """
    return struct.pack(">f", value)  # ">f" = big-endian float


def decode_float_be(data: bytes) -> float:
    """
    Decode big-endian IEEE 754 float.

    Example:
        [0x3F, 0xC0, 0x00, 0x00] → 1.5
    """
    return struct.unpack(">f", data)[0]
```

**Test Vectors**:
```python
assert encode_float_be(1.5) == bytes([0x3F, 0xC0, 0x00, 0x00])
assert encode_float_be(14710.0) == bytes([0x46, 0x65, 0xB0, 0x00])
assert decode_float_be(bytes([0x3F, 0xC0, 0x00, 0x00])) == 1.5
assert abs(decode_float_be(bytes([0x46, 0x65, 0xB0, 0x00])) - 14710.0) < 0.1
```


---

### 2.3 Integer Encoding

Encode integers as big-endian.

**Implementation**:
```python
def encode_uint16_be(value: int) -> bytes:
    """Encode uint16 as big-endian (2 bytes)."""
    return struct.pack(">H", value)


def encode_uint32_be(value: int) -> bytes:
    """Encode uint32 as big-endian (4 bytes)."""
    return struct.pack(">I", value)


def decode_uint16_be(data: bytes) -> int:
    """Decode big-endian uint16."""
    return struct.unpack(">H", data)[0]


def decode_uint32_be(data: bytes) -> int:
    """Decode big-endian uint32."""
    return struct.unpack(">I", data)[0]
```

**Test Vectors**:
```python
assert encode_uint16_be(0x5600) == bytes([0x56, 0x00])
assert encode_uint16_be(0x0601) == bytes([0x06, 0x01])
assert decode_uint16_be(bytes([0x56, 0x00])) == 0x5600
```


---

## Layer 3: Frame Building & Parsing

**Goal**: Construct and parse GENI protocol frames.

### 3.1 Frame Structure

All GENI frames follow this format:

```
[Start] [Length] [ServiceID-H] [ServiceID-L] [APDU...] [CRC-H] [CRC-L]
```

**Constants**:
```python
FRAME_START_REQUEST = 0x27
FRAME_START_RESPONSE = 0x24
SERVICE_ID_HIGH = 0xE7
SERVICE_ID_LOW_SOURCE = 0xF8
CLASS_10 = 0x0A
```

---

### 3.2 Build INFO Command (Read Telemetry)

INFO commands request data from the pump.

**Implementation**:
```python
def build_info_command(class_byte, sub_id, obj_id):
    """
    Build Class 10 INFO command.

    Frame: [27] [Length] [E7] [F8] [0A] [OpSpec] [Sub-H] [Sub-L] [Obj-H] [Obj-L] [CRC-H] [CRC-L]

    Args:
        class_byte: Always 0x0A for Class 10
        sub_id: Subsystem ID (e.g., 0x0045 for motor)
        obj_id: Object ID (e.g., 0x0057 for motor state)

    Returns:
        Complete frame (bytes)
    """
    # Build APDU
    apdu = []
    apdu.append(CLASS_10)
    apdu.append(0x00)  # OpSpec: INFO command, 0 bytes data
    apdu.append((sub_id >> 8) & 0xFF)  # Sub ID high
    apdu.append(sub_id & 0xFF)  # Sub ID low
    apdu.append((obj_id >> 8) & 0xFF)  # Obj ID high
    apdu.append(obj_id & 0xFF)  # Obj ID low

    # Build header
    length = 2 + len(apdu)  # ServiceID (2 bytes) + APDU
    frame = []
    frame.append(FRAME_START_REQUEST)
    frame.append(length)
    frame.append(SERVICE_ID_HIGH)
    frame.append(SERVICE_ID_LOW_SOURCE)
    frame.extend(apdu)

    # Calculate CRC over bytes from Length to end of APDU
    crc_data = bytes(frame[1:])  # Exclude start byte
    crc = calc_crc16(crc_data)

    # Append CRC (big-endian)
    frame.append((crc >> 8) & 0xFF)  # CRC high
    frame.append(crc & 0xFF)  # CRC low

    return bytes(frame)
```

**Test**:
```python
# Request motor state (Sub 0x0045, Obj 0x0057)
packet = build_info_command(0x0A, 0x0045, 0x0057)
assert packet[0] == 0x27  # Start byte
assert packet[4] == 0x0A  # Class 10
assert len(packet) == 12  # Header (4) + APDU (6) + CRC (2)
```


---

### 3.3 Build SET Command (Write Data)

SET commands write data to the pump (control, configuration).

**Implementation**:
```python
def build_set_command(sub_id, obj_id, data: bytes):
    """
    Build Class 10 SET command.
    
    Frame: [27] [Length] [E7] [F8] [0A] [OpSpec] [Sub-H] [Sub-L] [Obj-H] [Obj-L] [Data...] [CRC-H] [CRC-L]
    
    Args:
        sub_id: Subsystem ID (e.g., 0x5600 for control)
        obj_id: Object ID (e.g., 0x0601 for setpoint)
        data: Payload bytes (e.g., encoded float)
    
    Returns:
        Complete frame (bytes)
    """
    # Build APDU. The OpSpec's low bits count the SubID and ObjID bytes
    # as well as the payload - 4 + len(data), not len(data). A 12-byte
    # control payload gives 0x80 | 16 = 0x90, which is what the pump sees
    # on every real control frame.
    opspec = 0x80 | (4 + len(data))
    apdu = []
    apdu.append(CLASS_10)
    apdu.append(opspec)
    apdu.append((sub_id >> 8) & 0xFF)
    apdu.append(sub_id & 0xFF)
    apdu.append((obj_id >> 8) & 0xFF)
    apdu.append(obj_id & 0xFF)
    apdu.extend(data)
    
    # Build header
    length = 2 + len(apdu)
    frame = []
    frame.append(FRAME_START_REQUEST)
    frame.append(length)
    frame.append(SERVICE_ID_HIGH)
    frame.append(SERVICE_ID_LOW_SOURCE)
    frame.extend(apdu)
    
    # Calculate CRC
    crc_data = bytes(frame[1:])
    crc = calc_crc16(crc_data)
    frame.append((crc >> 8) & 0xFF)
    frame.append(crc & 0xFF)
    
    return bytes(frame)
```

**Test** — set Constant Pressure to 1.5 m (14710 Pa) through the fused
control object. The payload is 12 bytes, not 4: the object carries the run
state and the mode alongside the setpoint, and there is no way to write one
without asserting all three.

```python
payload = bytes(
    [
        0x2F,
        0x01,
        0x00,
        0x00,
        0x07,  # fixed prefix
        0x00,  # control_source (ignored)
        0x00,  # operation_mode: AUTO
        0x00,  # control mode: CONSTANT_PRESSURE
    ]
) + encode_float_be(14710.0)

packet = build_set_command(0x5600, 0x0601, payload)

assert packet[0] == 0x27
assert packet[5] == 0x90  # SET (0x80) | 16 (4 id bytes + 12 payload)
assert len(packet) == 24  # header 4 + APDU 18 + CRC 2
assert packet.hex() == "2714e7f80a90560006012f010000070000004665d80032a7"
```

Then send the configuration commit — see
[common_pitfalls.md](common_pitfalls.md) — and read Object 86 Sub 7 back,
because the pump acks setpoints it is about to clamp.


---

### 3.4 Parse Response Frame

Parse responses from the pump.

**Implementation**:
```python
def parse_frame(data: bytes):
    """
    Parse GENI response frame.

    Frame: [24] [Length] [E7] [0A] [Class] [OpSpec] [Sub-H] [Sub-L] [Obj-H] [Obj-L] [Payload...] [CRC-H] [CRC-L]

    Returns:
        dict with keys: start, length, service_id, source, class_byte, opspec,
                        sub_id, obj_id, payload, crc
    """
    if len(data) < 8:
        raise ValueError("Frame too short")

    # Verify start byte
    start = data[0]
    if start != FRAME_START_RESPONSE:
        raise ValueError(f"Invalid start byte: {start:#x}")

    # Parse header
    length = data[1]
    service_id_h = data[2]
    source = data[3]

    # Verify CRC
    crc_received = (data[-2] << 8) | data[-1]
    crc_calculated = calc_crc16(data[1:-2])
    if crc_received != crc_calculated:
        raise ValueError("CRC mismatch")

    # Parse APDU (Class 10)
    class_byte = data[4]
    opspec = data[5]
    sub_id = (data[6] << 8) | data[7]
    obj_id = (data[8] << 8) | data[9]

    # Extract payload (between obj_id and CRC)
    payload = data[10:-2]

    return {
        "start": start,
        "length": length,
        "service_id": (service_id_h << 8) | source,
        "source": source,
        "class_byte": class_byte,
        "opspec": opspec,
        "sub_id": sub_id,
        "obj_id": obj_id,
        "payload": payload,
        "crc": crc_received,
    }
```

**Test**:
```python
# Example response with motor speed = 2500.0 RPM
response = bytes(
    [
        0x24,  # Start
        0x08,  # Length
        0xE7,
        0x0A,  # Service ID
        0x0A,  # Class 10
        0x00,  # OpSpec
        0x00,
        0x45,  # Sub 0x0045 (motor)
        0x00,
        0x57,  # Obj 0x0057 (state)
        0x45,
        0x1C,
        0x40,
        0x00,  # Speed = 2500.0
        0x12,
        0x34,  # CRC (example)
    ]
)
# Note: CRC would need to be correct for real test

frame = parse_frame(response)
assert frame["class_byte"] == 0x0A
assert frame["sub_id"] == 0x0045
assert frame["obj_id"] == 0x0057
assert len(frame["payload"]) == 4
```


---

## Layer 4: Opening reads (optional — you can skip this layer)

> **Corrected 2026-08-18.** These four frames are **not** an authentication
> handshake and are **not** required. They decode as GENIbus reads — two GETs
> and two INFO queries — and ten connection cycles omitting them entirely,
> including two with the BLE bond cleared and re-paired, reached full readiness
> and accepted control commands. If you are writing a new client, **skip this
> step.** See esphome-alpha-hwr issue #174.

**Goal**: match what the reference client sends, if you want to.

### 4.1 The sequence this client sends

1. Class 2 identity read × 3
2. Class 10 operation-status read × 5
3. INFO query on Class 5 item `0x4B` × 1
4. INFO query on Class 11 item `0x0F` × 1

**Packets** — these are captured constants the pump accepts. Earlier
revisions of this page listed four *different* packets here, contradicting
every other file in this documentation set; those did not work.

```python
LEGACY_MAGIC = bytes.fromhex("2707e7f80203949596eb47")
CLASS10_UNLOCK = bytes.fromhex("2707e7f80a03560006c55a")
EXTEND_1 = bytes.fromhex("2705e7f805c14bc382")
EXTEND_2 = bytes.fromhex("2705e7f80bc10fd0c3")
```

Each is `build_geni_frame(apdu)` over the APDUs `02 03 94 95 96`,
`0A 03 56 00 06`, `05 C1 4B` and `0B C1 0F` respectively — so if your frame
builder is right, you can generate them rather than pasting them, and the
match is a useful test of the builder. See
[test_vectors.md](test_vectors.md), which is generated by executing the
codec.

**Timing.** The pump needs the gaps; they are not padding:

| Gap | Delay |
| :--- | :--- |
| Between packets, within a stage | 50 ms |
| Stage 1 → Stage 2 | 100 ms |
| Stage 2 → Stage 3 | 200 ms |
| After Stage 3, before any command | 500 ms |

**Implementation**:
```python
INTER_PACKET_DELAY = 0.05
STAGE_1_TO_2_DELAY = 0.10
STAGE_2_TO_3_DELAY = 0.20
STABILIZE_DELAY = 0.5


async def authenticate(client):
    """
    Perform the three-stage handshake.

    No response is expected. The pump sends no ack, so "success" means the
    sequence was sent without a transport error - not that the pump
    confirmed anything.
    """
    for _ in range(3):  # Stage 1: legacy magic
        await send_packet(client, LEGACY_MAGIC)
        await asyncio.sleep(INTER_PACKET_DELAY)
    await asyncio.sleep(STAGE_1_TO_2_DELAY)

    for _ in range(5):  # Stage 2: Class 10 unlock
        await send_packet(client, CLASS10_UNLOCK)
        await asyncio.sleep(INTER_PACKET_DELAY)
    await asyncio.sleep(STAGE_2_TO_3_DELAY)

    await send_packet(client, EXTEND_1)  # Stage 3: extension packets
    await asyncio.sleep(INTER_PACKET_DELAY)
    await send_packet(client, EXTEND_2)

    await asyncio.sleep(STABILIZE_DELAY)
```

> If the handshake appears to succeed and then everything times out, check
> **bonding** before you check your frames. An unbonded connection is dropped
> at about 1.8 seconds regardless of traffic.

See [02_authentication.md](../protocol/packet_traces/02_authentication.md) for detailed explanation.

---

## Layer 5: Session Management

**Goal**: Track connection state and ensure operations happen in correct order.

### 5.1 Session State Machine

```
DISCONNECTED → CONNECTED → AUTHENTICATING → AUTHENTICATED → ERROR
```

**Implementation**:
```python
from enum import Enum


class SessionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


class Session:
    def __init__(self):
        self.state = SessionState.DISCONNECTED
        self.client = None
        self.char = None

    async def connect(self, device_address):
        """Connect to pump."""
        if self.state != SessionState.DISCONNECTED:
            raise Exception(f"Cannot connect from state: {self.state}")

        self.client, self.char = await connect_to_pump(device_address)
        await enable_notifications(self.client)
        self.state = SessionState.CONNECTED

    async def authenticate(self):
        """Authenticate with pump."""
        if self.state != SessionState.CONNECTED:
            raise Exception(f"Cannot authenticate from state: {self.state}")

        self.state = SessionState.AUTHENTICATING
        try:
            await authenticate(self.client)
            self.state = SessionState.AUTHENTICATED
        except Exception as e:
            self.state = SessionState.ERROR
            raise

    async def disconnect(self):
        """Disconnect from pump."""
        if self.client:
            await self.client.disconnect()
        self.state = SessionState.DISCONNECTED

    def ensure_authenticated(self):
        """Raise error if not authenticated."""
        if self.state != SessionState.AUTHENTICATED:
            raise Exception(
                f"Operation requires authenticated session, current state: {self.state}"
            )
```


---

## Layer 6: Services

**Goal**: Implement business logic for pump operations.

### 6.1 Telemetry Service

Read measurements from pump.

**Implementation**:
```python
class TelemetryService:
    def __init__(self, session):
        self.session = session

    async def read_motor_state(self):
        """
        Read motor telemetry (RPM, power, voltage).

        Returns dict with keys: rpm, power_watts, grid_voltage
        """
        self.session.ensure_authenticated()

        # Request motor state (Sub 0x0045, Obj 0x0057)
        packet = build_info_command(0x0A, 0x0045, 0x0057)
        await send_packet(self.session.client, packet)

        # Wait for response
        response = await receive_packet(timeout=2.0)
        frame = parse_frame(response)

        # Decode payload (3 floats: RPM, Power, Voltage)
        rpm = decode_float_be(frame["payload"][0:4])
        power = decode_float_be(frame["payload"][4:8])
        voltage = decode_float_be(frame["payload"][8:12])

        return {"rpm": rpm, "power_watts": power, "grid_voltage": voltage}

    async def read_flow_pressure(self):
        """
        Read hydraulic telemetry (flow, head pressure).

        Returns dict with keys: flow_m3h, head_meters
        """
        self.session.ensure_authenticated()

        # Request flow/pressure (Sub 0x0122, Obj 0x005D)
        packet = build_info_command(0x0A, 0x0122, 0x005D)
        await send_packet(self.session.client, packet)

        response = await receive_packet(timeout=2.0)
        frame = parse_frame(response)

        # Decode payload (2 floats)
        flow = decode_float_be(frame["payload"][0:4])
        head = decode_float_be(frame["payload"][4:8])

        return {"flow_m3h": flow, "head_meters": head}
```


---

### 6.2 Control Service

Control pump operation.

**Implementation**:
```python
class ControlService:
    def __init__(self, session):
        self.session = session

    async def set_constant_pressure_mode(self, target_meters):
        """
        Set constant pressure mode.

        Args:
            target_meters: Target head pressure in meters (e.g., 1.5)
        """
        self.session.ensure_authenticated()

        # Convert meters to Pascals
        target_pascals = target_meters * 9806.65

        # Encode setpoint
        setpoint_data = encode_float_be(target_pascals)

        # Setpoint goes through the FUSED object (Sub 0x5600, Obj 0x0601),
        # which carries the run state and mode in the same frame. Assert
        # them deliberately: operation_mode = AUTO (0x00), and the mode you
        # actually want.
        payload = bytes([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00])
        packet = build_set_command(0x5600, 0x0601, payload + setpoint_data)
        await send_packet(self.session.client, packet)

        # Then the configuration commit, built from the pump's CURRENT
        # ClockProgramOverview - never from a constant. Byte 4 of that
        # structure is the schedule's enabled flag.
        await self.send_configuration_commit()

        # THE ACK IS NOT THE VERDICT. The pump acks values it is about to
        # clamp: 600 RPM is stored as 1650, 4400 as 3671. Read Object 86
        # Sub 7 back and report what it holds.
        stored = await self.read_prioritized_state()
        return stored.setpoint

    async def stop(self):
        """
        Stop the pump - Class 3, and nothing else.

        Nine bytes, with no room for a mode or a setpoint. Do NOT route this
        through the fused control object: earlier versions did, and every
        start or stop also asserted a mode and overwrote that mode's stored
        setpoint. There is no Obj 0x0600.
        """
        self.session.ensure_authenticated()

        packet = build_geni_frame(bytes([0x03, 0x81, 0x05]))  # 0x06 = START
        await send_packet(self.session.client, packet)

        # A clean ack is [03 00]. A descriptor-only reply [03 01 AC] means
        # the pump described the item instead of acting on it - a rejection.
        response = await receive_packet(timeout=2.0)
        return response[4:6] == bytes([0x03, 0x00])
```

> **Do not read state from Object 86 Sub 6.** It is the *request* object: it
> reports what was last written, and its `control_source` byte reads `0`
> whatever the pump is doing. Sub 7 is the pump's actual state after it has
> weighed remote, local and alarm influence. Measured side by side.

---

## Layer 7: Client Facade

**Goal**: Provide simple, unified API.

**Implementation**:
```python
class AlphaHWRClient:
    def __init__(self, device_address):
        self.device_address = device_address
        self.session = Session()
        self.telemetry = None
        self.control = None
    
    async def connect(self):
        """Connect and authenticate."""
        await self.session.connect(self.device_address)
        await self.session.authenticate()
        
        # Initialize services
        self.telemetry = TelemetryService(self.session)
        self.control = ControlService(self.session)
    
    async def disconnect(self):
        """Disconnect from pump."""
        await self.session.disconnect()
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()
```

**Usage Example**:
```python
async def main():
    address = "XX:XX:XX:XX:XX:XX"
    
    async with AlphaHWRClient(address) as client:
        # Read telemetry
        motor = await client.telemetry.read_motor_state()
        print(f"RPM: {motor['rpm']}")
        
        # Set mode
        await client.control.set_constant_pressure_mode(1.5)
        
        # Read again
        flow = await client.telemetry.read_flow_pressure()
        print(f"Flow: {flow['flow_m3h']} m³/h")
```

