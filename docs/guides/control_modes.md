# Control Modes and Setpoints

This guide provides comprehensive information about the ALPHA HWR's control modes and setpoint configuration.

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
        print(f"Range: {setpoint_info.min_setpoint} - {setpoint_info.max_setpoint}")
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

### Cycle Time Control

**Description:** Pump operates at maximum curve with time-based start/stop cycles.

**Default Parameters:**

- On time: 5 minutes
- Off time: 15 minutes
- Adjustable via the client application

**Use Case:** Energy-efficient operation with predictable hot water availability

### Constant Curve (Constant Speed)

**Description:** Pump runs at constant speed or power, following the selected constant curve.

**Setpoint:** RPM (revolutions per minute)

**Use Case:** Replacing old three-speed circulators where required performance is known

**Example:**

```bash
# Set constant speed to 2500 RPM
alpha-hwr control set-speed --value 2500
```

### Constant Pressure

**Description:** Head is kept constant regardless of system changes.

**Setpoint:** Pressure in Pascals (displayed as meters of water column)

**Typical Range:** 0.5-6.0 m (approximately 5-60 kPa)

**Use Case:** Systems with multiple risers and thermally actuated balancing valves

**Example:**

```bash
# Set constant pressure to 3.0 meters
alpha-hwr control set-pressure --value 3.0
```

### Proportional Pressure

**Description:** Similar to constant pressure but with proportional adjustment.

**Setpoint:** Pressure in Pascals (displayed as meters of water column)

**Use Case:** Advanced pressure control applications

### Constant Flow

**Description:** Maintains constant flow regardless of head.

**Setpoint:** Flow rate in m³/h

**Typical Range:** 0.1-3.0 m³/h

**Use Case:** Systems with external control (e.g., aquastat)

**Example:**

```bash
# Set constant flow to 2.0 m³/h
alpha-hwr control set-flow --value 2.0
```

### AutoAdapt Modes

The pump supports several AutoAdapt modes for automatic system optimization:

#### AutoAdapt (Generic)

**Mode ID:** 5  
**Setpoint Format:** uint16 (Pascals)  
**Use Case:** General adaptive control

#### AutoAdapt Radiator

**Mode ID:** 13  
**Setpoint Format:** float32 (Pascals)  
**Use Case:** Radiator heating systems

#### AutoAdapt Underfloor

**Mode ID:** 14  
**Setpoint Format:** float32 (Pascals)  
**Use Case:** Underfloor heating systems

#### AutoAdapt Combined (Radiator + Underfloor)

**Mode ID:** 15  
**Setpoint Format:** float32 (Pascals)  
**Use Case:** Mixed radiator and underfloor heating

**Example:**

```bash
# Set AutoAdapt radiator mode with 3.0m setpoint
alpha-hwr control set-autoadapt-radiator --value 3.0
```

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
