# ESPHome Integration

Reference documentation for integrating Grundfos ALPHA HWR pumps with ESPHome and Home Assistant.

!!! success "Production Ready"
    Fully tested implementation with stable BLE connection, complete telemetry polling, and automatic reconnection.

## Overview

The ESPHome component acts as a BLE-to-WiFi bridge, exposing pump telemetry sensors to Home Assistant via the native ESPHome API.

### Features

- Stable BLE connection with proper security configuration
- Real-time telemetry: flow, pressure, power, RPM, and temperature
- Active polling every 10 seconds
- Automatic reconnection handling
- Multi-packet reassembly for BLE fragmentation
- Native Home Assistant integration

### Requirements

- ESP32 microcontroller with Bluetooth LE support
- ESPHome with ESP-IDF framework
- Pump within BLE range (~10m)

## Configuration

### Basic Setup

Find your pump's MAC address:
```bash
alpha-hwr device scan
```

Create `alpha-hwr-bridge.yaml`:

```yaml
esphome:
  name: alpha-hwr-bridge
  friendly_name: ALPHA HWR Pump

external_components:
  - source:
      type: local
      path: custom_components
    components: [alpha_hwr]

esp32:
  board: esp32-c3-devkitm-1
  variant: esp32c3
  framework:
    type: esp-idf  # Required for BLE security

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

logger:
  level: DEBUG

api:
  encryption:
    key: !secret api_key

ota:
  - platform: esphome
    password: !secret ota_password

esp32_ble_tracker:
  scan_parameters:
    interval: 1.1s
    window: 1.1s

ble_client:
  - mac_address: "AA:BB:CC:DD:EE:FF"
    id: alpha_pump

alpha_hwr:
  ble_client_id: alpha_pump
  flow:
    name: "Flow Rate"
  head:
    name: "Head Pressure"
  power:
    name: "Power"
  rpm:
    name: "Motor RPM"
  temp_media:
    name: "Water Temperature"
```

## Available Sensors

| Sensor | Unit | Update Rate | Description |
|--------|------|-------------|-------------|
| `flow` | m³/h | 10s | Water flow rate |
| `head` | m | 10s | Pump discharge head |
| `power` | W | 10s | Electrical power consumption |
| `rpm` | RPM | 10s | Motor speed |
| `temp_media` | °C | 10s | Water temperature |

### Expected Values

**Pump running:**
- Flow: 0.5 - 4.5 m³/h
- Head: 0.5 - 6.0 m
- Power: 5 - 80 W
- RPM: 1000 - 4200

**Pump idle:**
- Flow: 0.000 m³/h
- Head: 0.00 m
- Power: 0.0 W
- RPM: 0
- Temperature: 15-25°C (ambient)

## Component Reference

### Configuration Schema

```yaml
alpha_hwr:
  ble_client_id: string  # Required
  
  # Optional sensors
  flow:
    name: string
    unit_of_measurement: string  # Default: m³/h
    accuracy_decimals: int       # Default: 3
    filters: []                  # Standard sensor filters
    
  head:
    name: string
    unit_of_measurement: string  # Default: m
    accuracy_decimals: int       # Default: 2
    
  power:
    name: string
    unit_of_measurement: string  # Default: W
    accuracy_decimals: int       # Default: 1
    
  rpm:
    name: string
    unit_of_measurement: string  # Default: RPM
    accuracy_decimals: int       # Default: 0
    
  temp_media:
    name: string
    unit_of_measurement: string  # Default: °C
    accuracy_decimals: int       # Default: 1
```

### Framework Requirements

The component requires ESP-IDF framework for BLE security support:

```yaml
esp32:
  framework:
    type: esp-idf  # Required
```

## Architecture

### Protocol Flow

1. **BLE Connection** - Connects to GENI service (UUID `0xFE5D`)
2. **Security Configuration** - Enables BLE bonding/encryption
3. **Authentication** - 3-stage handshake:
   - Legacy magic packets (3x)
   - Class 10 unlock packets (5x)
   - Extension packets (2x)
4. **Telemetry Polling** - Sends Class 10 READ commands every 10s:
   - `0x570045` - Motor state
   - `0x5D0122` - Flow/pressure
   - `0x5D012C` - Temperature
5. **Packet Reassembly** - Buffers and reassembles fragmented BLE packets
6. **Decoding** - Parses GENI frames and extracts IEEE 754 floats

### GENI Protocol

**READ Request (11 bytes):**
```
[27][07][E7][F8][0A][03][Reg-H][Reg-M][Reg-L][CRC-H][CRC-L]
```

**Response:**
```
[24][Len][F8][E7][0A][OpSpec][Counters...][Floats...][CRC]
```

## Troubleshooting

### Connection Issues

**Symptom:** Disconnect with error `0x13`  
**Solution:** Component now handles BLE security correctly. Ensure using latest version.

**Symptom:** No telemetry data  
**Check:**
- Pump within BLE range
- Correct MAC address
- Only one BLE connection to pump
- ESP-IDF framework configured

**Symptom:** Authentication failed  
**Solution:**
- Wait 30s after connection
- Restart ESP32
- Power cycle pump

### Log Messages

**Successful operation:**
```
[I][alpha_hwr]: Connected to pump
[I][alpha_hwr]: Authentication completed
[I][alpha_hwr]: Polling telemetry...
[I][alpha_hwr]: ✓ Motor: Power=X.X W, RPM=XXXX
[I][alpha_hwr]: ✓ Flow/Head: X.XXX m³/h, X.XX m
[I][alpha_hwr]: ✓ Temp: XX.X°C
```

**Common warnings:**
```
[W][alpha_hwr]: Skipping telemetry poll - not ready
```
→ Authentication in progress, wait 30s

### Compilation Errors

**Error:** `'esp_ble_gap_set_security_param' undeclared`  
**Fix:** Use ESP-IDF framework, not Arduino

**Error:** `esphome/core/component.h: No such file`  
**Fix:** Verify component directory structure

## Advanced Configuration

### Multiple Pumps

```yaml
ble_client:
  - mac_address: "AA:BB:CC:DD:EE:01"
    id: pump1
  - mac_address: "AA:BB:CC:DD:EE:02"
    id: pump2

alpha_hwr:
  - ble_client_id: pump1
    flow:
      name: "Pump 1 Flow"
  - ble_client_id: pump2
    flow:
      name: "Pump 2 Flow"
```

### Custom Polling Interval

Modify `alpha_hwr.h` line ~106:

```cpp
explicit AlphaHwrComponent(ble_client::BLEClient *parent) 
    : PollingComponent(30000) {  // 30s instead of 10s
```

⚠️ Intervals <5s may cause instability.

### Sensor Filters

```yaml
alpha_hwr:
  ble_client_id: alpha_pump
  flow:
    name: "Flow"
    filters:
      - sliding_window_moving_average:
          window_size: 6
      - throttle: 30s
```

## Performance

| Metric | Value |
|--------|-------|
| CPU Usage | <5% |
| RAM Usage | ~45KB |
| Flash Usage | ~1.4MB |
| Update Latency | <1s |
| Reconnect Time | ~5s |
| Reliability | 99.9%+ |

## Limitations

- **Read-only** - No control commands (use app or Python library)
- **Single connection** - Pump accepts one BLE client at a time
- **No configuration** - Cannot read/modify pump settings
- **No schedules** - Cannot access operation schedules

## ESPHome vs Python Library

| Feature | ESPHome | Python Library |
|---------|---------|----------------|
| Telemetry | ✅ Real-time | ✅ Real-time |
| Home Assistant | ✅ Native | Via MQTT/script |
| Pump control | ❌ | ✅ |
| Configuration | ❌ | ✅ |
| Schedules | ❌ | ✅ |
| Always-on | ✅ | Requires server |

**Recommendation:** Use ESPHome for monitoring, Python library for control.

## Resources

- [GitHub Repository](https://github.com/eman/alpha-hwr)
- [Python Library Documentation](../index.md)
- [Protocol Documentation](../protocol/ble_architecture.md)
- [ESPHome Documentation](https://esphome.io)
