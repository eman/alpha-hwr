# Control Modes - Complete Support Matrix

This document provides an overview of all 32 control modes defined in the GENI protocol and their support status on the Grundfos ALPHA HWR pump.

## Executive Summary

The ALPHA HWR is a **domestic hot water recirculation pump** designed for residential heating systems. Hardware testing reveals it supports **6 out of 32 control modes** - those specifically related to hot water recirculation applications.

**Support Statistics:**
-  **Fully Supported:** 6 modes (19%)
-  **Not Supported:** 26 modes (81%)

---

## Complete Mode Support Matrix

| Mode | Name | Support | SubID | Register | Notes |
|------|------|---------|-------|----------|-------|
| 0 | CONSTANT_PRESSURE |  **Full** | 15 | 0x18 | Constant head pressure |
| 1 | PROPORTIONAL_PRESSURE |  **Full** | 17 | 0x17 | Proportional pressure curve |
| 2 | CONSTANT_SPEED |  **Full** | 13 | 0x04 | Fixed RPM operation |
| 5 | AUTO_ADAPT |  Not Supported | - | - | Generic AutoAdapt (deprecated, not for DHW) |
| 7 | CLOSED_LOOP_SENSOR |  Not Supported | - | - | Generic sensor control |
| 8 | CONSTANT_FLOW |  **Full** | 39 | 0x15 | Constant flow rate |
| 9 | CONSTANT_LEVEL |  Not Supported | - | - | Water level control (tanks/sumps) |
| 10 | FLOW_ADAPT |  Not Supported | - | - | Adaptive flow control |
| 11 | CONSTANT_DIFF_PRESSURE |  Not Supported | - | - | Differential pressure sensors required |
| 12 | CONSTANT_DIFF_TEMP |  Not Supported | - | - | Temperature differential control |
| 13 | AUTO_ADAPT_RADIATOR |  Not Supported | 19 | 0x1E | Heating system mode (not DHW) |
| 14 | AUTO_ADAPT_UNDERFLOOR |  Not Supported | 21 | 0x1F | Heating system mode (not DHW) |
| 15 | AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR |  Not Supported | 23 | 0x20 | Heating system mode (not DHW) |
| 16 | CONSTANT_DOSING |  Not Supported | - | - | Chemical dosing (pools/industrial) |
| 17 | DISINFECTANT_CONTROL |  Not Supported | - | - | Chemical dosing (pools/water treatment) |
| 18 | FLOCCULENT_CONTROL |  Not Supported | - | - | Chemical dosing (water treatment) |
| 19 | PH_CONTROL |  Not Supported | - | - | pH dosing (pools/industrial) |
| 20 | PID_CONTROL |  Not Supported | - | - | Generic PID algorithm |
| 21 | CONSTANT_RELATIVE_SETPOINT |  Not Supported | - | - | Relative setpoint adjustment |
| 22 | LEVEL_CONTROL |  Not Supported | - | - | Water level control |
| 23 | ZONE_PUMP_CONTROL |  Not Supported | - | - | Multi-zone systems |
| 24 | USER_DEFINED |  Not Supported | - | - | Custom mode |
| 25 | DHW_ON_OFF_CONTROL |   **Full** | - | 0x19 | Cycle time control (on/off minutes) |
| 26 | PROPORTIONAL_DIFF_PRESSURE |  Not Supported | - | - | Differential pressure sensors required |
| 27 | TEMPERATURE_RANGE_CONTROL |  **Full** | - | - | Temperature range control (min/max) |
| 28 | COMFORT_VALVE_CONTROL |  Not Supported | - | - | Valve control |
| 29 | ON_OFF_CONTROL |  Not Supported | - | - | Simple on/off |
| 30 | CONSTANT_VOLTAGE |  Not Supported | - | - | Voltage control (industrial/testing) |
| 128 | SYSTEM_AIR_VENTING |  Not Supported | - | - | Air venting control |
| 254 | NONE | N/A | - | - | No control mode active |

---

## Supported Modes (6 modes)

### 1. Constant Pressure (Mode 0) -  Full Support

**Description:** Maintains constant head pressure regardless of flow rate.

**Use Case:** Standard residential circulation, consistent pressure delivery

**Hardware Support:**
-  SubID 15 in Object 86 (factory configuration)
-  Mode switching works reliably
-  Register 0x18 for setpoint writes
-  Limits: 0.10-4.57 m (typical)

**Implementation:**
```python
await client.set_constant_pressure(1.5)  # 1.5 meters
```

**CLI:**
```bash
alpha-hwr control set-pressure --value 1.5
```

---

### 2. Proportional Pressure (Mode 1) -  Full Support

**Description:** Adjusts pressure proportionally to flow rate along a curve.

**Use Case:** Energy-efficient operation, reduces pressure at low flow

**Hardware Support:**
-  SubID 17 in Object 86
-  Mode switching works reliably
-  Register 0x17 for setpoint writes
-  Limits: 0.10-4.57 m (typical)

**Implementation:**
```python
await client.set_proportional_pressure(1.2)  # 1.2 meters max
```

**CLI:**
```bash
alpha-hwr control set-proportional-pressure --value 1.2
```

---

### 3. Constant Speed (Mode 2) -  Full Support

**Description:** Maintains constant motor RPM regardless of system conditions.

**Use Case:** Testing, diagnostics, special applications

**Hardware Support:**
-  SubID 13 in Object 86
-  Mode switching works reliably
-  Register 0x04 for setpoint writes
-  Limits: 1000-4500 RPM (typical)

**Implementation:**
```python
await client.set_constant_speed(2500)  # 2500 RPM
```

**CLI:**
```bash
alpha-hwr control set-speed --value 2500
```

---

### 4. Constant Flow (Mode 8) -  Full Support

**Description:** Maintains constant flow rate by adjusting pump speed.

**Use Case:** Applications requiring precise flow control

**Hardware Support:**
-  SubID 39 in Object 86
-  Mode switching works reliably
-  Register 0x15 for setpoint writes
-  Limits: 0.10-3.00 m³/h (typical)

**Implementation:**
```python
await client.set_constant_flow(0.5)  # 0.5 m³/h
```

**CLI:**
```bash
alpha-hwr control set-flow --value 0.5
```

---

### 5. Temperature Control with AutoAdapt (Mode 27) - Full Support

**Description:** Temperature range control with automatic flow adjustment (AutoAdapt feature).

**Use Case:** Hot water recirculation maintaining temperature within specified range with automatic flow optimization (1-4 gpm)

**Hardware Support:**
-  **This is the ALPHA HWR's primary temperature control mode**
-  Confirmed via live hardware verification (factory default mode)
-  Uses **Object 91** (Setpoint), **SubID 430** (`0x01AE`) for configuration
-  Supports dual setpoints (Minimum and Maximum Temperature)
-  **AutoAdapt:** Flow rate automatically adjusts between 1-4 gpm based on system demand

**Implementation:**
```python
# Set temperature range: 35°C min, 39°C max
await client.set_temperature_range_control(35.0, 39.0)
```

**CLI:**
```bash
alpha-hwr control set-temperature --min 35 --max 39
```

**Note:** This mode combines temperature range control WITH the AutoAdapt flow adjustment feature. The "AutoAdapt" mentioned in ALPHA HWR documentation refers to this mode's automatic flow adjustment capability, not to modes 13/14/15 (which are for heating system pumps).

---

### 6. Cycle Time Control (Mode 25) -  Full Support

**Description:** Operates the pump in on/off cycles at configurable intervals for domestic hot water (DHW) recirculation.

**Use Case:** DHW recirculation systems where intermittent pump operation maintains water temperature while saving energy.

**Hardware Support:**
-   Mode switching works reliably (mode byte 0x19, suffix 0x38 0xC6 0x70 0x00)
-   Successfully operates on ALPHA HWR hardware
-   Supports configurable ON/OFF durations (1-60 minutes)

**Implementation:**
```python
# Set cycle times: 5 min on, 15 min off
await client.set_cycle_time_control(5, 15)
```

**CLI:**
```bash
alpha-hwr control set-cycle-time --on 5 --off 15
alpha-hwr control get-cycle-time
```

**Next Steps:**
Investigate additional advanced modes if requested by users.

---

## Unsupported Modes (26 modes)

### Why These Modes Are Not Supported

The ALPHA HWR is a **residential hot water recirculation pump**, not a general-purpose industrial pump or heating system pump. The unsupported modes fall into these categories:

#### 1. Heating System Modes (Not DHW)
- **Mode 13 (AUTO_ADAPT_RADIATOR):** For radiator heating systems, not DHW recirculation
- **Mode 14 (AUTO_ADAPT_UNDERFLOOR):** For underfloor heating systems, not DHW recirculation
- **Mode 15 (AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR):** For combined heating systems, not DHW recirculation

**Note:** The ALPHA HWR uses Mode 27 (TEMPERATURE_RANGE_CONTROL) for temperature control with AutoAdapt flow adjustment. Modes 13/14/15 are GENI protocol modes for heating system pumps.

#### 2. Sensor Requirements Not Met
- **Mode 11 (CONSTANT_DIFF_PRESSURE):** Requires differential pressure sensors
- **Mode 26 (PROPORTIONAL_DIFF_PRESSURE):** Requires differential pressure sensors
- **Mode 12 (CONSTANT_DIFF_TEMP):** Requires temperature differential sensors

#### 2. Chemical Dosing (Pools/Industrial)
- **Mode 16 (CONSTANT_DOSING):** Chemical metering pumps
- **Mode 17 (DISINFECTANT_CONTROL):** Chlorine/disinfectant dosing
- **Mode 18 (FLOCCULENT_CONTROL):** Flocculation dosing
- **Mode 19 (PH_CONTROL):** pH adjustment dosing

#### 3. Level Control (Tanks/Sumps)
- **Mode 9 (CONSTANT_LEVEL):** Water level maintenance
- **Mode 22 (LEVEL_CONTROL):** Water level regulation

#### 4. Specialized Applications
- **Mode 7 (CLOSED_LOOP_SENSOR):** Generic external sensor control
- **Mode 10 (FLOW_ADAPT):** Adaptive flow algorithms
- **Mode 20 (PID_CONTROL):** Generic PID control
- **Mode 21 (CONSTANT_RELATIVE_SETPOINT):** Relative setpoint adjustment
- **Mode 23 (ZONE_PUMP_CONTROL):** Multi-zone systems
- **Mode 24 (USER_DEFINED):** Custom control algorithms
- **Mode 28 (COMFORT_VALVE_CONTROL):** Valve control systems
- **Mode 29 (ON_OFF_CONTROL):** Simple on/off operation
- **Mode 30 (CONSTANT_VOLTAGE):** Voltage control (motor testing)
- **Mode 128 (SYSTEM_AIR_VENTING):** Automated air venting

## Technical Discovery

All 32 GENI protocol modes were systematically tested on real ALPHA HWR hardware to determine compatibility. The categories below reflect the results of this hardware-in-the-loop verification.

### Investigation Details
- **Hardware:** Grundfos ALPHA HWR (Family 52, Type 7, Version 2)
- **Tool:** `tools/probe_all_modes.py`

### Summary Table

| Category | Tested | Supported |
|----------|--------|-----------|
| Pressure/Flow Control | 4 | 4 |
| Temperature Control | 1 | 1 |
| DHW Cycle Control | 1 | 1 (limited) |
| Heating System Modes | 3 | 0 |
| Industrial/Dosing/Other | 23 | 0 |
| **Total** | **32** | **5 fully + 1 limited** |

---

## Implementation Status

### Library Support

**Fully Implemented (6 modes via Class 10):**
- `set_constant_pressure(value_m)` - Mode 0
- `set_proportional_pressure(value_m)` - Mode 1  
- `set_constant_speed(value_rpm)` - Mode 2
- `set_constant_flow(value_m3h)` - Mode 8
- `set_temperature_range_control(min_c, max_c, autoadapt=True)` - Mode 27
- `set_cycle_time_control(on_min, off_min)` - Mode 25
- `set_flow_limit(value_gpm)` - Sub 39 limitation

**Deprecated Methods (for heating systems, not ALPHA HWR):**
- `set_temperature_control(on_temp, off_temp, heating_type)` - Uses modes 13/14/15 (not for DHW)
- `set_autoadapt_radiator(value_m)` - Mode 13 (not for DHW)
- `set_autoadapt_underfloor(value_m)` - Mode 14 (not for DHW)
- `set_autoadapt_combined(value_m)` - Mode 15 (not for DHW)

**Not Implemented (26 modes):**
- Unsupported modes listed above - no methods created

### CLI Support

**Available Commands:**
```bash
alpha-hwr control set-pressure <meters>
alpha-hwr control set-proportional <meters>
alpha-hwr control set-speed <rpm> [--flow-limit <gpm>]
alpha-hwr control set-flow <m3h>
alpha-hwr control set-temperature --min <temp_c> --max <temp_c> [--autoadapt/--no-autoadapt] [--flow-limit <gpm>]
alpha-hwr control set-cycle-time --on <minutes> --off <minutes>
alpha-hwr control set-flow-limit <gpm>
alpha-hwr control get-cycle-time
```

**Deprecated Commands (removed from CLI):**

These methods still exist in the service layer for GENI protocol compatibility but are not exposed in the CLI since they are not applicable to ALPHA HWR (they are for heating system pumps, not DHW pumps).

---

## Recommendations

### For Users

1. **Use Supported Modes Only:** Stick to the 5 fully supported modes + Mode 25 (cycle time control) for reliable operation.
2. **Temperature Control:** Use Mode 27 (`set-temperature --min --max`) which includes AutoAdapt flow adjustment.
3. **Understand Pump Limitations:** ALPHA HWR is optimized for domestic hot water recirculation, not heating systems or industrial applications.

### For Developers

1. **No Further Investigation Needed:** All GENI protocol modes have been verified for ALPHA HWR compatibility.
2. **Mode 25 Protocol:** See issue #14 for ongoing work to document the cycle time parameter protocol.
3. **Documentation Complete:** Support matrix is fully documented for the 5 ALPHA HWR modes.

---

## References

- **AutoAdapt Modes:** `docs/protocol/autoadapt_modes.md`
- **Investigation Results:** `mode_investigation_results.json`
- **GENI Protocol:** Grundfos GENI profile specification
