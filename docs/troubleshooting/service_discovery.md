# Service Discovery Troubleshooting

## The Issue
Unable to discover GENI service UUID (`0000fdd0-0000-1000-8000-00805f9b34fb`) on the pump.

## Root Cause
**The GENI service UUID is NOT advertised during BLE scanning.** It only appears in the GATT service table after connection and service discovery.

### Key Distinction
- **BLE Advertisement**: Broadcast packets sent continuously, minimal data
- **GATT Service Table**: Complete list of services, discovered during connection phase

## Solution: Discovery by Device Name

### Step 1: Scan for Device Name (NOT Service UUID)
The pump advertises with local name: `Grundfos` or `HWR`

```cpp
// In ESPHome, match by device name
if (device->get_name() == "Grundfos" || device->get_name() == "HWR") {
    // This is the pump - proceed to connect
}
```

### Step 2: Connect to Discovered MAC Address
```cpp
ble_client:
  - mac_address: AA:BB:CC:DD:EE:FF  # MAC from scan
    id: alpha_pump_client
```

### Step 3: Service Discovery (Automatic)
After connection, the pump's GATT table is available:
- GENI Service: `0000fdd0-0000-1000-8000-00805f9b34fb` ✓ (now discoverable)
- GENI Characteristic: `859cffd1-036e-432a-aa28-1a0085b87ba9` ✓

## Correct Connection Sequence

```
┌─────────────────────────────────────────┐
│ 1. BLE SCAN PHASE                       │
│    Look for: name = "Grundfos" or "HWR"│
│    Get: MAC address, signal strength    │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│ 2. CONNECT PHASE                        │
│    Connect to MAC address               │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│ 3. SERVICE DISCOVERY (Auto)             │
│    GENI Service UUID now available ✓    │
│    GENI Characteristic now available ✓  │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│ 4. AUTHENTICATE                         │
│    Send magic packets                   │
│    Start receiving telemetry            │
└─────────────────────────────────────────┘
```

## Alternative Discovery Methods

### Option A: Scan by Manufacturer ID
The pump uses **Grundfos Company ID**: `0000fe5d-0000-1000-8000-00805f9b34fb`

Look for this in BLE advertisement manufacturer data:

```cpp
static const esp32_ble_tracker::ESPBTUUID GRUNDFOS_COMPANY_ID =
    esp32_ble_tracker::ESPBTUUID::from_raw("0000fe5d-0000-1000-8000-00805f9b34fb");
```

### Option B: Scan by Signal Strength + Name
For better filtering when multiple devices present:

```cpp
if (device->get_rssi() > -60 && 
    device->get_name().find("Grundfos") != std::string::npos) {
    // Likely the pump
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

- [ ] Device broadcasts with name "Grundfos" or "HWR"
- [ ] Pump MAC address correct
- [ ] ESP32 can see pump in BLE scan logs
- [ ] Connection established (check logs for "Connected")
- [ ] Service discovery completes (check logs for "Discovery complete")
- [ ] GENI Service UUID found in GATT table
- [ ] GENI Characteristic found
- [ ] Authentication packets sent successfully
- [ ] Telemetry notifications received

## Key Takeaway

**Do NOT look for the GENI service UUID in BLE advertisements. Match by device name ("Grundfos" or "HWR"), connect, and then the GENI service will be automatically discovered.**

## Related Documentation

- **Connection Sequence**: See `docs/protocol/connection.md`
- **BLE Architecture**: See `docs/protocol/ble_architecture.md`
- **Device Info**: See `docs/protocol/device_info.md`
- **ESPHome Integration**: See `docs/integrations/esphome.md`
