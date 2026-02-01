# Energy and Power Information

This document explains energy and power data availability on the Grundfos ALPHA HWR pump.

## Summary

-  **Instantaneous Power (W)** - Available via telemetry streaming
-  **Cumulative Energy (kWh)** - NOT available on ALPHA HWR

---

## Instantaneous Power and Electrical Data

### Available via Telemetry

Real-time power consumption, grid voltage, and current are available through the **Motor State** telemetry object.

**Protocol Details:**
- **Class:** 10 (DataObject)
- **SubID:** `0x0045` (69)
- **ObjID:** `0x0057` (87)
- **Streaming:** Automatic notifications when pump is running
- **Update Rate:** ~10 Hz

**Data Format (Motor State):**

| Offset | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| +0 | Float32 | V | Grid voltage (AC) |
| +8 | Float32 | A | Current |
| +16 | Float32 | W | Power consumption |
| +20 | Float32 | RPM | Actual motor speed |

**Example:**
```python
# The library automatically updates these fields in the telemetry snapshot
telemetry = await client.telemetry.read_once()

print(f"Grid Voltage: {telemetry.voltage_ac_v} V")
print(f"Current: {telemetry.current_a} A")
print(f"Power: {telemetry.power_w} W")
print(f"Speed: {telemetry.speed_rpm} RPM")
```

**Typical Values:**
- **Voltage:** 115-125 V (Residential US)
- **Power:** 2-38 W (ALPHA HWR 15-60)
- **Speed:** 0-4500 RPM
- **Current:** 0.05-0.4 A

---

## Cumulative Energy Consumption - NOT SUPPORTED

### Object 77 Investigation

The GENI protocol documentation mentions **Object 77 (power_and_energy_info_obj)** for storing cumulative energy data. However, **the ALPHA HWR does NOT implement this object**.

**Hardware Testing Results:**

All SubIDs tested on a real ALPHA HWR (Family 52, Type 7) returned empty responses:

```python
# Test results for Object 77
SubID 0:    No data (status 0x81 = not available)
SubID 1:    No data
SubID 2:    No data
```

**Workaround: Manual Calculation**

You can estimate cumulative energy from operating hours and average power:

```python
stats = await client.device_info.read_statistics()
operating_hours = stats.operating_hours

# Assume average power consumption (depends on usage pattern)
avg_power_w = 15.0 

# Calculate approximate energy
energy_kwh = (operating_hours * avg_power_w) / 1000.0
print(f"Estimated energy: {energy_kwh:.2f} kWh")
```

---

## Comparison with Statistics

### Available Data (Object 93)

The pump DOES provide cumulative operating statistics via **Object 93, SubID 1**:

```python
stats = await client.device_info.read_statistics()
print(f"Operating hours: {stats.operating_hours:.1f} h")
print(f"Start count: {stats.start_count}")
```

**Object 93 Data:**
- **Operating Hours** - Total runtime in hours
- **Start Count** - Number of pump starts

---

## Summary Table

| Feature | Available | Source | Update Rate |
|---------|-----------|--------|-------------|
| Instantaneous Power (W) | Yes | Object 0x0045/0x0057 | ~10 Hz |
| Grid Voltage (V) | Yes | Object 0x0045/0x0057 | ~10 Hz |
| Current (A) | Yes | Object 0x0045/0x0057 | ~10 Hz |
| Cumulative Energy (kWh) | No | - | - |
| Operating Hours | Yes | Object 93 | On-demand |
| Start Count | Yes | Object 93 | On-demand |


---

## Related Documentation

- [BLE Architecture](ble_architecture.md) - Object mapping and protocol structure
- [Telemetry](telemetry.md) - Real-time data streaming
- [Device Info](device_info.md) - Device identification limitations
