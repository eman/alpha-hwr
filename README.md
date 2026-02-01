# Grundfos ALPHA HWR Python Client

A modern Python library and CLI for interacting with Grundfos ALPHA HWR pumps via Bluetooth Low Energy (BLE).

## Features

- **Passive Monitoring**: Continuously monitor pump telemetry (Flow, Head, Power, Temperature, Voltage/Current, Speed).
- **Status Reading**: Read current control mode, setpoint values (with min/max limits), alarms/warnings, cumulative statistics, and device information.
- **Active Control**: Set pump modes and setpoints with automatic validation (Constant Pressure, Proportional Pressure, Constant Speed, Constant Flow, AutoAdapt variants).
- **Schedule Management**: Read and write weekly schedules across 5 independent layers with comprehensive validation.
- **Type-Safe**: Fully typed API using standard Python type hints and Pydantic models.
- **AsyncIO**: Built on `bleak` for efficient asynchronous BLE communication.
- **CLI**: Built-in command-line interface for quick diagnostics and control.

## Installation

```bash
pip install .
```

## Configuration

The library supports cross-platform device addressing and automatic discovery. Create a `.env` file in your project root:

```bash
# BLE Device Address
# Format is platform-specific:
# - macOS: Uses UUID format (e.g., "A1B2C3D4-E5F6-7890-1234-567890ABCDEF")
# - Linux/Windows: Uses MAC address format (e.g., "00:11:22:33:44:55")
# 
# Seamless Cross-Platform: You can provide a comma-separated list of addresses.
# The library automatically picks the correct one for your current OS.
ALPHA_HWR_DEVICE_ADDRESS="A1B2C3D4-E5F6-7890-1234-567890ABCDEF, 00:11:22:33:44:55"
```

### Automatic Discovery

If you don't provide a device address (either via `.env` or as a parameter), the library will automatically attempt to discover and connect to any nearby ALPHA HWR pump.

## Usage

### CLI

**Discovery:**
```bash
# Scan for nearby pumps
alpha-hwr device scan
```

**Monitoring:**
```bash
# Monitor default device
alpha-hwr monitor
```

**Device Information:**
```bash
# Get device information
alpha-hwr device info

# Get cumulative statistics (operating hours, start count)
alpha-hwr device stats

# Check for active alarms and warnings
alpha-hwr device alarms
```

**Control Commands:**
```bash
# Show current control mode and setpoint
alpha-hwr control status

# Start/stop pump
alpha-hwr control start
alpha-hwr control stop

# Set constant pressure mode (meters of water column)
alpha-hwr control set-pressure 1.5

# Set constant speed mode (RPM)
alpha-hwr control set-speed 2500
```

**History & Events:**
```bash
# Show historical trend data (last 10 cycles)
alpha-hwr history trends

# Show full 100-cycle history
alpha-hwr history trends --detailed

# List pump event log
alpha-hwr events list
```

**Schedule Management:**
```bash
# Read current schedule
alpha-hwr schedule list

# Enable/disable the schedule
alpha-hwr schedule enable
alpha-hwr schedule disable
```

**Configuration Backup & Restore:**
```bash
# Backup pump configuration (schedules, modes, setpoints)
alpha-hwr config backup pump_config.json

# Restore configuration from backup
alpha-hwr config restore pump_config.json
```

### Library

**Basic Monitoring:**
```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def main():
    async with AlphaHWRClient("DEVICE_UUID") as client:
        # Authenticate first
        await client.pair_device()
        
        # Get single reading
        telemetry = await client.read_telemetry()
        print(f"Flow: {telemetry.flow_m3h} m3/h")
        
        # Continuous monitoring
        async for data in client.monitor():
            print(data)

if __name__ == "__main__":
    asyncio.run(main())
```

**Reading Status Information:**
```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def main():
    async with AlphaHWRClient("DEVICE_UUID") as client:
        await client.pair_device()
        
        # Get current control mode
        mode = await client.get_control_mode()
        print(f"Mode: {mode}")
        
        # Read current setpoint with limits
        setpoint = await client.read_current_setpoint(include_limits=True)
        if setpoint:
            value, unit = setpoint.get_display_value()
            print(f"Setpoint: {value:.2f} {unit}")
            
            if setpoint.min_setpoint:
                limits = setpoint.get_limits_display()
                if limits:
                    (min_val, min_unit), (max_val, max_unit) = limits
                    print(f"Limits: {min_val:.2f} - {max_val:.2f} {max_unit}")
        
        # Check for alarms
        alarms = await client.read_alarms()
        if alarms and alarms.alarm_code and alarms.alarm_code != 0:
            print(f"ALARM: {alarms.alarm_description}")
        
        # Read cumulative statistics
        stats = await client.read_statistics()
        if stats:
            print(f"Operating Hours: {stats.operating_hours:.1f} h")
            print(f"Start Count: {stats.start_count}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Setting Control Modes and Setpoints:**
```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def main():
    async with AlphaHWRClient("DEVICE_UUID") as client:
        await client.pair_device()
        
        # Set constant pressure mode (automatic validation against limits)
        success = await client.set_constant_pressure(1.5)  # 1.5 meters
        if success:
            print("Pressure setpoint updated successfully")
        
        # Set proportional pressure mode
        success = await client.set_proportional_pressure(1.2)  # 1.2 meters
        
        # Set constant speed mode
        success = await client.set_constant_speed(2500)  # 2500 RPM
        
        # Set constant flow mode
        success = await client.set_constant_flow(2.0)  # 2.0 m³/h
        
        # Set AutoAdapt Radiator mode
        success = await client.set_autoadapt_radiator(3.0)  # 3.0 meters
        
        # Set AutoAdapt Underfloor mode
        success = await client.set_autoadapt_underfloor(2.5)  # 2.5 meters
        
        # Set AutoAdapt Radiator+Underfloor combined mode
        success = await client.set_autoadapt_combined(3.5)  # 3.5 meters
        
        # Validate a setpoint before setting
        is_valid, error = await client.validate_setpoint(
            value=9804.0,  # Pascals for pressure modes
            control_mode=0,  # Constant Pressure
            strict=True
        )
        if not is_valid:
            print(f"Invalid setpoint: {error}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Schedule Management:**
```python
import asyncio
from alpha_hwr import AlphaHWRClient
from alpha_hwr.models import ScheduleEntry

async def main():
    async with AlphaHWRClient("DEVICE_UUID") as client:
        await client.pair_device()
        
        # Enable the schedule
        await client.set_schedule_enabled(True)
        
        # Set a schedule entry for Monday 06:00-08:30
        success = await client.set_schedule_entry(
            day="monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=30,
            layer=0  # Layer 0-4 (supports 5 independent schedules)
        )
        
        # Set multiple entries at once
        entries = [
            ScheduleEntry(day="monday", begin_hour=6, begin_minute=0, 
                         end_hour=8, end_minute=30, layer=0),
            ScheduleEntry(day="tuesday", begin_hour=18, begin_minute=0,
                         end_hour=22, end_minute=0, layer=0),
        ]
        await client.set_weekly_schedule(entries, layer=0)
        
        # Read current schedule
        schedule = await client.read_weekly_schedule(layer=0)
        for entry in schedule:
            print(f"{entry.day}: {entry.begin_hour:02d}:{entry.begin_minute:02d} - "
                  f"{entry.end_hour:02d}:{entry.end_minute:02d}")
        
        # Clear a specific day
        await client.clear_schedule_entry("wednesday", layer=0)
        
        # Clear entire layer
        await client.clear_schedule_layer(layer=0)
        
        # Export schedule to JSON
        await client.export_schedule_json("schedule_backup.json")
        
        # Import schedule from JSON
        import json
        with open("schedule_backup.json", "r") as f:
            schedule_data = json.load(f)
        # ... process and set schedule

if __name__ == "__main__":
    asyncio.run(main())
```

**Configuration Backup & Restore:**
```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def main():
    async with AlphaHWRClient("DEVICE_UUID") as client:
        await client.pair_device()
        
        # Backup configuration
        success = await client.backup_configuration("pump_backup.json")
        if success:
            print("Configuration backed up successfully")
        
        # Restore configuration
        success = await client.restore_configuration("pump_backup.json")
        if success:
            print("Configuration restored successfully")

if __name__ == "__main__":
    asyncio.run(main())
```

## Supported Features

### Control Modes

The ALPHA HWR supports **8 out of 32 GENI protocol control modes** (25%), specifically those needed for residential heating applications:

| Mode | Name | Status | Setpoint Range |
|------|------|--------|----------------|
| 0 | Constant Pressure |  Fully Supported | 0.0 - 6.0 m |
| 1 | Proportional Pressure |  Fully Supported | 0.0 - 6.0 m |
| 2 | Constant Speed |  Fully Supported | 1000 - 4200 RPM |
| 8 | Constant Flow |  Fully Supported | 0.0 - 4.5 m³/h |
| 5 | AutoAdapt (Generic) |  Limited Support | 0.0 - 6.0 m (see docs) |
| 13 | AutoAdapt Radiator |  Fully Supported | 0.0 - 6.0 m |
| 14 | AutoAdapt Underfloor |  Fully Supported | 0.0 - 6.0 m |
| 15 | AutoAdapt Radiator+Underfloor |  Fully Supported | 0.0 - 6.0 m |

**Unsupported Modes (24 total):** Chemical dosing (16-19), level control (9, 22), differential pressure (11, 12, 26), CEOPS/industrial modes (7, 10, 20-21, 23-25, 27-30, 128). See [Control Modes Matrix](https://eman.github.io/alpha-hwr/protocol/control_modes/) for details.

### Advanced Features

| Feature | Status | Notes |
|---------|--------|-------|
| Real-time Telemetry | Supported | Flow, head, power, temp, voltage, current, RPM |
| Setpoint Limits | Supported | Min/max/default from factory config |
| Setpoint Validation | Supported | Automatic validation before writes |
| Alarm/Warning System | Supported | Current state only (98+ error codes) |
| Operating Statistics | Supported | Operating hours, start count |
| Weekly Schedules | Supported | 5 independent layers, full CRUD |
| Schedule Import/Export | Supported | JSON format |
| Config Backup/Restore | Supported | Full configuration backup |
| Historical Data | Supported | 100-cycle history for flow, head, temp, power |
| Event Log | Supported | Last 20 pump events with timestamps and modes |
| Multi-pump (CEOPS) | Not Available | Residential pump only |
| Cumulative Energy (kWh) | Not Available | Instantaneous power available |

## Documentation

Complete documentation is available at [https://eman.github.io/alpha-hwr/](https://eman.github.io/alpha-hwr/).

*   [**Getting Started**](https://eman.github.io/alpha-hwr/getting_started/installation/)
*   [**CLI Guide**](https://eman.github.io/alpha-hwr/guides/cli_guide/)
*   [**API Reference**](https://eman.github.io/alpha-hwr/api/client/)
*   [**Protocol Details**](https://eman.github.io/alpha-hwr/protocol/ble_architecture/)

## Project Status

**Status:** Production-ready for ALPHA HWR series.

**Test Coverage:** 204 passing tests, 100% of hardware features tested on real ALPHA HWR pump.

**Key Features Implemented:**
- Real-time telemetry (Flow, Head, Power, Temp, Electrical)
- Full motor control (Start/Stop, Mode switching)
- Advanced setpoint management with validation
- Comprehensive weekly schedule management (5 layers)
- Configuration backup and restore
- Detailed device information (Serial, Firmware)

## Contributing

Contributions are welcome! Please ensure:
- All tests pass (`tox`)
- Code follows project style (ruff, mypy, basedpyright)
- New features include tests and documentation

## License

See LICENSE file for details.
