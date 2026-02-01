# ESPHome / ESP32 Integration

This guide demonstrates how to connect a Grundfos ALPHA HWR pump to **ESPHome** using an ESP32 microcontroller. This allows you to bridge the pump's Bluetooth LE interface to WiFi (MQTT, Home Assistant API) for local monitoring.

!!! warning "Advanced Topic"
    This integration uses a **Custom C++ Component** in ESPHome. It requires some familiarity with ESPHome's `lambda` and C++ includes mechanism.

## Overview

Because the ALPHA HWR uses the GENI protocol encapsulated in BLE, and requires a specific "Authentication Handshake" to start streaming data, the standard ESPHome `ble_client` sensors are not sufficient.

We must use a custom component that:
1.  Connects to the pump.
2.  Sends the "Magic Packet" handshake to unlock the device.
3.  Decodes the binary Class 10 GENI packets into float values.

## 1. The Custom Component (`alpha_hwr.h`)

Create a file named `alpha_hwr.h` in your ESPHome configuration directory (next to your `pump.yaml`).

This C++ code handles the connection logic and protocol parsing.

```cpp
#include "esphome.h"
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"

using namespace esphome;
using namespace esphome::ble_client;

// GENI UUIDs
static const esp32_ble_tracker::ESPBTUUID GENI_SERVICE_UUID = 
    esp32_ble_tracker::ESPBTUUID::from_raw("0000fe5d-0000-1000-8000-00805f9b34fb");
static const esp32_ble_tracker::ESPBTUUID GENI_CHAR_UUID = 
    esp32_ble_tracker::ESPBTUUID::from_raw("859cffd1-036e-432a-aa28-1a0085b87ba9");

// Authentication Packets
static const uint8_t AUTH_LEGACY[] = {0x27, 0x07, 0xE7, 0xF8, 0x02, 0x03, 0x94, 0x95, 0x96, 0xEB, 0x47};
static const uint8_t AUTH_CLASS10[] = {0x27, 0x07, 0xE7, 0xF8, 0x0A, 0x03, 0x56, 0x00, 0x06, 0xC5, 0x5A};
static const uint8_t AUTH_EXT_1[] = {0x27, 0x05, 0xE7, 0xF8, 0x05, 0xC1, 0x4B, 0xC3, 0x82};
static const uint8_t AUTH_EXT_2[] = {0x27, 0x05, 0xE7, 0xF8, 0x0B, 0xC1, 0x0F, 0xD0, 0xC3};

class AlphaHwrComponent : public PollingComponent, public BLEClientNode {
 public:
  Sensor *flow_sensor = new Sensor();
  Sensor *head_sensor = new Sensor();
  Sensor *power_sensor = new Sensor();
  Sensor *rpm_sensor = new Sensor();
  Sensor *temp_media_sensor = new Sensor();

  AlphaHwrComponent() : PollingComponent(10000) {} // Poll loop not heavily used, data is pushed

  void setup() override {
    // Initialize
  }

  void loop() override {
    // Keep-alive or re-auth logic could go here
  }

  void gatt_startup() override {
    // Called when BLE client is connected and services discovered
    ESP_LOGI("alpha_hwr", "BLE Connected. Starting Authentication...");
    
    auto *chr = this->parent()->get_characteristic(GENI_SERVICE_UUID, GENI_CHAR_UUID);
    if (chr == nullptr) {
      ESP_LOGE("alpha_hwr", "GENI Characteristic not found!");
      return;
    }

    // Send Authentication Sequence
    // Note: In a real robust implementation, we should chain these with callbacks or delays.
    // For simplicity, we fire them quickly. ESP32 BLE queue usually handles this okay.
    
    // 1. Legacy Magic Burst
    for(int i=0; i<3; i++) chr->write_value((uint8_t*)AUTH_LEGACY, sizeof(AUTH_LEGACY));
    
    // 2. Class 10 Unlock Burst
    for(int i=0; i<5; i++) chr->write_value((uint8_t*)AUTH_CLASS10, sizeof(AUTH_CLASS10));
    
    // 3. Extensions
    chr->write_value((uint8_t*)AUTH_EXT_1, sizeof(AUTH_EXT_1));
    chr->write_value((uint8_t*)AUTH_EXT_2, sizeof(AUTH_EXT_2));
    
    ESP_LOGI("alpha_hwr", "Authentication frames sent.");
  }

  void on_ble_client_node_notify(esp32_ble_tracker::ESPBTUUID uuid, uint8_t *data, size_t length) override {
    if (uuid == GENI_CHAR_UUID) {
      this->decode_packet(data, length);
    }
  }

  // Helper to read Big Endian Float
  float read_float_be(uint8_t *data, size_t offset) {
    if (offset + 4 > 255) return 0.0f; // Safety
    uint32_t temp = (data[offset] << 24) | (data[offset+1] << 16) | (data[offset+2] << 8) | data[offset+3];
    float val;
    memcpy(&val, &temp, 4);
    return val;
  }

  void decode_packet(uint8_t *data, size_t len) {
    if (len < 10) return;
    
    // Check Frame Start (0x24 for Response) and Class (0x0A for Class 10)
    if (data[0] != 0x24 || data[4] != 0x0A) return;

    uint8_t opspec = data[5];

    // 1. Passive Notifications (OpSpec 0x0E)
    // Structure: [Class][OpSpec][SubID(2)][ObjID(2)][Data...]
    if (opspec == 0x0E) {
        uint16_t sub_id = (data[6] << 8) | data[7];
        uint16_t obj_id = (data[8] << 8) | data[9];
        
        // Payload starts at index 10
        if (sub_id == 0x0045 && obj_id == 0x0057) { // Motor State
            if (len >= 34) {
                 power_sensor->publish_state(read_float_be(data, 26)); // +16
                 rpm_sensor->publish_state(read_float_be(data, 30));   // +20
            }
        }
        else if (sub_id == 0x0122 && obj_id == 0x005D) { // Flow/Head
            if (len >= 18) {
                 flow_sensor->publish_state(read_float_be(data, 10)); // +0
                 head_sensor->publish_state(read_float_be(data, 14)); // +4
            }
        }
        else if (sub_id == 0x012C && obj_id == 0x005D) { // Temperature
            if (len >= 14) temp_media_sensor->publish_state(read_float_be(data, 10)); // +0
        }
    }
    // 2. Query Responses (OpSpec 0x2B, 0x30, etc.)
    // Structure: [Class][Op][Seq(2)][ID(2)][Res(2)][DataLen(1)][Data...]
    // Note: Offsets differ here! Data starts at index 13.
    else if (opspec == 0x2B) { // Flow query response
        if (len >= 41) {
             // Flow is at index 6 in the float array (13 + 6*4 = 37)
             flow_sensor->publish_state(read_float_be(data, 37));
             // Head is at index 7 (13 + 7*4 = 41)
             head_sensor->publish_state(read_float_be(data, 41));
        }
    }
  }
};
```

## 2. ESPHome Configuration (`pump.yaml`)

Now, configure your ESPHome node to include this file and register the sensors.

```yaml
esphome:
  name: alpha-hwr-bridge
  platform: ESP32
  board: esp32dev
  
  # Include the custom component header
  includes:
    - alpha_hwr.h

# Enable Logging
logger:

# Enable Bluetooth Tracker
esp32_ble_tracker:

# Define the BLE Client connection to the pump
ble_client:
  - mac_address: AA:BB:CC:DD:EE:FF  # <--- REPLACE WITH YOUR PUMP MAC ADDRESS
    id: alpha_pump_client

# Register the Custom Component as a Sensor platform
sensor:
  - platform: custom
    lambda: |-
      auto my_pump = new AlphaHwrComponent();
      // Link the component to the BLE client
      my_pump->set_ble_client_parent(id(alpha_pump_client));
      App.register_component(my_pump);
      return {
        my_pump->flow_sensor, 
        my_pump->head_sensor, 
        my_pump->power_sensor, 
        my_pump->rpm_sensor,
        my_pump->temp_media_sensor
      };
    sensors:
      - name: "Alpha HWR Flow"
        unit_of_measurement: "m³/h"
        accuracy_decimals: 3
      - name: "Alpha HWR Head"
        unit_of_measurement: "m"
        accuracy_decimals: 2
      - name: "Alpha HWR Power"
        unit_of_measurement: "W"
        accuracy_decimals: 1
      - name: "Alpha HWR RPM"
        unit_of_measurement: "RPM"
        accuracy_decimals: 0
      - name: "Alpha HWR Temperature"
        unit_of_measurement: "°C"
        accuracy_decimals: 1
```

## 3. Usage

1.  Flash this configuration to your ESP32.
2.  Once booted, the ESP32 will scan for the MAC address defined.
3.  Upon connection, it will send the authentication packets.
4.  As the pump streams data, the sensors in Home Assistant (or MQTT) will update in real-time.

## Limitations

*   **Fragmentation**: This example does not implement the split-write logic required for **Control Commands** (Start/Stop). It is primarily for telemetry. Implementing robust fragmentation in a simple ESPHome header is complex and may cause stability issues.
*   **Reconnection**: While `ble_client` handles reconnection, the authentication sequence needs to run *every time* it reconnects. The `gatt_startup` method handles this, but robust error recovery might need more logic.

---

## Advanced Example: Control and Robustness

This advanced example includes:
- **Packet Splitting**: Helper to send >20 byte packets.
- **Control**: Switches to Start/Stop the pump.
- **Robustness**: Better connection handling and reconnection logic.

### `alpha_hwr_advanced.h`

```cpp
#include "esphome.h"
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"

using namespace esphome;
using namespace esphome::ble_client;

static const esp32_ble_tracker::ESPBTUUID GENI_SERVICE_UUID = 
    esp32_ble_tracker::ESPBTUUID::from_raw("0000fe5d-0000-1000-8000-00805f9b34fb");
static const esp32_ble_tracker::ESPBTUUID GENI_CHAR_UUID = 
    esp32_ble_tracker::ESPBTUUID::from_raw("859cffd1-036e-432a-aa28-1a0085b87ba9");

// Auth Packets
static const uint8_t AUTH_LEGACY[] = {0x27, 0x07, 0xE7, 0xF8, 0x02, 0x03, 0x94, 0x95, 0x96, 0xEB, 0x47};
static const uint8_t AUTH_CLASS10[] = {0x27, 0x07, 0xE7, 0xF8, 0x0A, 0x03, 0x56, 0x00, 0x06, 0xC5, 0x5A};
static const uint8_t AUTH_EXT_1[] = {0x27, 0x05, 0xE7, 0xF8, 0x05, 0xC1, 0x4B, 0xC3, 0x82};
static const uint8_t AUTH_EXT_2[] = {0x27, 0x05, 0xE7, 0xF8, 0x0B, 0xC1, 0x0F, 0xD0, 0xC3};

// Control Packets
// Start (Class 10, Sub 5600, Obj 0601) - 24 bytes
static const uint8_t CMD_START[] = {
    0x27, 0x14, 0xE7, 0xF8, 0x0A, 0x90, 0x56, 0x00, 
    0x06, 0x01, 0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 
    0x00, 0x02, 0x45, 0x65, 0x70, 0x00, 0x79, 0x2F
};

// Stop (Class 10, Sub 5600, Obj 0601) - 24 bytes
static const uint8_t CMD_STOP[] = {
    0x27, 0x14, 0xE7, 0xF8, 0x0A, 0x90, 0x56, 0x00, 
    0x06, 0x01, 0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 
    0x01, 0x02, 0x45, 0x65, 0x70, 0x00, 0x3C, 0x8F
};

class AlphaHwrAdvanced : public PollingComponent, public BLEClientNode {
 public:
  Sensor *flow_sensor = new Sensor();
  Sensor *power_sensor = new Sensor();
  Switch *pump_switch = new Switch(); // Pump control switch

  AlphaHwrAdvanced() : PollingComponent(10000) {}

  void setup() override {
    // Register switch callbacks
    pump_switch->add_on_turn_on_callback([this]() { this->send_control(true); });
    pump_switch->add_on_turn_off_callback([this]() { this->send_control(false); });
  }

  void loop() override {}

  void gatt_startup() override {
    ESP_LOGI("alpha_hwr", "Connected. Authenticating...");
    auto *chr = this->parent()->get_characteristic(GENI_SERVICE_UUID, GENI_CHAR_UUID);
    if (!chr) return;

    // Authenticate
    for(int i=0; i<3; i++) { chr->write_value((uint8_t*)AUTH_LEGACY, sizeof(AUTH_LEGACY)); delay(50); }
    for(int i=0; i<5; i++) { chr->write_value((uint8_t*)AUTH_CLASS10, sizeof(AUTH_CLASS10)); delay(50); }
    chr->write_value((uint8_t*)AUTH_EXT_1, sizeof(AUTH_EXT_1)); delay(50);
    chr->write_value((uint8_t*)AUTH_EXT_2, sizeof(AUTH_EXT_2)); delay(100);
    
    ESP_LOGI("alpha_hwr", "Authenticated.");
  }

  void on_ble_client_node_notify(esp32_ble_tracker::ESPBTUUID uuid, uint8_t *data, size_t length) override {
    if (uuid == GENI_CHAR_UUID) this->decode_packet(data, length);
  }

  // Helper to split packets > 20 bytes
  void write_split_packet(const uint8_t* packet, size_t len) {
    auto *chr = this->parent()->get_characteristic(GENI_SERVICE_UUID, GENI_CHAR_UUID);
    if (!chr) return;

    if (len <= 20) {
        chr->write_value((uint8_t*)packet, len);
    } else {
        // Chunk 1
        chr->write_value((uint8_t*)packet, 20);
        delay(20); // Critical delay for pump processing
        // Chunk 2
        chr->write_value((uint8_t*)packet + 20, len - 20);
    }
  }

  void send_control(bool turn_on) {
    ESP_LOGI("alpha_hwr", "Sending control command: %s", turn_on ? "ON" : "OFF");
    if (turn_on) {
        write_split_packet(CMD_START, sizeof(CMD_START));
        pump_switch->publish_state(true);
    } else {
        write_split_packet(CMD_STOP, sizeof(CMD_STOP));
        pump_switch->publish_state(false);
    }
  }

  float read_float_be(uint8_t *data, size_t offset) {
    uint32_t temp = (data[offset] << 24) | (data[offset+1] << 16) | (data[offset+2] << 8) | data[offset+3];
    float val;
    memcpy(&val, &temp, 4);
    return val;
  }

  void decode_packet(uint8_t *data, size_t len) {
    if (len < 10 || data[0] != 0x24 || data[4] != 0x0A) return;
    
    uint16_t sub_id = (data[6] << 8) | data[7];
    uint16_t obj_id = (data[8] << 8) | data[9];

    // Motor State (Sub 0x45, Obj 0x57)
    if (sub_id == 0x0045 && obj_id == 0x0057 && len >= 34) {
        power_sensor->publish_state(read_float_be(data, 26)); // Power at 16 (10+16)
        
        // Update switch state based on RPM?
        // float rpm = read_float_be(data, 30);
        // pump_switch->publish_state(rpm > 0);
    }
    
    // Flow (Sub 0x122, Obj 0x5D)
    if (sub_id == 0x0122 && obj_id == 0x005D && len >= 18) {
        flow_sensor->publish_state(read_float_be(data, 10)); // Flow at 0 (10+0)
    }
  }
};
```

### Advanced Configuration

Register the switch in your YAML:

```yaml
# ... (includes alpha_hwr_advanced.h)

switch:
  - platform: custom
    lambda: |-
      // ... (setup code similar to basic example)
      return {my_pump->pump_switch};
    switches:
      - name: "Alpha HWR Control"
```
