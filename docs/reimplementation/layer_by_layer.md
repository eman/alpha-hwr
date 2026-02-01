# Layer-by-Layer Implementation Guide

This guide walks through implementing the ALPHA HWR protocol step-by-step, from lowest to highest layer. Follow this order to build a working implementation incrementally with testable milestones at each stage.

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
- **CRC Checksums**: CRC-16/MODBUS calculation

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

**Test Milestone**:
- [x] Can discover pump by name
- [x] Returns correct device address

---

### 1.2 Connect to Pump

Connect via BLE and discover GENI service.

**GENI Service UUIDs**:
```python
GENI_SERVICE_UUID = "0000fdd0-0000-1000-8000-00805f9b34fb"
TX_CHAR_UUID = "0000fdd1-0000-1000-8000-00805f9b34fb"  # Write to pump
RX_CHAR_UUID = "0000fdd2-0000-1000-8000-00805f9b34fb"  # Notifications from pump
```

**Implementation**:
```python
async def connect_to_pump(device_address):
    """
    Connect to pump and setup characteristics.
    
    Returns (client, tx_char, rx_char)
    """
    # Connect
    client = await ble_library.connect(device_address)
    
    # Discover services
    await client.discover_services()
    
    # Get GENI service
    service = client.get_service(GENI_SERVICE_UUID)
    
    # Get characteristics
    tx_char = service.get_characteristic(TX_CHAR_UUID)
    rx_char = service.get_characteristic(RX_CHAR_UUID)
    
    return (client, tx_char, rx_char)
```

**Test Milestone**:
- [x] Successfully connects to pump
- [x] Discovers GENI service
- [x] Can access TX/RX characteristics

---

### 1.3 Setup Notifications

Enable notifications on RX characteristic to receive pump responses.

**Implementation**:
```python
response_queue = []

def notification_handler(sender, data):
    """Handle incoming notifications from pump."""
    response_queue.append(data)

async def enable_notifications(client, rx_char):
    """Enable BLE notifications."""
    await client.start_notify(rx_char, notification_handler)
```

**Test Milestone**:
- [x] Notifications enabled without error
- [x] Handler receives data when pump sends

---

### 1.4 Send/Receive Raw Bytes

Implement basic send/receive functions.

**Implementation**:
```python
async def send_packet(tx_char, data: bytes):
    """Send bytes to pump."""
    await tx_char.write_value(data, response=False)

async def receive_packet(timeout=5.0):
    """Wait for response from pump."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if response_queue:
            return response_queue.pop(0)
        await asyncio.sleep(0.01)
    
    raise TimeoutError("No response from pump")
```

**Test Milestone**:
- [x] Can send arbitrary bytes
- [x] Can receive responses
- [x] Timeout works correctly

---

## Layer 2: Protocol Codec

**Goal**: Encode and decode primitive data types (floats, integers).

### 2.1 CRC-16/MODBUS

Implement CRC calculation for packet integrity.

**Algorithm**:
```python
def calc_crc16_modbus(data: bytes) -> int:
    """
    Calculate CRC-16/MODBUS checksum.
    
    Polynomial: 0x8005
    Initial value: 0xFFFF
    Final XOR: 0x0000
    Reflect input: True
    Reflect output: True
    """
    crc = 0xFFFF
    
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001  # Reflected polynomial
            else:
                crc >>= 1
    
    return crc
```

**Test Vectors** (from [test_vectors.md](test_vectors.md)):
```python
assert calc_crc16_modbus(b"\x07\xe7\xf8\x0a\x04\x00\x85") == 0x1202
assert calc_crc16_modbus(b"\x06\xe7\xf8\x00\x67") == 0xE3A3
```

**Test Milestone**:
- [x] Matches all test vectors
- [x] Handles empty input
- [x] Handles large inputs

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

**Test Milestone**:
- [x] Encodes all test values correctly
- [x] Decodes all test values correctly
- [x] Round-trip conversion (encode → decode) is accurate

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

**Test Milestone**:
- [x] Encodes correctly
- [x] Decodes correctly
- [x] Handles edge cases (0, max value)

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
    apdu.append(sub_id & 0xFF)         # Sub ID low
    apdu.append((obj_id >> 8) & 0xFF)  # Obj ID high
    apdu.append(obj_id & 0xFF)         # Obj ID low
    
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
    crc = calc_crc16_modbus(crc_data)
    
    # Append CRC (big-endian)
    frame.append((crc >> 8) & 0xFF)  # CRC high
    frame.append(crc & 0xFF)         # CRC low
    
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

**Test Milestone**:
- [x] Builds valid INFO command
- [x] CRC is correct
- [x] Length field is correct

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
    # Build APDU
    opspec = 0x80 | len(data)  # SET operation (bit 7) + data length
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
    crc = calc_crc16_modbus(crc_data)
    frame.append((crc >> 8) & 0xFF)
    frame.append(crc & 0xFF)
    
    return bytes(frame)
```

**Test**:
```python
# Set constant pressure mode to 1.5m (14710 Pascals)
setpoint_data = encode_float_be(14710.0)
packet = build_set_command(0x5600, 0x0601, setpoint_data)
assert packet[0] == 0x27
assert packet[5] == 0x84  # OpSpec: SET (0x80) + 4 bytes (0x04)
assert len(packet) == 16  # Header (4) + APDU (10: class, opspec, ids, data) + CRC (2)
```

**Test Milestone**:
- [x] Builds valid SET command
- [x] OpSpec encodes data length correctly
- [x] CRC is correct

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
    crc_calculated = calc_crc16_modbus(data[1:-2])
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
        "crc": crc_received
    }
```

**Test**:
```python
# Example response with motor speed = 2500.0 RPM
response = bytes([
    0x24,  # Start
    0x08,  # Length
    0xE7, 0x0A,  # Service ID
    0x0A,  # Class 10
    0x00,  # OpSpec
    0x00, 0x45,  # Sub 0x0045 (motor)
    0x00, 0x57,  # Obj 0x0057 (state)
    0x45, 0x1C, 0x40, 0x00,  # Speed = 2500.0
    0x12, 0x34  # CRC (example)
])
# Note: CRC would need to be correct for real test

frame = parse_frame(response)
assert frame["class_byte"] == 0x0A
assert frame["sub_id"] == 0x0045
assert frame["obj_id"] == 0x0057
assert len(frame["payload"]) == 4
```

**Test Milestone**:
- [x] Parses valid responses
- [x] Detects CRC errors
- [x] Extracts payload correctly

---

## Layer 4: Authentication

**Goal**: Unlock pump with magic packet sequence.

### 4.1 Authentication Sequence

Send exactly these packets in order:
1. Legacy Magic × 3
2. Class 10 Unlock × 5
3. Extend 1 × 1
4. Extend 2 × 1

**Packets** (pre-calculated with CRC):
```python
LEGACY_MAGIC = bytes([0x27, 0x06, 0xE7, 0xF8, 0x00, 0x67, 0xA3, 0xE3])
CLASS10_UNLOCK = bytes([0x27, 0x07, 0xE7, 0xF8, 0x0A, 0x04, 0x00, 0x85, 0x02, 0x12])
EXTEND_1 = bytes([0x27, 0x07, 0xE7, 0xF8, 0x1A, 0x2C, 0x00, 0x52, 0x01, 0x02])
EXTEND_2 = bytes([0x27, 0x06, 0xE7, 0xF8, 0x1A, 0x54, 0xD2, 0x55])
```

**Implementation**:
```python
async def authenticate(tx_char):
    """
    Perform authentication sequence.
    
    No response expected - success is assumed if no errors.
    """
    # Step 1: Legacy Magic (3x)
    for _ in range(3):
        await send_packet(tx_char, LEGACY_MAGIC)
        await asyncio.sleep(0.05)  # 50ms delay
    
    # Step 2: Class 10 Unlock (5x)
    for _ in range(5):
        await send_packet(tx_char, CLASS10_UNLOCK)
        await asyncio.sleep(0.05)
    
    # Step 3: Extend 1
    await send_packet(tx_char, EXTEND_1)
    await asyncio.sleep(0.05)
    
    # Step 4: Extend 2
    await send_packet(tx_char, EXTEND_2)
    await asyncio.sleep(0.1)  # Longer delay after final packet
```

**Test Milestone**:
- [x] Sends all packets without error
- [x] Respects timing delays
- [x] After authentication, commands work

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
        self.tx_char = None
        self.rx_char = None
    
    async def connect(self, device_address):
        """Connect to pump."""
        if self.state != SessionState.DISCONNECTED:
            raise Exception(f"Cannot connect from state: {self.state}")
        
        self.client, self.tx_char, self.rx_char = await connect_to_pump(device_address)
        await enable_notifications(self.client, self.rx_char)
        self.state = SessionState.CONNECTED
    
    async def authenticate(self):
        """Authenticate with pump."""
        if self.state != SessionState.CONNECTED:
            raise Exception(f"Cannot authenticate from state: {self.state}")
        
        self.state = SessionState.AUTHENTICATING
        try:
            await authenticate(self.tx_char)
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
            raise Exception(f"Operation requires authenticated session, current state: {self.state}")
```

**Test Milestone**:
- [x] State transitions work correctly
- [x] Guards prevent invalid operations
- [x] Error state is set on failures

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
        await send_packet(self.session.tx_char, packet)
        
        # Wait for response
        response = await receive_packet(timeout=2.0)
        frame = parse_frame(response)
        
        # Decode payload (3 floats: RPM, Power, Voltage)
        rpm = decode_float_be(frame["payload"][0:4])
        power = decode_float_be(frame["payload"][4:8])
        voltage = decode_float_be(frame["payload"][8:12])
        
        return {
            "rpm": rpm,
            "power_watts": power,
            "grid_voltage": voltage
        }
    
    async def read_flow_pressure(self):
        """
        Read hydraulic telemetry (flow, head pressure).
        
        Returns dict with keys: flow_m3h, head_meters
        """
        self.session.ensure_authenticated()
        
        # Request flow/pressure (Sub 0x0122, Obj 0x005D)
        packet = build_info_command(0x0A, 0x0122, 0x005D)
        await send_packet(self.session.tx_char, packet)
        
        response = await receive_packet(timeout=2.0)
        frame = parse_frame(response)
        
        # Decode payload (2 floats)
        flow = decode_float_be(frame["payload"][0:4])
        head = decode_float_be(frame["payload"][4:8])
        
        return {
            "flow_m3h": flow,
            "head_meters": head
        }
```

**Test Milestone**:
- [x] Successfully reads motor state
- [x] Successfully reads flow/pressure
- [x] Parses values correctly

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
        
        # Send SET command (Sub 0x5600, Obj 0x0601)
        packet = build_set_command(0x5600, 0x0601, setpoint_data)
        await send_packet(self.session.tx_char, packet)
        
        # Wait for ACK
        response = await receive_packet(timeout=2.0)
        frame = parse_frame(response)
        
        # Check for success (OpSpec should indicate success)
        if frame["opspec"] & 0x40:  # Error bit
            raise Exception("Pump rejected command")
    
    async def stop(self):
        """Stop the pump."""
        self.session.ensure_authenticated()
        
        # Send stop command (Sub 0x5600, Obj 0x0600, value=0)
        stop_data = encode_float_be(0.0)
        packet = build_set_command(0x5600, 0x0600, stop_data)
        await send_packet(self.session.tx_char, packet)
        
        response = await receive_packet(timeout=2.0)
        frame = parse_frame(response)
        
        if frame["opspec"] & 0x40:
            raise Exception("Stop command failed")
```

**Test Milestone**:
- [x] Successfully sets mode
- [x] Successfully stops pump
- [x] Detects errors

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

**Test Milestone**:
- [x] Context manager works
- [x] Services accessible
- [x] Clean disconnect
