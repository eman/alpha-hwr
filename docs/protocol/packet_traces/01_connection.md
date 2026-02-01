# Packet Trace: BLE Connection Setup

This document shows the complete BLE connection sequence for the ALPHA HWR pump, from discovery to being ready for authentication.

## Overview

Before authenticating, you must:
1. Discover the pump via BLE scanning
2. Connect to the pump
3. Discover GATT services and characteristics
4. Enable notifications

## Connection Flow

```mermaid
sequenceDiagram
    participant Client
    participant Pump

    Client->>Pump: BLE Scan
    Pump-->>Client: Advertisement (ALPHA_XXX)
    
    Client->>Pump: Connect Request
    Pump-->>Client: Connection Accepted
    
    Client->>Pump: Discover Services
    Pump-->>Client: GENI Service (0xFDD0)
    
    Client->>Pump: Discover Characteristics
    Pump-->>Client: TX (0xFDD1), RX (0xFDD2)
    
    Client->>Pump: Enable Notifications
    Pump-->>Client: Notifications Enabled
    
    Note right of Pump: Ready for Authentication
```


---

## Step 1: BLE Discovery

### 1.1 Scan for Devices

The pump advertises with a recognizable name pattern.

**Advertisement Name**: `ALPHA_<serial>` or `ALPHA <serial>`

**Examples**:
- `ALPHA_123456`
- `ALPHA 123456`
- `ALPHA_XXXXXXXXXXXX`

**Service UUID** (advertised): `0000fdd0-0000-1000-8000-00805f9b34fb`

### 1.2 Implementation

```python
import asyncio
from bleak import BleakScanner

async def discover_alpha_pumps(timeout=10.0):
    """
    Scan for ALPHA HWR pumps.
    
    Returns list of discovered devices.
    """
    print(f"Scanning for ALPHA pumps (timeout: {timeout}s)...")
    
    devices = await BleakScanner.discover(timeout=timeout)
    
    alpha_pumps = []
    for device in devices:
        if device.name and "ALPHA" in device.name:
            alpha_pumps.append(device)
            print(f"Found: {device.name} ({device.address})")
    
    return alpha_pumps

# Usage
pumps = await discover_alpha_pumps()
if not pumps:
    print("No pumps found!")
else:
    print(f"Found {len(pumps)} pump(s)")
```

### 1.3 JavaScript Example

```javascript
// Web Bluetooth API
async function discoverPump() {
  try {
    const device = await navigator.bluetooth.requestDevice({
      filters: [
        { namePrefix: "ALPHA" },
        { services: ["0000fdd0-0000-1000-8000-00805f9b34fb"] }
      ]
    });
    
    console.log(`Connected to: ${device.name}`);
    return device;
  } catch (error) {
    console.error("Discovery failed:", error);
  }
}
```

**Test Milestone**:
- [x] Can discover pump by name
- [x] Pump appears in scan results
- [x] Device address is valid

---

## Step 2: BLE Connection

### 2.1 Connect to Device

Once discovered, connect to the pump using its BLE address.

**Implementation**:
```python
from bleak import BleakClient

async def connect_to_pump(address):
    """
    Connect to pump via BLE.
    
    Args:
        address: BLE MAC address (e.g., "XX:XX:XX:XX:XX:XX")
    
    Returns:
        BleakClient instance
    """
    print(f"Connecting to {address}...")
    
    client = BleakClient(address, timeout=15.0)
    await client.connect()
    
    if client.is_connected:
        print("Connected successfully!")
    else:
        raise Exception("Connection failed")
    
    return client
```

**Test Milestone**:
- [x] Successfully connects to pump
- [x] Connection is stable
- [x] No immediate disconnection

---

## Step 3: Service Discovery

### 3.1 GENI Service UUIDs

The pump exposes a GATT service with two characteristics:

**GENI Service**:
- **UUID**: `0000fdd0-0000-1000-8000-00805f9b34fb`

**TX Characteristic** (Write to pump):
- **UUID**: `0000fdd1-0000-1000-8000-00805f9b34fb`
- **Properties**: Write, Write Without Response

**RX Characteristic** (Notifications from pump):
- **UUID**: `0000fdd2-0000-1000-8000-00805f9b34fb`
- **Properties**: Notify

### 3.2 Discover Services

```python
# UUIDs
GENI_SERVICE_UUID = "0000fdd0-0000-1000-8000-00805f9b34fb"
TX_CHAR_UUID = "0000fdd1-0000-1000-8000-00805f9b34fb"
RX_CHAR_UUID = "0000fdd2-0000-1000-8000-00805f9b34fb"

async def discover_geni_service(client):
    """
    Discover GENI service and characteristics.
    
    Args:
        client: Connected BleakClient
    
    Returns:
        (service, tx_char, rx_char)
    """
    print("Discovering services...")
    
    # Get all services
    services = client.services
    
    # Find GENI service
    service = None
    for svc in services:
        if svc.uuid.lower() == GENI_SERVICE_UUID.lower():
            service = svc
            break
    
    if not service:
        raise Exception("GENI service not found")
    
    print(f"Found GENI service: {service.uuid}")
    
    # Find TX characteristic
    tx_char = None
    for char in service.characteristics:
        if char.uuid.lower() == TX_CHAR_UUID.lower():
            tx_char = char
            print(f"  TX Char: {char.uuid} (properties: {char.properties})")
    
    # Find RX characteristic
    rx_char = None
    for char in service.characteristics:
        if char.uuid.lower() == RX_CHAR_UUID.lower():
            rx_char = char
            print(f"  RX Char: {char.uuid} (properties: {char.properties})")
    
    if not tx_char or not rx_char:
        raise Exception("Required characteristics not found")
    
    return (service, tx_char, rx_char)
```

**Test Milestone**:
- [x] GENI service discovered
- [x] TX characteristic found
- [x] RX characteristic found
- [x] Correct UUIDs matched

---

## Step 4: Enable Notifications

### 4.1 Subscribe to RX Characteristic

The pump sends responses and telemetry via notifications on the RX characteristic.

**Implementation**:
```python
async def enable_notifications(client, rx_char_uuid):
    """
    Enable notifications for responses from pump.
    
    Args:
        client: Connected BleakClient
        rx_char_uuid: RX characteristic UUID
    """
    
    def notification_handler(sender, data):
        """Handle incoming notifications."""
        print(f"<< Received ({len(data)} bytes): {data.hex(' ')}")
        # Store in queue for processing
        response_queue.append(bytes(data))
    
    # Enable notifications
    await client.start_notify(rx_char_uuid, notification_handler)
    print("Notifications enabled")

# Global response queue
response_queue = []
```

### 4.2 Verify Notifications

After enabling, the pump may send an initial notification (sometimes empty or telemetry).

**Expected Behavior**:
- No error when enabling notifications
- Handler is called when pump sends data
- Data arrives as `bytearray` or `bytes`

**Test Milestone**:
- [x] Notifications enabled without error
- [x] Handler registered successfully
- [x] Ready to receive responses

---

## Step 5: Complete Setup Example

### 5.1 Full Connection Flow

```python
import asyncio
from bleak import BleakClient, BleakScanner

# UUIDs
GENI_SERVICE_UUID = "0000fdd0-0000-1000-8000-00805f9b34fb"
TX_CHAR_UUID = "0000fdd1-0000-1000-8000-00805f9b34fb"
RX_CHAR_UUID = "0000fdd2-0000-1000-8000-00805f9b34fb"

# Response queue
response_queue = []

def notification_handler(sender, data):
    """Handle notifications from pump."""
    print(f"<< Notification ({len(data)} bytes): {data.hex(' ')}")
    response_queue.append(bytes(data))

async def setup_connection(address=None):
    """
    Complete BLE connection setup.
    
    Args:
        address: BLE address (if None, will scan)
    
    Returns:
        (client, tx_char_uuid, rx_char_uuid)
    """
    # Step 1: Discover pump if no address provided
    if address is None:
        print("Scanning for ALPHA pumps...")
        devices = await BleakScanner.discover(timeout=10.0)
        
        for device in devices:
            if device.name and "ALPHA" in device.name:
                address = device.address
                print(f"Found pump: {device.name} at {address}")
                break
        
        if not address:
            raise Exception("No ALPHA pump found")
    
    # Step 2: Connect to pump
    print(f"\nConnecting to {address}...")
    client = BleakClient(address, timeout=15.0)
    await client.connect()
    print("Connected!")
    
    # Step 3: Verify services
    print("\nDiscovering services...")
    services = client.services
    geni_service = None
    
    for service in services:
        if service.uuid.lower() == GENI_SERVICE_UUID.lower():
            geni_service = service
            print(f"Found GENI service: {service.uuid}")
            break
    
    if not geni_service:
        await client.disconnect()
        raise Exception("GENI service not found")
    
    # Step 4: Verify characteristics
    print("\nVerifying characteristics...")
    tx_found = False
    rx_found = False
    
    for char in geni_service.characteristics:
        if char.uuid.lower() == TX_CHAR_UUID.lower():
            tx_found = True
            print(f"  TX: {char.uuid} ({char.properties})")
        elif char.uuid.lower() == RX_CHAR_UUID.lower():
            rx_found = True
            print(f"  RX: {char.uuid} ({char.properties})")
    
    if not tx_found or not rx_found:
        await client.disconnect()
        raise Exception("Required characteristics not found")
    
    # Step 5: Enable notifications
    print("\nEnabling notifications...")
    await client.start_notify(RX_CHAR_UUID, notification_handler)
    print("Notifications enabled!")
    
    print("\n✓ Connection setup complete!")
    print("  Ready for authentication\n")
    
    return (client, TX_CHAR_UUID, RX_CHAR_UUID)

async def main():
    """Test connection setup."""
    try:
        client, tx_uuid, rx_uuid = await setup_connection()
        
        # Keep connection alive
        print("Connection active. Press Ctrl+C to disconnect...")
        await asyncio.sleep(30)
        
        # Cleanup
        await client.disconnect()
        print("Disconnected")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 5.2 Expected Output

```
Scanning for ALPHA pumps...
Found pump: ALPHA_123456 at XX:XX:XX:XX:XX:XX

Connecting to XX:XX:XX:XX:XX:XX...
Connected!

Discovering services...
Found GENI service: 0000fdd0-0000-1000-8000-00805f9b34fb

Verifying characteristics...
  TX: 0000fdd1-0000-1000-8000-00805f9b34fb (['write', 'write-without-response'])
  RX: 0000fdd2-0000-1000-8000-00805f9b34fb (['notify'])

Enabling notifications...
Notifications enabled!

✓ Connection setup complete!
  Ready for authentication

Connection active. Press Ctrl+C to disconnect...
```

**Test Milestone**:
- [x] Full connection flow completes
- [x] All services and characteristics found
- [x] Notifications enabled
- [x] Ready for authentication

---

## Common Issues

### Issue 1: Pump Not Found in Scan

**Symptom**: No devices with "ALPHA" in name.

**Causes**:
- Pump is off or out of range
- Pump is already connected to another device
- Bluetooth adapter disabled

**Fix**:
1. Verify pump is powered on
2. Disconnect pump from other devices (phone app)
3. Move closer to pump
4. Restart Bluetooth adapter

---

### Issue 2: Connection Timeout

**Symptom**: Connection attempt times out.

**Causes**:
- Pump went to sleep
- Pump is paired with another device
- BLE interference

**Fix**:
1. Wake pump (touch button)
2. Unpair from other devices
3. Increase connection timeout (15-20 seconds)
4. Retry connection

---

### Issue 3: Service Not Found

**Symptom**: GENI service UUID not discovered.

**Causes**:
- Connected to wrong device
- BLE cache issue
- Incompatible firmware

**Fix**:
1. Verify device name contains "ALPHA"
2. Clear BLE cache (restart app/OS)
3. Check pump firmware version
4. Use correct service UUID

---

### Issue 4: Notifications Not Working

**Symptom**: Notifications never trigger handler.

**Causes**:
- Wrong characteristic UUID
- Handler not registered
- Pump not sending data yet

**Fix**:
1. Verify RX characteristic UUID is correct
2. Ensure notifications enabled before sending commands
3. Send authentication packets to unlock telemetry
4. Check handler is `async` if required by library

---

## Platform-Specific Notes

### Python (Bleak)

```python
# Bleak is cross-platform and works on Windows, macOS, Linux
from bleak import BleakClient, BleakScanner

# No special setup needed
```

### JavaScript (Web Bluetooth)

```javascript
// Only works in browsers with Web Bluetooth
// Requires HTTPS or localhost
const device = await navigator.bluetooth.requestDevice({
  filters: [{ namePrefix: "ALPHA" }]
});

const server = await device.gatt.connect();
const service = await server.getPrimaryService("0000fdd0-0000-1000-8000-00805f9b34fb");
```

### Rust (btleplug)

```rust
use btleplug::api::{Central, Manager as _, Peripheral as _};
use btleplug::platform::{Adapter, Manager};

let manager = Manager::new().await?;
let adapters = manager.adapters().await?;
let central = &adapters[0];

// Scan and connect
```

### C/C++ (Platform-specific)

**Windows**: Use Windows BLE APIs
**macOS/iOS**: Use CoreBluetooth
**Linux**: Use BlueZ D-Bus API

---

## Next Steps

After successful connection setup:

1. **Authenticate**: Send authentication sequence (see [02_authentication.md](02_authentication.md))
2. **Read Telemetry**: Request telemetry data (see [03_telemetry_stream.md](03_telemetry_stream.md))
3. **Control Pump**: Send control commands (see [04_set_mode.md](04_set_mode.md))

---

## Reference

- [BLE Architecture](../ble_architecture.md) - BLE layer details
- [Connection Protocol](../connection.md) - Protocol overview
- [Authentication](02_authentication.md) - Next step after connection

---

## Testing Checklist

Use this checklist to verify your connection implementation:

- [ ] Discovers pump via BLE scan
- [ ] Connects successfully
- [ ] Finds GENI service (0xFDD0)
- [ ] Finds TX characteristic (0xFDD1)
- [ ] Finds RX characteristic (0xFDD2)
- [ ] Enables notifications successfully
- [ ] Notification handler receives data
- [ ] Connection remains stable for 30+ seconds
- [ ] Clean disconnection works
- [ ] Can reconnect after disconnection

Once all items are checked, proceed to authentication!
