# ESPHome Integration

Reference documentation for integrating Grundfos ALPHA HWR pumps with ESPHome and Home Assistant.

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
- ESPHome with ESP-IDF framework (required for BLE security)
- Pump within BLE range (~10m)

## Component Implementation

The component consists of three files that work together to implement the GENI protocol over BLE.

### File Structure

```
custom_components/
└── alpha_hwr/
    ├── __init__.py      # Component registration
    ├── alpha_hwr.h      # C++ header with protocol constants
    └── alpha_hwr.cpp    # Main implementation
```

### 1. Component Registration (`__init__.py`)

```python
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor, ble_client
from esphome.const import (
    CONF_ID,
    UNIT_CELSIUS,
    UNIT_WATT,
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_POWER,
    STATE_CLASS_MEASUREMENT,
)

DEPENDENCIES = ["ble_client"]
CODEOWNERS = ["@your-github"]

alpha_hwr_ns = cg.esphome_ns.namespace("alpha_hwr")
AlphaHwrComponent = alpha_hwr_ns.class_(
    "AlphaHwrComponent", cg.PollingComponent, ble_client.BLEClientNode
)

CONF_FLOW = "flow"
CONF_HEAD = "head"
CONF_POWER = "power"
CONF_RPM = "rpm"
CONF_TEMP_MEDIA = "temp_media"

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(AlphaHwrComponent),
    cv.Optional(CONF_FLOW): sensor.sensor_schema(
        unit_of_measurement="m³/h",
        accuracy_decimals=3,
        state_class=STATE_CLASS_MEASUREMENT,
    ),
    cv.Optional(CONF_HEAD): sensor.sensor_schema(
        unit_of_measurement="m",
        accuracy_decimals=2,
        state_class=STATE_CLASS_MEASUREMENT,
    ),
    cv.Optional(CONF_POWER): sensor.sensor_schema(
        unit_of_measurement=UNIT_WATT,
        accuracy_decimals=1,
        device_class=DEVICE_CLASS_POWER,
        state_class=STATE_CLASS_MEASUREMENT,
    ),
    cv.Optional(CONF_RPM): sensor.sensor_schema(
        unit_of_measurement="RPM",
        accuracy_decimals=0,
        state_class=STATE_CLASS_MEASUREMENT,
    ),
    cv.Optional(CONF_TEMP_MEDIA): sensor.sensor_schema(
        unit_of_measurement=UNIT_CELSIUS,
        accuracy_decimals=1,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
    ),
}).extend(ble_client.BLE_CLIENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await ble_client.register_ble_node(var, config)

    if CONF_FLOW in config:
        sens = await sensor.new_sensor(config[CONF_FLOW])
        cg.add(var.set_flow_sensor(sens))
    if CONF_HEAD in config:
        sens = await sensor.new_sensor(config[CONF_HEAD])
        cg.add(var.set_head_sensor(sens))
    if CONF_POWER in config:
        sens = await sensor.new_sensor(config[CONF_POWER])
        cg.add(var.set_power_sensor(sens))
    if CONF_RPM in config:
        sens = await sensor.new_sensor(config[CONF_RPM])
        cg.add(var.set_rpm_sensor(sens))
    if CONF_TEMP_MEDIA in config:
        sens = await sensor.new_sensor(config[CONF_TEMP_MEDIA])
        cg.add(var.set_temp_media_sensor(sens))
```

### 2. Protocol Constants (`alpha_hwr.h`)

Key sections of the header file:

```cpp
#pragma once

#include "esphome/core/component.h"
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/sensor/sensor.h"
#include <esp_gattc_api.h>
#include <esp_gap_ble_api.h>
#include <esp_bt_defs.h>

namespace esphome {
namespace alpha_hwr {

static const char *TAG = "alpha_hwr";

// GENI Service UUIDs
static const uint16_t GRUNDFOS_SERVICE_UUID = 0xFE5D;
static ESPBTUUID GENI_CHAR_UUID = 
    ESPBTUUID::from_raw("859cffd1-036e-432a-aa28-1a0085b87ba9");

// Authentication packets
static const uint8_t AUTH_LEGACY[] = {
    0x27, 0x07, 0xE7, 0xF8, 0x02, 0x03, 0x94, 0x95, 0x96, 0xEB, 0x47
};
static const uint8_t AUTH_CLASS10[] = {
    0x27, 0x07, 0xE7, 0xF8, 0x0A, 0x03, 0x56, 0x00, 0x06, 0xC5, 0x5A
};
static const uint8_t AUTH_EXT_1[] = {
    0x27, 0x05, 0xE7, 0xF8, 0x05, 0xC1, 0x4B, 0xC3, 0x82
};
static const uint8_t AUTH_EXT_2[] = {
    0x27, 0x05, 0xE7, 0xF8, 0x0B, 0xC1, 0x0F, 0xD0, 0xC3
};

// CRC-16-CCITT lookup table for GENI protocol
static const uint16_t CRC16_TABLE[256] = {
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    // ... (full table in actual implementation)
};

class AlphaHwrComponent : public PollingComponent, public ble_client::BLEClientNode {
 public:
  explicit AlphaHwrComponent(ble_client::BLEClient *parent) : PollingComponent(10000) {
    parent->register_ble_node(this);
    parent_ = parent;
  }

  void set_flow_sensor(sensor::Sensor *sensor) { flow_sensor_ = sensor; }
  void set_head_sensor(sensor::Sensor *sensor) { head_sensor_ = sensor; }
  void set_power_sensor(sensor::Sensor *sensor) { power_sensor_ = sensor; }
  void set_rpm_sensor(sensor::Sensor *sensor) { rpm_sensor_ = sensor; }
  void set_temp_media_sensor(sensor::Sensor *sensor) { temp_media_sensor_ = sensor; }

  void setup() override;
  void loop() override;
  void update() override;
  void gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                           esp_ble_gattc_cb_param_t *param) override;
  void gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) override;

 private:
  ble_client::BLEClient *parent_;
  sensor::Sensor *flow_sensor_{nullptr};
  sensor::Sensor *head_sensor_{nullptr};
  sensor::Sensor *power_sensor_{nullptr};
  sensor::Sensor *rpm_sensor_{nullptr};
  sensor::Sensor *temp_media_sensor_{nullptr};
  
  // Protocol implementation
  float read_float_be(uint8_t *data, size_t offset);
  void decode_packet(uint8_t *data, size_t len);
  void authenticate();
  void send_auth_packet(const uint8_t *data, size_t len);
  void subscribe_to_notifications();
  void poll_telemetry();
  void send_read_request(uint32_t register_addr);
  uint16_t calc_crc16(const uint8_t *data, size_t len);
  
  // State tracking
  bool authenticated_ = false;
  bool subscribed_ = false;
  
  // Packet reassembly for multi-packet BLE responses
  std::vector<uint8_t> reassembly_buffer_;
  uint8_t expected_packet_length_ = 0;
  bool reassembling_ = false;
};

}  // namespace alpha_hwr
}  // namespace esphome
```

### 3. Implementation Highlights (`alpha_hwr.cpp`)

#### BLE Security Configuration

Critical for preventing disconnections:

```cpp
void AlphaHwrComponent::setup() {
  // Configure BLE security - prevents disconnect issue (0x13 error)
  esp_ble_io_cap_t iocap = ESP_IO_CAP_NONE;
  esp_ble_gap_set_security_param(ESP_BLE_SM_IOCAP_MODE, &iocap, sizeof(uint8_t));

  uint8_t auth_req = ESP_LE_AUTH_REQ_SC_BOND;
  esp_ble_gap_set_security_param(ESP_BLE_SM_AUTHEN_REQ_MODE, &auth_req, sizeof(uint8_t));

  uint8_t key_size = 16;
  esp_ble_gap_set_security_param(ESP_BLE_SM_MAX_KEY_SIZE, &key_size, sizeof(uint8_t));
  esp_ble_gap_set_security_param(ESP_BLE_SM_MIN_KEY_SIZE, &key_size, sizeof(uint8_t));
  
  ESP_LOGI(TAG, "BLE security configured (bonding enabled)");
}
```

#### Three-Stage Authentication

```cpp
void AlphaHwrComponent::authenticate() {
  // Stage 1: Legacy magic burst (3x)
  for (int i = 0; i < 3; i++) {
    send_auth_packet(AUTH_LEGACY, sizeof(AUTH_LEGACY));
    delay(50);
  }
  
  // Stage 2: Class 10 unlock burst (5x)
  for (int i = 0; i < 5; i++) {
    send_auth_packet(AUTH_CLASS10, sizeof(AUTH_CLASS10));
    delay(50);
  }
  
  // Stage 3: Extensions (2x)
  send_auth_packet(AUTH_EXT_1, sizeof(AUTH_EXT_1));
  delay(50);
  send_auth_packet(AUTH_EXT_2, sizeof(AUTH_EXT_2));
  delay(500);
  
  authenticated_ = true;
  ESP_LOGI(TAG, "Authentication completed");
}
```

#### Active Telemetry Polling

Pump requires polling, not passive listening:

```cpp
void AlphaHwrComponent::poll_telemetry() {
  ESP_LOGI(TAG, "Polling telemetry...");
  
  // Request motor state (0x570045)
  send_read_request(0x570045);
  
  // Request flow/pressure (0x5D0122)
  this->set_timeout(100, [this]() {
    send_read_request(0x5D0122);
  });
  
  // Request temperature (0x5D012C)
  this->set_timeout(200, [this]() {
    send_read_request(0x5D012C);
  });
}

void AlphaHwrComponent::update() {
  // Called every 10 seconds by PollingComponent
  if (authenticated_ && parent_ && parent_->get_conn_id() != 0xFF) {
    poll_telemetry();
  }
}
```

#### Building READ Requests

```cpp
void AlphaHwrComponent::send_read_request(uint32_t register_addr) {
  uint8_t packet[11];
  
  // Frame structure: [27][07][E7][F8][0A][03][Reg-H][Reg-M][Reg-L][CRC-H][CRC-L]
  packet[0] = 0x27;  // Frame start (request)
  packet[1] = 0x07;  // Length
  packet[2] = 0xE7;  // Service ID high
  packet[3] = 0xF8;  // Source
  packet[4] = 0x0A;  // Class 10
  packet[5] = 0x03;  // OpSpec (READ)
  packet[6] = (register_addr >> 16) & 0xFF;  // Register high byte
  packet[7] = (register_addr >> 8) & 0xFF;   // Register mid byte
  packet[8] = register_addr & 0xFF;          // Register low byte
  
  // Calculate CRC-16-CCITT over bytes 1-8, XOR result with 0xFFFF
  uint16_t crc = calc_crc16_read(packet + 1, 8);
  packet[9] = (crc >> 8) & 0xFF;   // CRC high byte
  packet[10] = crc & 0xFF;         // CRC low byte
  
  // Send via BLE characteristic
  auto *chr = parent_->get_characteristic(GRUNDFOS_SERVICE_UUID, GENI_CHAR_UUID);
  if (chr) {
    auto status = esp_ble_gattc_write_char(
        parent_->get_gattc_if(),
        parent_->get_conn_id(),
        chr->handle,
        sizeof(packet),
        packet,
        ESP_GATT_WRITE_TYPE_NO_RSP,
        ESP_GATT_AUTH_REQ_NONE);
  }
}
```

#### Packet Reassembly

Handles BLE 20-byte MTU limitation:

```cpp
case ESP_GATTC_NOTIFY_EVT: {
  auto *notify_evt = &param->notify;
  if (notify_evt->value_len > 0) {
    // Check if this is start of new packet (frame byte 0x24 or 0x27)
    if (notify_evt->value[0] == 0x24 || notify_evt->value[0] == 0x27) {
      if (notify_evt->value_len >= 2) {
        expected_packet_length_ = notify_evt->value[1] + 2;
      }
      reassembly_buffer_.clear();
      reassembly_buffer_.insert(reassembly_buffer_.end(), 
                               notify_evt->value, 
                               notify_evt->value + notify_evt->value_len);
      reassembling_ = true;
    } else if (reassembling_) {
      // Continuation packet
      reassembly_buffer_.insert(reassembly_buffer_.end(), 
                               notify_evt->value, 
                               notify_evt->value + notify_evt->value_len);
    }
    
    // Check if packet is complete
    if (reassembling_ && reassembly_buffer_.size() >= expected_packet_length_) {
      decode_packet(reassembly_buffer_.data(), reassembly_buffer_.size());
      reassembling_ = false;
      reassembly_buffer_.clear();
    }
  }
  break;
}
```

#### Response Decoding

```cpp
void AlphaHwrComponent::decode_packet(uint8_t *data, size_t len) {
  if (len < 10) return;
  
  // Check frame type (0x24 = response) and class (0x0A = Class 10)
  if (data[0] != 0x24 || data[4] != 0x0A) return;
  
  uint8_t opspec = data[5];
  
  // Motor state response (OpSpec 0x30)
  if (opspec == 0x30 && len >= 37) {
    // Floats start at offset 13
    float power = read_float_be(data, 25);  // Float[3] at offset 13+12
    float rpm = read_float_be(data, 33);    // Float[5] at offset 13+20
    
    if (power >= 0 && power <= 1000 && rpm >= 0 && rpm <= 10000) {
      if (power_sensor_) power_sensor_->publish_state(power);
      if (rpm_sensor_) rpm_sensor_->publish_state(rpm);
    }
  }
  
  // Flow/pressure response (OpSpec 0x2B)
  else if (opspec == 0x2B && len >= 45) {
    float flow = read_float_be(data, 37);  // Float[6] at offset 13+24
    float head = read_float_be(data, 41);  // Float[7] at offset 13+28
    
    if (flow >= 0 && flow <= 100 && head >= 0 && head <= 50) {
      if (flow_sensor_) flow_sensor_->publish_state(flow);
      if (head_sensor_) head_sensor_->publish_state(head);
    }
  }
  
  // Temperature response (OpSpec 0x14)
  else if (opspec == 0x14 && len >= 21) {
    float temp = read_float_be(data, 13);  // Single float at offset 13
    
    if (temp >= -50 && temp <= 150) {
      if (temp_media_sensor_) temp_media_sensor_->publish_state(temp);
    }
  }
}

float AlphaHwrComponent::read_float_be(uint8_t *data, size_t offset) {
  // Read IEEE 754 big-endian float
  uint32_t temp = (data[offset] << 24) | (data[offset+1] << 16) | 
                  (data[offset+2] << 8) | data[offset+3];
  float val;
  memcpy(&val, &temp, 4);
  return val;
}
```

## Configuration

### ESPHome YAML

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

## Protocol Reference

### GENI Frame Structure

**READ Request (11 bytes):**
```
[27] [07] [E7] [F8] [0A] [03] [Reg-H] [Reg-M] [Reg-L] [CRC-H] [CRC-L]
 ^    ^    ^    ^    ^    ^    ^--------register-------^  ^----CRC----^
 |    |    |    |    |    |
 |    |    |    |    |    OpSpec (0x03 = READ)
 |    |    |    |    Class 10
 |    |    |    Source (0xF8)
 |    |    Service ID High (0xE7)
 |    Length (7 bytes)
 Frame Start (0x27 for requests)
```

**Response:**
```
[24] [Len] [F8] [E7] [0A] [OpSpec] [Counters(6)] [Res(2)] [Floats...] [CRC(2)]
 ^    ^                    ^                                ^
 |    |                    |                                Data starts at offset 13
 |    |                    Response OpSpec
 |    Total length
 Response Frame (0x24)
```

### Register Map

| Register | Description | OpSpec | Data |
|----------|-------------|--------|------|
| `0x570045` | Motor state | 0x30 | Power (W), RPM |
| `0x5D0122` | Flow/pressure | 0x2B | Flow (m³/h), Head (m) |
| `0x5D012C` | Temperature | 0x14 | Media temp (°C) |

### CRC Calculation

CRC-16-CCITT with initial value 0xFFFF:
- For READ requests: XOR final result with 0xFFFF
- Calculate over length through register bytes (not including frame start or CRC)

## Troubleshooting

### Connection Issues

**Disconnect with error 0x13:** Ensure BLE security is configured in `setup()`.

**No telemetry:** Check authentication completed and polling is active every 10 seconds.

**Compilation errors:** Must use ESP-IDF framework, not Arduino.

### Log Messages

Successful operation:
```
[I][alpha_hwr]: BLE security configured (bonding enabled)
[I][alpha_hwr]: Connected to pump
[I][alpha_hwr]: Authentication completed
[I][alpha_hwr]: Polling telemetry...
[I][alpha_hwr]: Motor: Power=0.0 W, RPM=0
[I][alpha_hwr]: Flow/Head: 0.000 m³/h, 0.00 m
[I][alpha_hwr]: Temp: 18.3°C
```

## Advanced Topics

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

Modify `alpha_hwr.h` constructor:
```cpp
explicit AlphaHwrComponent(ble_client::BLEClient *parent) 
    : PollingComponent(30000) {  // 30s instead of 10s
```

### Additional Registers

The pump exposes many more registers. Add to `poll_telemetry()`:
```cpp
send_read_request(0x570001);  // Voltages
send_read_request(0x570002);  // Current
```

Then add corresponding decode cases in `decode_packet()`.

## Limitations

- Read-only telemetry (no control commands)
- Single BLE connection to pump at a time
- Cannot read/modify pump configuration
- Cannot access operation schedules

For pump control, use the Python library or mobile app.

## Resources

- [Python Library Documentation](../index.md)
- [Protocol Documentation](../protocol/ble_architecture.md)
- [ESPHome Documentation](https://esphome.io)
- [GitHub Repository](https://github.com/eman/alpha-hwr)
