# Understanding Pump Telemetry

This guide explains the metrics reported by the ALPHA HWR pump and how to interpret them for optimal system performance.

## Core Metrics

### Flow Rate

**What it is:** Flow rate measures the volume of water circulating through the pump per unit time.

**Units:**

- **m³/h** (cubic meters per hour) - Primary unit used by the pump
- **GPM** (gallons per minute) - Common in North America
- **Conversion:** 1 m³/h ≈ 4.40 GPM

**Typical Values for ALPHA HWR:**

- **ALPHA HWR 15-29:** 0.0 - 2.5 m³/h (0-11 GPM)
- **ALPHA HWR 15-55:** 0.0 - 3.1 m³/h (0-13.6 GPM)

**Why it's important:**

1. **System Coverage:** Higher flow rates ensure hot water reaches all fixtures quickly. Insufficient flow results in lukewarm water at distant taps.

2. **Tankless Heater Compatibility:** Tankless water heaters require minimum flow rates to activate (typically 0.4-0.8 GPM). The pump must maintain this threshold.

3. **Pipe Sizing Validation:** Flow rates can reveal pipe sizing issues:
   - Very low flow (< 0.5 m³/h) may indicate undersized pipes or blockages
   - Very high flow (> 3.0 m³/h) may indicate oversized pipes or system leaks

4. **Energy Efficiency:** Flow directly correlates with pump power consumption. Higher flow = more energy. The AUTOADAPT mode optimizes flow based on actual temperature needs.

5. **Flow-Accelerated Corrosion (FAC):** Excessive flow rates can accelerate pipe corrosion, especially in copper systems. The ALPHA HWR includes configurable flow limits by pipe diameter:
   - 1/2" pipes: 1.5 GPM limit (0.34 m³/h)
   - 3/4" pipes: 2.3 GPM limit (0.52 m³/h)
   - 1" pipes: 3.8 GPM limit (0.86 m³/h)

**Reading Flow:**

```python
from alpha_hwr import AlphaHWRClient

async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
    telemetry = await client.telemetry.read_once()
    
    flow_m3h = telemetry.flow_m3h
    flow_gpm = flow_m3h * 4.40  # Convert to GPM
    
    print(f"Flow: {flow_m3h:.2f} m³/h ({flow_gpm:.2f} GPM)")
```

### Head Pressure

**What it is:** Head pressure (also called differential head) measures the pressure difference the pump creates between its inlet and outlet. It represents the pump's ability to push water through the system against resistance.

**Units:**

- **m** (meters of water column) - Primary unit
- **ft** (feet of water column) - Common in North America
- **psi** (pounds per square inch) - Absolute pressure
- **Conversions:**
  - 1 m H₂O ≈ 3.28 ft ≈ 1.42 psi ≈ 9806.65 Pa

**Typical Values for ALPHA HWR:**

- **ALPHA HWR 15-29:** 0.0 - 2.9 m (0-9.5 ft, 0-4.1 psi)
- **ALPHA HWR 15-55:** 0.0 - 5.5 m (0-18 ft, 0-7.8 psi)

**Why it's important:**

1. **System Resistance Indication:** Head pressure reveals how hard the pump is working against system resistance:
   - **Low head (< 1.0 m):** Short pipe runs, wide pipes, few elbows - easy system
   - **Medium head (1.0-3.0 m):** Typical residential hot water recirculation
   - **High head (> 3.0 m):** Long pipe runs, narrow pipes, many elbows/fittings, multiple floors

2. **Blockage Detection:** Sudden increase in head pressure can indicate:
   - Partially closed valves
   - Air locks in the system
   - Sediment buildup or scaling
   - Check valve malfunction

3. **Pump Performance Verification:** The pump's performance follows a curve where head decreases as flow increases. Abnormal head-flow relationships indicate problems.

4. **Control Mode Selection:**
   - **Constant Pressure mode:** Maintains steady head regardless of flow - ideal for multi-zone systems with thermostatic valves
   - **Proportional Pressure mode:** Adjusts head proportional to flow - energy-efficient for single-zone systems
   - **Constant Curve/Speed mode:** Follows fixed performance curve

5. **Energy Optimization:** Higher head requires more power. If the system can maintain adequate circulation at lower head, reducing the setpoint saves energy.

**Reading Head:**

```python
from alpha_hwr import AlphaHWRClient

async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
    telemetry = await client.telemetry.read_once()
    
    head_m = telemetry.head_m
    head_ft = head_m * 3.28  # Convert to feet
    head_psi = head_m * 1.42  # Convert to psi
    
    print(f"Head: {head_m:.2f} m ({head_ft:.2f} ft, {head_psi:.2f} psi)")
```

## Performance Relationships

### Pump Curve

The relationship between flow and head follows the pump's performance curve:

- **At zero flow (shutoff head):** Maximum head, pump closed or blocked
- **At maximum flow:** Minimum head, fully open system
- **Operating point:** Where system resistance curve intersects pump curve

**Example Operating Points:**

| Scenario | Flow (m³/h) | Head (m) | Power (W) | Interpretation |
|----------|-------------|----------|-----------|----------------|
| Ideal | 1.2 | 2.5 | 25 | Balanced system, good circulation |
| Restricted | 0.5 | 4.0 | 30 | High resistance, check for blockage |
| Oversized | 2.5 | 1.0 | 35 | Low resistance, may waste energy |
| Shutoff | 0.0 | 5.5 | 15 | Closed valve or air lock |

### Power Consumption

Power consumption relates to both flow and head:

```
Power ∝ Flow × Head
```

**Typical Power Draw:**

- **ALPHA HWR 15-29:** 2-21 W
- **ALPHA HWR 15-55:** 2-38 W

**Energy-Saving Strategies:**

1. Use **AUTOADAPT mode** to automatically optimize flow/head based on temperature
2. Enable **scheduling** to run pump only when hot water is needed
3. Configure **flow limits** appropriate for your pipe diameter
4. Set **minimum head** just sufficient for system (don't over-pressurize)

## Temperature Metrics

### Media Temperature

**What it is:** Estimated temperature of the water flowing through the pump.

**How it works:** The ALPHA HWR doesn't have a direct water temperature sensor. Instead, it estimates media temperature based on thermal sensors on the pump housing and internal algorithms.

**Typical Values:**

- **Cold water:** 10-20°C (50-68°F)
- **Hot water recirculation:** 35-60°C (95-140°F)
- **Warning threshold:** > 60°C (140°F) may trigger protection

**Why it's important:**

1. **System Performance Verification:** Confirms hot water is actually circulating
2. **Temperature Control Modes:** Used by AUTOADAPT and Temperature Control modes to regulate pump operation
3. **Thermal Protection:** Pump automatically reduces speed if water is too hot
4. **Comfort Monitoring:** Ensures hot water availability meets user expectations

**Accuracy Limitations:**

- ±5°C typical accuracy
- Best accuracy when pump has been running continuously
- Less accurate immediately after startup or during rapid temperature changes

### PCB and Control Box Temperatures

**What they are:** Internal electronics temperatures.

**Typical Values:**

- **Normal operation:** 30-50°C (86-122°F)
- **Warning:** > 60°C (140°F)

**Why it's important:**

- Indicates pump ventilation and ambient conditions
- High electronics temperatures can trigger thermal protection
- Useful for diagnosing overheating in enclosed installations

## Motor Metrics

### Speed (RPM)

**What it is:** Motor rotational speed in revolutions per minute.

**Typical Range:** 1000-4500 RPM (varies by model and control mode)

**Why it's important:**

- Direct indicator of pump activity (0 RPM = pump off)
- In Constant Speed mode, this is the controlled parameter
- Correlates with flow rate (higher RPM = higher flow, generally)
- Can reveal pump health (erratic RPM changes may indicate motor issues)

### Power Draw

**What it is:** Electrical power consumed by the pump motor.

**Why it's important:**

- **Energy monitoring:** Track operating costs
- **Efficiency analysis:** Compare power vs. flow/head to evaluate system efficiency
- **Fault detection:** Abnormal power draw can indicate:
  - Motor overload (too high)
  - Bearing wear (fluctuating)
  - Electrical issues (too low)

## Monitoring Best Practices

### 1. Baseline Your System

When first installing or after system changes:

```bash
# Monitor for 5 minutes to establish baseline
alpha-hwr monitor --interval 2 > baseline.log
```

Record typical values:

- Flow during normal operation
- Head at typical flow
- Temperature when fully warmed up
- Power consumption averages

### 2. Watch for Anomalies

**Flow Anomalies:**

- Sudden drop (< 50% of baseline)  Check for blockage/closed valve
- Gradual decline  Check for scaling or sediment
- Excessive flow (> 150% of baseline)  Check for leaks or open bypass

**Head Anomalies:**

- Sudden spike  Air lock, blockage, or closed valve
- Gradual increase  Scaling or sediment buildup
- Sudden drop  System leak or bypass valve opened

**Temperature Anomalies:**

- Not reaching target  Heater issue or excessive heat loss
- Fluctuating rapidly  Water heater short cycling
- Declining over time  Check for heat loss in pipes

### 3. Optimize for Efficiency

**Goal:** Minimum flow and head that maintains comfort

**Process:**

1. Monitor temperature at furthest fixture
2. Gradually reduce setpoint (pressure/speed) until temperature just meets minimum
3. Set flow limit to prevent waste
4. Enable scheduling to run only when needed

**Example Optimization:**

```python
from alpha_hwr import AlphaHWRClient

async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
    # Start with baseline
    await client.control.set_constant_pressure(3.0)  # 3.0 m initial
    
    # Monitor and verify comfort at all fixtures
    # If adequate, reduce gradually
    await client.control.set_constant_pressure(2.5)  # Reduce to 2.5 m
    
    # Continue until minimum effective setpoint found
```

### 4. Use JSON Output for Logging

```bash
# Log to file for long-term analysis
alpha-hwr monitor --format json >> pump_log_$(date +%Y%m%d).json

# Analyze later with jq or Python
jq '.flow_m3h' pump_log_20260130.json | awk '{sum+=$1; count++} END {print sum/count}'
```

## System Diagnostics

### Interpreting Common Scenarios

#### Scenario: No Flow, High Head

```
Flow: 0.00 m³/h
Head: 5.5 m
Speed: 3500 RPM
Power: 15 W
```

**Diagnosis:** Closed valve or complete blockage  
**Action:** Check all valves in return line, verify no closed isolation valves

#### Scenario: Low Flow, Very High Head

```
Flow: 0.3 m³/h
Head: 4.8 m
Speed: 4000 RPM
Power: 28 W
```

**Diagnosis:** Partial blockage or severely restricted system  
**Action:** Check for:

- Sediment buildup in pipes
- Partially closed balancing valves
- Undersized pipe sections
- Air trapped in high points

#### Scenario: High Flow, Low Head, High Power

```
Flow: 3.0 m³/h
Head: 0.5 m
Speed: 3800 RPM
Power: 38 W
```

**Diagnosis:** Oversized system or bypass open  
**Action:**

- Verify all bypass valves are closed
- Consider flow limiting to reduce energy waste
- Check for unintended parallel paths

#### Scenario: Normal Flow/Head, Excessive Power

```
Flow: 1.2 m³/h
Head: 2.5 m
Speed: 2800 RPM
Power: 45 W
```

**Diagnosis:** Motor/bearing issue  
**Action:** Contact service - motor may need maintenance

## CLI Commands for Monitoring

```bash
# Real-time monitoring
alpha-hwr monitor

# Compact single-line updates
alpha-hwr monitor --format compact

# JSON for logging/automation
alpha-hwr monitor --format json

# Custom update interval
alpha-hwr monitor --interval 5

# Get single snapshot
alpha-hwr monitor --format json | head -1
```

## Python API Examples

### Basic Telemetry

```python
from alpha_hwr import AlphaHWRClient

async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
    telemetry = await client.telemetry.read_once()
    
    print(f"Flow: {telemetry.flow_m3h:.2f} m³/h")
    print(f"Head: {telemetry.head_m:.2f} m")
    print(f"Power: {telemetry.power_w:.1f} W")
    print(f"Temperature: {telemetry.media_temperature_c:.1f} °C")
    print(f"Speed: {telemetry.speed_rpm:.0f} RPM")
```

### Continuous Monitoring with Analysis

```python
import asyncio
from alpha_hwr import AlphaHWRClient


async def monitor_with_analysis(duration_seconds=60):
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        flow_samples = []
        head_samples = []

        for _ in range(duration_seconds // 2):  # Sample every 2 seconds
            telemetry = await client.telemetry.read_once()

            flow_samples.append(telemetry.flow_m3h)
            head_samples.append(telemetry.head_m)

            await asyncio.sleep(2)

        # Calculate statistics
        avg_flow = sum(flow_samples) / len(flow_samples)
        avg_head = sum(head_samples) / len(head_samples)

        print(f"Average Flow: {avg_flow:.2f} m³/h")
        print(f"Average Head: {avg_head:.2f} m")
        print(
            f"Flow Stability: {max(flow_samples) - min(flow_samples):.2f} m³/h range"
        )
        print(
            f"Head Stability: {max(head_samples) - min(head_samples):.2f} m range"
        )


asyncio.run(monitor_with_analysis())
```

## See Also

- [CLI Guide](cli_guide.md) - Complete CLI command reference
- [Control Modes](control_modes.md) - Detailed control mode documentation
- [Data Models](../reference/data_models.md) - Telemetry data structure reference
- [Hardware Reference](../reference/hardware.md) - Physical specifications and limits