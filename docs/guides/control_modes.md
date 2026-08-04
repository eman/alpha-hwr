# Control Modes and Setpoints

This guide provides details on the ALPHA HWR's control modes and setpoint configuration.

## Overview

The ALPHA HWR pump supports multiple control modes, each designed for specific application requirements. Control modes can be configured via:

- **Physical operating panel** (limited modes)
- **Mobile application** (all modes)
- **alpha-hwr library** (all modes via CLI or Python API)

## Reading Current Setpoint

### CLI

```bash
# Read current control mode and setpoint
alpha-hwr control status
```

### Python API

```python
from alpha_hwr import AlphaHWRClient

async with AlphaHWRClient("AA:BB:CC:DD:EE:FF") as client:
    await client.authenticate(fast_mode=True)

    # Read current setpoint
    setpoint_info = await client.control.get_mode()

    if setpoint_info:
        print(f"Control Mode: {setpoint_info.control_mode.name}")
        print(f"Setpoint: {setpoint_info.setpoint}")
        print(
            f"Range: {setpoint_info.min_setpoint} - {setpoint_info.max_setpoint}"
        )
```

## Control Modes Available via Operating Panel

### Temperature Control - AUTOADAPT

**Description:** Ensures comfort via integrated temperature estimator, suitable for all hot-water recirculation applications with a dedicated return line.

**Features:**

- Automatically adjusts flow according to temperature setpoint
- Ensures hot water availability throughout the house
- Meets minimum flow requirement for tankless water heaters
- Flow rate: 1-4 GPM (automatically adjusted)
- Temperature range: 95-102°F (35-39°C)

**Use Case:** General hot-water recirculation with optimal energy efficiency

### Temperature Control

**Description:** Ensures comfort via flow limits based on predefined pipe diameters.

**Features:**

- Maintains temperature between 95-102°F (35-39°C)
- Flow limits designed to reduce flow-accelerated corrosion
- Operates on maximum curve until reaching flow limits

**Flow Limits by Pipe Diameter:**

- 1/2": 1.5 GPM
- 3/4": 2.3 GPM
- 1": 3.8 GPM

**Use Case:** Systems where flow-accelerated corrosion is a concern

### Continuous Operation - 24/7

**Description:** Ensures comfort through continuous operation in constant curve III with flow limits.

**Features:**

- Continuous operation
- Flow limits based on predefined pipe diameters
- Reduces flow-accelerated corrosion and noise

**Flow Limits (adjustable via Bluetooth interface):**

- 1/2": 1.5 GPM
- 3/4": 2.3 GPM
- 1": 3.8 GPM

**Use Case:** Applications requiring 24/7 hot water availability

## Control Modes Available via Bluetooth Interface

The ALPHA HWR supports 5 primary control modes specifically optimized for hot water recirculation.

### 1. Temperature Control (Mode 27)

**Description:** Controls pump operation to maintain water temperature within a specified range. This is the recommended mode for most DHW applications.

**Features:**
- **Min/Max Temperature:** Configurable range (default 35-39°C).
- **AUTOADAPT:** Automatic flow adjustment (1-4 gpm) to maintain comfort and efficiency.
- **Flow Limits:** Can be limited based on pipe diameter to prevent corrosion.

**Example:**
```bash
# Set range 35-39°C with AUTOADAPT enabled
alpha-hwr control set-temperature --min 35 --max 39 --autoadapt

# Set range 40-45°C with AUTOADAPT disabled and 1.5 GPM limit
alpha-hwr control set-temperature --min 40 --max 45 --no-autoadapt --flow-limit 1.5
```

### 2. Cycle Time Control (Mode 25)

**Description:** Pump operates at maximum curve with configurable on/off cycles.

**Parameters:**
- **On time:** 1-60 minutes
- **Off time:** 1-60 minutes

**Example:**
```bash
# Set 5 minutes ON, 15 minutes OFF
alpha-hwr control set-cycle-time --on 5 --off 15
```

### 3. Constant Curve / Constant Speed (Mode 2)

**Description:** Pump runs at a fixed rotational speed (RPM).

**Features:**
- **Setpoint:** 1000-4500 RPM.
- **Flow Limits:** Optional GPM limit to prevent noise and corrosion.

**Example:**
```bash
# Set to 2500 RPM with 2.3 GPM limit (3/4" pipe)
alpha-hwr control set-speed 2500 --flow-limit 2.3
```

### 4. Constant Pressure (Mode 0)

**Description:** Maintains a fixed head pressure regardless of flow.

**Setpoint:** 0.5-6.0 meters.

**Example:**
```bash
alpha-hwr control set-pressure 1.5
```

### 5. Constant Flow (Mode 8)

**Description:** Maintains a fixed flow rate regardless of head pressure.

**Setpoint:** 0.1-3.0 m³/h.

**Example:**
```bash
alpha-hwr control set-flow 0.5
```

---

## Flow Limitation and Pipe Diameters

The ALPHA HWR allows setting a maximum flow limit to prevent **flow-accelerated corrosion (FAC)** and noise in the system. Limits are typically chosen based on pipe diameter:

| Pipe Diameter | Recommended Limit |
|---------------|-------------------|
| 1/2"          | 1.5 GPM           |
| 3/4"          | 2.3 GPM           |
| 1"            | 3.8 GPM           |

**CLI:**
```bash
alpha-hwr control set-flow-limit 1.5
```

---

## Proportional Pressure (Mode 1)

Proportional pressure mode is also fully supported and adjusts pressure along a curve based on flow.

**CLI:**
```bash
alpha-hwr control set-proportional 1.2
```

---

## Deprecated/Unsupported Modes

The following modes are defined in the GENI protocol but are **not recommended** for ALPHA HWR as they are designed for heating systems (radiators/underfloor heating) rather than DHW recirculation:
- AUTOADAPT Radiator (Mode 13)
- AUTOADAPT Underfloor (Mode 14)
- AUTOADAPT Combined (Mode 15)
- AUTOADAPT Generic (Mode 5)

Use **Temperature Control (Mode 27)** with the `--autoadapt` flag instead.

## Temperature Range Control

**Mode ID:** 27  
**Special Handling:** Uses dual setpoints (high/low temperature)

**Description:** Controls pump operation to maintain water temperature within a specified range.

**Setpoints:**

- **Low Temperature:** Minimum temperature limit
- **High Temperature:** Maximum temperature limit
- **AutoAdapt Flag:** Enable/disable automatic delta temperature adjustment

**Default Range:** 32.95-41.11°C (91-106°F)  
**Nominal Range (per manual):** 35-39°C (95-102°F)

**Reading Temperature Range:**

```bash
alpha-hwr control status
# Output will show min/max temperatures for this mode
```

**Data Source:** Object 91, Sub-ID 430 (TemperatureRangeControlUserSettings, Type 1012)

## Setpoint Data Structures

### Standard Modes (Object 86, Sub-ID 6)

**Type 303: OperationRequest**

Structure:

```
[ControlSource(1)][OperationMode(1)][ControlMode(1)][Setpoint(4)]
```

- `ControlSource`: Source of control command
- `OperationMode`: Current operation mode
- `ControlMode`: Active control mode (0-27)
- `Setpoint`: Target value (float32, big-endian)

### Limit Configuration (Object 86, Sub-IDs 11-39)

**Type 301: FactoryConfig**

**Standard Format (float32):**

```
[DefaultSetpoint(4)][MinSetpoint(4)][MaxSetpoint(4)][...]
```

**AutoAdapt Generic Format (uint16 with padding):**

```
[DefaultSetpoint(2)][Padding(2)][MinSetpoint(2)][Padding(2)][MaxSetpoint(2)][Padding(2)]
```

**Sub-ID Mapping:**

- Sub 11: AutoAdapt Generic (uint16)
- Sub 13: Constant Speed (float32)
- Sub 15: Constant Pressure (float32)
- Sub 17: Proportional Pressure (float32)
- Sub 19: AutoAdapt Radiator (float32)
- Sub 21: AutoAdapt Underfloor (float32)
- Sub 23: AutoAdapt Combined (float32)
- Sub 39: Constant Flow (float32)

### Temperature Range Control (Object 91, Sub-ID 430)

**Type 1012: TemperatureRangeControlUserSettings**

Structure:

```
[DeltaTempEnabled(1)][MinTemp(4)][MaxTemp(4)][MinOffTime(1)][MaxOffTime(1)][MinOnTime(1)][MaxOnTime(1)]
```

- `DeltaTempEnabled`: AutoAdapt flag (bool)
- `MinTemp`: Low temperature limit (float32, °C)
- `MaxTemp`: High temperature limit (float32, °C)
- Time limits: On/off timing parameters

## Unit Conversions

The library automatically handles unit conversions for display:

### Pressure Modes

- **Stored as:** Pascals (Pa)
- **Displayed as:** Meters of water column (m)
- **Conversion:** 1 m H₂O ≈ 9806.65 Pa

### Flow Modes

- **Stored as:** m³/h
- **Displayed as:** m³/h (no conversion)

### Speed Modes

- **Stored as:** RPM
- **Displayed as:** RPM (no conversion)

### Temperature Modes

- **Stored as:** °C
- **Displayed as:** °C (no conversion)

## Best Practices

1. **Choose the Right Mode:**
   - For hot water recirculation: Temperature Control - AUTOADAPT
   - For predictable scheduling: Cycle Time Control
   - For legacy system replacement: Constant Curve
   - For multi-zone systems: Constant Pressure
   - For external control: Constant Flow

2. **Setpoint Selection:**
   - Start with factory defaults
   - Adjust based on system performance
   - Use `--limits` flag to see allowed ranges

3. **Energy Efficiency:**
   - Use AUTOADAPT modes when possible
   - Enable scheduling for time-based control
   - Set appropriate temperature ranges (don't overheat)

4. **System Protection:**
   - Respect flow limits for pipe diameter
   - Monitor for corrosion in high-flow applications
   - Use minimum flow settings for tankless heaters

## See Also

- [CLI Guide](cli_guide.md) - Complete CLI command reference
- [Data Models](../reference/data_models.md) - SetpointInfo model documentation
- [Hardware Reference](../reference/hardware.md) - Physical specifications
- User Manual: See `resources/reference/92992176_0224_ALPHA_HWR_CS_DB.md` in the repository
