# Control Modes - Complete Support Matrix

This document provides a comprehensive overview of all 32 control modes defined in the GENI protocol and their support status on the Grundfos ALPHA HWR pump.

## Executive Summary

The ALPHA HWR is a **domestic hot water recirculation pump** designed for residential heating systems. Hardware testing reveals it supports **9 out of 32 control modes** - those specifically related to heating and circulation applications.

**Support Statistics:**
-  **Fully Supported:** 8 modes (25%)
-   **Limited Support:** 1 mode (3%)
-  **Not Supported:** 23 modes (72%)

---

## Complete Mode Support Matrix

| Mode | Name | Support | SubID | Register | Notes |
|------|------|---------|-------|----------|-------|
| 0 | CONSTANT_PRESSURE |  **Full** | 15 | 0x18 | Constant head pressure |
| 1 | PROPORTIONAL_PRESSURE |  **Full** | 17 | 0x17 | Proportional pressure curve |
| 2 | CONSTANT_SPEED |  **Full** | 13 | 0x04 | Fixed RPM operation |
| 5 | AUTO_ADAPT |   **Limited** | 11 | 0x1D/0x06/0x05 | Generic AutoAdapt (use modes 13-15 instead) |
| 7 | CLOSED_LOOP_SENSOR |  Not Supported | - | - | Generic sensor control |
| 8 | CONSTANT_FLOW |  **Full** | 39 | 0x15 | Constant flow rate |
| 9 | CONSTANT_LEVEL |  Not Supported | - | - | Water level control (tanks/sumps) |
| 10 | FLOW_ADAPT |  Not Supported | - | - | Adaptive flow control |
| 11 | CONSTANT_DIFF_PRESSURE |  Not Supported | - | - | Differential pressure sensors required |
| 12 | CONSTANT_DIFF_TEMP |  Not Supported | - | - | Temperature differential control |
| 13 | AUTO_ADAPT_RADIATOR |  **Full** | 19 | 0x1E | AutoAdapt for radiator systems |
| 14 | AUTO_ADAPT_UNDERFLOOR |  **Full** | 21 | 0x1F | AutoAdapt for underfloor heating |
| 15 | AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR |  **Full** | 23 | 0x20 | AutoAdapt for combined systems |
| 16 | CONSTANT_DOSING |  Not Supported | - | - | Chemical dosing (pools/industrial) |
| 17 | DISINFECTANT_CONTROL |  Not Supported | - | - | Chemical dosing (pools/water treatment) |
| 18 | FLOCCULENT_CONTROL |  Not Supported | - | - | Chemical dosing (water treatment) |
| 19 | PH_CONTROL |  Not Supported | - | - | pH dosing (pools/industrial) |
| 20 | PID_CONTROL |  Not Supported | - | - | Generic PID algorithm |
| 21 | CONSTANT_RELATIVE_SETPOINT |  Not Supported | - | - | Relative setpoint adjustment |
| 22 | LEVEL_CONTROL |  Not Supported | - | - | Water level control |
| 23 | ZONE_PUMP_CONTROL |  Not Supported | - | - | Multi-zone systems |
| 24 | USER_DEFINED |  Not Supported | - | - | Custom mode |
| 25 | DHW_ON_OFF_CONTROL |  Not Supported | - | - | Domestic hot water on/off |
| 26 | PROPORTIONAL_DIFF_PRESSURE |  Not Supported | - | - | Differential pressure sensors required |
| 27 | TEMPERATURE_RANGE_CONTROL |  **Full** | - | - | Temperature range control (min/max) |
| 28 | COMFORT_VALVE_CONTROL |  Not Supported | - | - | Valve control |
| 29 | ON_OFF_CONTROL |  Not Supported | - | - | Simple on/off |
| 30 | CONSTANT_VOLTAGE |  Not Supported | - | - | Voltage control (industrial/testing) |
| 128 | SYSTEM_AIR_VENTING |  Not Supported | - | - | Air venting control |
| 254 | NONE | N/A | - | - | No control mode active |

---

## Supported Modes (8 modes)

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

### 5. AutoAdapt Radiator (Mode 13) -  Full Support

**Description:** Intelligent adaptation for radiator heating systems.

**Use Case:** Radiator-only heating systems, automatic optimization

**Hardware Support:**
-  SubID 19 in Object 86
-  Mode switching works reliably
-  Register 0x1E for setpoint writes
-  Limits: 1.83-4.57 m (typical)

**Implementation:**
```python
await client.set_autoadapt_radiator(3.0)  # 3.0 meters
```

**CLI:**
```bash
alpha-hwr control set-autoadapt-radiator --value 3.0
```

---

### 6. AutoAdapt Underfloor (Mode 14) -  Full Support

**Description:** Intelligent adaptation for underfloor heating systems.

**Use Case:** Underfloor heating, low-temperature systems

**Hardware Support:**
-  SubID 21 in Object 86
-  Mode switching works reliably
-  Register 0x1F for setpoint writes
-  Limits: 1.83-4.57 m (typical)

**Implementation:**
```python
await client.set_autoadapt_underfloor(2.5)  # 2.5 meters
```

**CLI:**
```bash
alpha-hwr control set-autoadapt-underfloor --value 2.5
```

---

### 7. AutoAdapt Combined (Mode 15) -  Full Support

**Description:** Intelligent adaptation for mixed radiator and underfloor systems.

**Use Case:** Hybrid heating systems, both radiator and underfloor

**Hardware Support:**
-  SubID 23 in Object 86
-  Mode switching works reliably
-  Register 0x20 for setpoint writes
-  Limits: 1.83-4.57 m (typical)

**Implementation:**
```python
await client.set_autoadapt_combined(3.5)  # 3.5 meters
```

**CLI:**
```bash
alpha-hwr control set-autoadapt-combined --value 3.5
```

---

### 8. AutoAdapt Generic (Mode 5) -  Limited Support

**Description:** Generic AutoAdapt mode (older/deprecated).

**Use Case:** Not recommended - use modes 13-15 instead

**Hardware Support:**
-   SubID 11 in Object 86 (uint16 format, unusual)
-   Mode switching unreliable
-   Register IDs: tries 0x1D, 0x06, 0x05 (uncertain)
-   Very narrow limits: 1.48-1.52 m (0.04m range)

**Recommendation:** **DO NOT USE** - Use specific variants (13, 14, or 15) instead.

**Implementation:**
```python
# Available but not recommended
await client.set_autoadapt(1.5)  # Limited support warning displayed
```

---

### 9. Temperature Range Control (Mode 27) - Full Support

**Description:** Regulates pump operation based on a minimum and maximum temperature range.

**Use Case:** Maintaining water temperature within specific bounds (e.g., DHW recirculation).

**Hardware Support:**
-  Confirmed via live hardware verification (default mode on some units).
-  Uses **Object 91** (Setpoint), **SubID 430** (`0x01AE`) for configuration.
-  Supports dual setpoints (Minimum and Maximum Temperature).

**Implementation:**
```python
# Set range: 35°C to 45°C
await client.set_temperature_range_control(35.0, 45.0)
```

---

## Unsupported Modes (23 modes)

### Why These Modes Are Not Supported

The ALPHA HWR is a **residential hot water recirculation pump**, not a general-purpose industrial pump. The unsupported modes fall into these categories:

#### 1. Sensor Requirements Not Met
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
- **Mode 25 (DHW_ON_OFF_CONTROL):** DHW on/off switching
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
| Standard Modes | 8 | 8 |
| Temperature Range | 1 | 1 |
| Industrial/Dosing | 23 | 0 |
| **Total** | **32** | **9** |

---

## Implementation Status

### Library Support

**Fully Implemented (9 modes):**
- `set_constant_pressure(value_m)` - Mode 0
- `set_proportional_pressure(value_m)` - Mode 1
- `set_constant_speed(value_rpm)` - Mode 2
- `set_constant_flow(value_m3h)` - Mode 8
- `set_autoadapt_radiator(value_m)` - Mode 13
- `set_autoadapt_underfloor(value_m)` - Mode 14
- `set_autoadapt_combined(value_m)` - Mode 15
- `set_temperature_range_control(min, max)` - Mode 27

**Partially Implemented (1 mode):**
- `set_autoadapt(value_m)` - Mode 5 (with warnings)

**Not Implemented (23 modes):**
- Unsupported modes listed above - no methods created

### CLI Support

**Available Commands:**
```bash
alpha-hwr control set-pressure --value <meters>
alpha-hwr control set-proportional-pressure --value <meters>
alpha-hwr control set-speed --value <rpm>
alpha-hwr control set-flow --value <m3h>
alpha-hwr control set-autoadapt-radiator --value <meters>
alpha-hwr control set-autoadapt-underfloor --value <meters>
alpha-hwr control set-autoadapt-combined --value <meters>
alpha-hwr control set-autoadapt --value <meters>  # Not recommended
```

---

## Recommendations

### For Users

1. **Use Supported Modes Only:** Stick to the 9 supported modes for reliable operation.
2. **Avoid Mode 5:** Use specific AutoAdapt variants (13-15) instead.
3. **Understand Pump Limitations:** ALPHA HWR is optimized for residential heating, not industrial applications.

### For Developers

1. **No Further Investigation Needed:** All GENI protocol modes have been verified.
2. **Documentation Complete:** Support matrix is fully documented.

---

## References

- **AutoAdapt Modes:** `docs/protocol/autoadapt_modes.md`
- **Investigation Results:** `mode_investigation_results.json`
- **GENI Protocol:** Grundfos GENI profile specification
