# Service Discovery Troubleshooting

## The Issue
Unable to discover GENI service UUID (`0000fdd0-0000-1000-8000-00805f9b34fb`) on the pump.

## Root Cause
**The GENI service UUID is NOT always advertised in BLE advertisements.** However, the pump DOES advertise the **Grundfos Company ID** (`0000fe5d-0000-1000-8000-00805f9b34fb`) in its service data.

### How the Python Library Discovers Pumps
The `alpha-hwr` CLI scan command matches pumps using **either of these criteria**:

```python
# From src/alpha_hwr/client.py discover() method:
is_geni = "0000fdd0-0000-1000-8000-00805f9b34fb" in advertised_services
is_grundfos = "0000fe5d-0000-1000-8000-00805f9b34fb" in service_data

if is_geni or is_grundfos:
    # Device is an ALPHA HWR pump
```

**This means:**
1. Some pumps advertise the GENI service UUID directly
2. All pumps advertise the Grundfos Company ID in service data
3. Either match is sufficient for discovery

### BLE Advertisement Structure
- **Device Name**: `ALPHA_<SERIAL>` (e.g., `ALPHA_0000479`)
- **Service UUIDs** (optional): May include `0000fdd0-...`
- **Service Data**: Includes `0000fe5d-...` (Grundfos Company ID) with payload `[flags][family][type][version]`

## Solution: Discovery by Grundfos Company ID (Most Reliable)

The **most reliable discovery method** is to match by Grundfos Company ID in the BLE service data, since all ALPHA HWR pumps advertise this.

### Step 1: Scan for Grundfos Company ID in Service Data
```cpp
// Scan and look for Grundfos Company ID in service data
static const esp32_ble_tracker::ESPBTUUID GRUNDFOS_COMPANY_ID =
    esp32_ble_tracker::ESPBTUUID::from_raw("0000fe5d-0000-1000-8000-00805f9b34fb");

// In your scan callback:
if (device->get_manufacturer_data().contains(GRUNDFOS_COMPANY_ID)) {
    // This is an ALPHA HWR pump
    const auto &service_data = device->get_manufacturer_data()[GRUNDFOS_COMPANY_ID];
    
    // Parse service data:
    // Byte 0-1: Flags
    // Byte 2: Product Family (0x34 = ALPHA)
    // Byte 3: Product Type (0x07 = HWR)
    // Byte 4: Product Version
    
    if (service_data.size() >= 5 && 
        service_data[2] == 0x34 && 
        service_data[3] == 0x07) {
        // Confirmed ALPHA HWR pump
    }
}
```

### Step 2: Alternative - Match by Device Name Pattern
As a secondary method, you can also match by the advertised device name:

```cpp
// Device name pattern: ALPHA_<SERIAL_NUMBER>
if (device->get_name() && device->get_name().substr(0, 6) == "ALPHA_") {
    // This is likely an ALPHA HWR pump
}
```

### Step 3: Connect and Proceed
```cpp
ble_client:
  - mac_address: AA:BB:CC:DD:EE:FF  # MAC from scan
    id: alpha_pump_client
```

## Correct Connection Sequence

```
┌──────────────────────────────────────────────┐
│ 1. BLE SCAN PHASE                            │
│    Match by: Grundfos Company ID in data     │
│    OR by: GENI Service UUID (if advertised)  │
│    OR by: Device name "ALPHA_<serial>"       │
│    Get: MAC address, signal strength         │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│ 2. CONNECT PHASE                             │
│    Connect to MAC address                    │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│ 3. SERVICE DISCOVERY (Auto)                  │
│    GENI Service UUID now available ✓         │
│    GENI Characteristic now available ✓       │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│ 4. AUTHENTICATE                              │
│    Send magic packets                        │
│    Start receiving telemetry                 │
└──────────────────────────────────────────────┘
```

## Alternative Discovery Methods

### Option A: Scan by GENI Service UUID (If Advertised)
Some pump firmware versions advertise the GENI service UUID directly:

```cpp
if (device->is_advertising_service(GENI_SERVICE_UUID)) {
    // Device advertises GENI service
}
```

However, this is NOT guaranteed, so the Grundfos Company ID method is more reliable.

### Option B: Scan by Device Name Pattern
Secondary method - matches devices with names starting with "ALPHA_":

```cpp
if (device->get_name() && device->get_name().substr(0, 6) == "ALPHA_") {
    // Likely an ALPHA HWR pump
}
```

### Option C: Scan by Signal Strength + Name Filter
For better filtering when multiple devices present:

```cpp
if (device->get_rssi() > -60 && 
    device->get_name() && device->get_name().substr(0, 6) == "ALPHA_") {
    // Likely the pump nearby
}
```

## Debugging

### Enable Low-Level BLE Logging
```yaml
logger:
  level: DEBUG
  
esp32_ble_tracker:
  scan_parameters:
    interval: 1.1s
    window: 1.1s
```

Look for logs like:
```
[ESP32_BLE] Found device: AA:BB:CC:DD:EE:FF
[ESP32_BLE] Name: "Grundfos"
[ESP32_BLE] RSSI: -45 dBm
```

### Verify Service Discovery After Connection
```cpp
void gatt_discover_complete_callback() {
    ESP_LOGI("alpha_hwr", "Service Discovery Complete!");
    
    auto *svc = this->parent()->get_service(GENI_SERVICE_UUID);
    if (svc) {
        ESP_LOGI("alpha_hwr", "✓ GENI Service found!");
    } else {
        ESP_LOGE("alpha_hwr", "✗ GENI Service NOT in GATT table!");
    }
}
```

## Common Issues

### Issue 1: ESP32 Sees Pump in Scan but Service Discovery Fails

**Symptoms:**
- Pump appears in BLE scan logs
- Connection established
- Service discovery reports no services

**Causes:**
- Pump firmware issue
- Pump doesn't support GENI service
- Bonding/pairing issue

**Solutions:**
1. Try factory reset of pump
2. Verify pump is ALPHA HWR model (Family 52, Type 7)
3. Check pump firmware version (see Class 7 ID 50 after auth)
4. Force re-pair: delete bonding data, reconnect

### Issue 2: Multiple Pumps Nearby

**Symptoms:**
- Connecting to wrong pump

**Solutions:**
1. Use MAC address whitelist (most reliable)
2. Filter by signal strength (RSSI > -60)
3. Read serial number (Class 7 ID 9) after connecting to verify

### Issue 3: Bonding Cache Issues

**Symptoms:**
- Device connected but services not discovered
- Works first time, fails on reconnect

**Solutions:**
```yaml
ble_client:
  - mac_address: AA:BB:CC:DD:EE:FF
    id: alpha_pump
    auto_connect: true  # Force fresh connection
```

## Complete ESPHome Configuration Example

```yaml
esphome:
  name: alpha-hwr-bridge
  platform: ESP32
  board: esp32dev

logger:
  level: DEBUG  # Enable to debug discovery

esp32_ble_tracker:
  scan_parameters:
    interval: 1.1s
    window: 1.1s

ble_client:
  - mac_address: AA:BB:CC:DD:EE:FF  # Replace with your pump MAC
    id: alpha_pump_client

custom_component:
  - lambda: |-
      auto pump = new AlphaHwrComponent();
      pump->set_ble_client_parent(id(alpha_pump_client));
      App.register_component(pump);
      return {pump->flow_sensor, pump->head_sensor};
```

## Verification Checklist

- [ ] **Method 1 (Recommended)**: Scan for Grundfos Company ID (`0000fe5d-...`) in service data
- [ ] **Method 2 (Fallback)**: Scan for device name starting with "ALPHA_" (e.g., "ALPHA_0000479")
- [ ] **Method 3 (Firmware dependent)**: Check if GENI Service UUID is advertised
- [ ] Pump MAC address correct
- [ ] ESP32 can see pump in BLE scan logs
- [ ] Connection established (check logs for "Connected")
- [ ] Service discovery completes (check logs for "Discovery complete")
- [ ] GENI Service UUID found in GATT table (always present after connection)
- [ ] GENI Characteristic found
- [ ] Authentication packets sent successfully
- [ ] Telemetry notifications received

## Key Takeaway

**The most reliable discovery method is to match by Grundfos Company ID (`0000fe5d-...`) in BLE service data, since all ALPHA HWR pumps advertise this regardless of firmware version. Alternatively, match by device name pattern ("ALPHA_").**

The GENI service UUID itself may NOT be in the BLE advertisement (depends on firmware), but it WILL be discovered in the GATT table after connection.

## Related Documentation

- **Connection Sequence**: See `docs/protocol/connection.md`
- **BLE Architecture**: See `docs/protocol/ble_architecture.md`
- **Device Info**: See `docs/protocol/device_info.md`
- **ESPHome Integration**: See `docs/integrations/esphome.md`
