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
CODEOWNERS = ["@your-username"]

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
// Full 256-entry table available in protocol documentation
static const uint16_t CRC16_TABLE[256] = {
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
    0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
    0x2463, 0x3442, 0x0421, 0x1400, 0x64E7, 0x74C6, 0x44A5, 0x5484,
    0xA56B, 0xB54A, 0x8529, 0x9508, 0xE5EF, 0xF5CE, 0xC5AD, 0xD58C,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
    0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
    0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
    0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12,
    0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
    0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
    0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
    0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
    0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
    0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
    0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
    0x02B1, 0x1290, 0x22D3, 0x32F2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
    0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
    0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
    0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A,
    0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
    0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DC8, 0x8DE9,
    0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
    0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
    0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0
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
  uint16_t crc = calc_crc16(packet + 1, 8);
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
  - mac_address: "AA:BB:CC:DD:EE:FF"  # Replace with your pump's actual MAC address
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
  - mac_address: "AA:BB:CC:DD:EE:01"  # Replace with pump 1's actual MAC address
    id: pump1
  - mac_address: "AA:BB:CC:DD:EE:02"  # Replace with pump 2's actual MAC address
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
