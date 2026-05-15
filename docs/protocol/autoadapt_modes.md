# AutoAdapt Modes - Support Status

This document details the support status for AutoAdapt control modes on the Grundfos ALPHA HWR pump.

## Overview

AutoAdapt is an intelligent pump control algorithm that automatically adjusts operation based on system characteristics and demand. The GENI protocol defines several AutoAdapt variants:

| Mode ID | Name | ALPHA HWR Support |
|---------|------|-------------------|
| 5 | AUTO_ADAPT (generic) |  **Limited** |
| 13 | AUTO_ADAPT_RADIATOR |  **Full** |
| 14 | AUTO_ADAPT_UNDERFLOOR |  **Full** |
| 15 | AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR |  **Full** |
| 26 | PROPORTIONAL_DIFF_PRESSURE |  **Not Supported** |

---

## Mode 5: AUTO_ADAPT (Generic) - Limited Support

### Discovery Results

**Configuration Data:**
-  SubID 11 found in Object 86 (PumpConfiguration)
-  Setpoint limits available: min=1.48m, max=1.52m, default=1.50m
-  Data format: uint16 (Pascals), not float32 like other modes
-  Very narrow operating range (0.04m spread)

**Mode Switching:**
-  Class 3 fallback command 0x06 exists
-  Mode switch commands succeed but verification shows mode doesn't change reliably
-  May require specific firmware version or system conditions

**Setpoint Writing:**
-  Register IDs unknown - library tries multiple candidates (0x1D, 0x06, 0x05)
-  Success not guaranteed

### Implementation Status

**Library Support:**
```python
# Available but with warnings
await client.set_autoadapt(1.5)  # meters
```

**CLI Support:**
```bash
# Available but displays warning
alpha-hwr control set-autoadapt --value 1.5
# Output:
#   Note: Mode 5 (AUTO_ADAPT) has limited support.
#     Consider using specific variants (radiator/underfloor/combined) instead.
```

### Recommendations

**DO NOT USE Mode 5** for production deployments. Instead, use the specific AutoAdapt variants:

| System Type | Recommended Mode | Command |
|-------------|------------------|---------|
| Radiator heating | Mode 13 (AUTO_ADAPT_RADIATOR) | `set_autoadapt_radiator()` |
| Underfloor heating | Mode 14 (AUTO_ADAPT_UNDERFLOOR) | `set_autoadapt_underfloor()` |
| Combined systems | Mode 15 (AUTO_ADAPT_COMBINED) | `set_autoadapt_combined()` |

### Why Mode 5 Has Limited Support

**Possible Reasons:**

1. **Firmware Evolution:** Mode 5 may be legacy/deprecated in favor of specific variants (13-15)
2. **Hardware Limitations:** ALPHA HWR may lack sensors/logic for generic AutoAdapt
3. **Configuration Requirements:** May require additional setup not implemented in library
4. **Narrow Range:** 0.04m spread suggests it's a placeholder or diagnostic mode

---

## Mode 26: PROPORTIONAL_DIFF_PRESSURE - NOT Supported

### Discovery Results

**Configuration Data:**
-  No SubID found in Object 86 (tested 0-65)
-  No factory configuration available
-  No setpoint limits defined

**Mode Switching:**
-  No Class 3 fallback command
-  Explicitly returns error: "Unsupported Control Mode for Set: 26"

**Conclusion:** Mode 26 is **NOT implemented** in ALPHA HWR firmware.

### Implementation Status

**Library:** Not implemented (no `set_proportional_diff_pressure()` method)

**CLI:** Not available

### Why Mode 26 Is Not Supported

**Analysis:**

1. **Product Line Differentiation:** Proportional Differential Pressure may be exclusive to higher-end models (ALPHA3, MAGNA3)
2. **Sensor Requirements:** Requires differential pressure sensors not present in ALPHA HWR
3. **Application Specific:** More relevant for complex hydronic systems than recirculation pumps

**Alternative:** Use Mode 1 (PROPORTIONAL_PRESSURE) which IS fully supported:

```python
await client.set_proportional_pressure(3.0)  # meters
```

```bash
alpha-hwr control set-proportional-pressure --value 3.0
```

---

## Fully Supported AutoAdapt Modes

### Mode 13: AUTO_ADAPT_RADIATOR

**Best for:** Radiator heating systems with high-temperature operation.

**Configuration:**
- SubID: 19
- Format: uint16 (Pascals)
- Typical range: 0.5 - 6.0 m
- Setpoint register: 0x1E

**Usage:**
```python
await client.set_autoadapt_radiator(3.0)  # 3 meters
```

```bash
alpha-hwr control set-autoadapt-radiator --value 3.0
```

### Mode 14: AUTO_ADAPT_UNDERFLOOR

**Best for:** Underfloor heating systems with low-temperature operation.

**Configuration:**
- SubID: 21
- Format: uint16 (Pascals)
- Typical range: 0.3 - 4.0 m
- Setpoint register: 0x1F

**Usage:**
```python
await client.set_autoadapt_underfloor(2.5)  # 2.5 meters
```

```bash
alpha-hwr control set-autoadapt-underfloor --value 2.5
```

### Mode 15: AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR

**Best for:** Combined radiator and underfloor heating systems.

**Configuration:**
- SubID: 23
- Format: uint16 (Pascals)
- Typical range: 0.4 - 5.0 m
- Setpoint register: 0x20

**Usage:**
```python
await client.set_autoadapt_combined(3.5)  # 3.5 meters
```

```bash
alpha-hwr control set-autoadapt-combined --value 3.5
```

---

## Testing Methodology

### Test Commands

```bash
# Test mode switching
python test_mode_support.py <DEVICE_ADDRESS>

# Test Class 3 commands
python test_mode5_class3.py <DEVICE_ADDRESS>
```

### Test Results (ALPHA HWR Family 52, Type 7, Version 2)

| Test | Mode 5 | Mode 26 |
|------|--------|---------|
| SubID found |  Yes (11) |  No |
| Limits readable |  Yes |  No |
| Mode switch |  Partial |  Fails |
| Setpoint write |  Unknown |  N/A |

---

## Comparison with Other Modes

| Mode | Name | Support | Typical Use |
|------|------|---------|-------------|
| 0 | CONSTANT_PRESSURE |  Full | Fixed differential pressure |
| 1 | PROPORTIONAL_PRESSURE |  Full | Flow-dependent pressure |
| 2 | CONSTANT_SPEED |  Full | Fixed RPM operation |
| **5** | **AUTO_ADAPT** |  **Limited** | Generic adaptive (use 13-15 instead) |
| 8 | CONSTANT_FLOW |  Full | Fixed flow rate |
| **13** | **AUTO_ADAPT_RADIATOR** |  **Full** | Radiator systems (RECOMMENDED) |
| **14** | **AUTO_ADAPT_UNDERFLOOR** |  **Full** | Underfloor heating (RECOMMENDED) |
| **15** | **AUTO_ADAPT_COMBINED** |  **Full** | Mixed systems (RECOMMENDED) |
| **26** | **PROPORTIONAL_DIFF_PRESSURE** |  **None** | Not available on ALPHA HWR |

---

## Related Documentation

- [Control Protocol](control.md) - Control mode switching and setpoint writing
- [BLE Architecture](ble_architecture.md) - Object mapping and SubID structure
- [API Client Methods](../api/client.md) - Python API reference
- [CLI Guide](../guides/cli_guide.md) - Command-line usage
