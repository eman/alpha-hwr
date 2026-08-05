# Grundfos ALPHA HWR Python Library

[![PyPI](https://img.shields.io/pypi/v/alpha-hwr)](https://pypi.org/project/alpha-hwr/)
[![Python](https://img.shields.io/pypi/pyversions/alpha-hwr)](https://pypi.org/project/alpha-hwr/)
[![Tests](https://github.com/eman/alpha-hwr/actions/workflows/tests.yml/badge.svg)](https://github.com/eman/alpha-hwr/actions/workflows/tests.yml)
[![Documentation](https://img.shields.io/badge/docs-github%20pages-blue)](https://eman.github.io/alpha-hwr/)
[![License](https://img.shields.io/pypi/l/alpha-hwr)](https://github.com/eman/alpha-hwr/blob/main/LICENSE)

Python library and CLI for controlling Grundfos ALPHA HWR pumps via Bluetooth Low Energy.

> **Not affiliated with, endorsed by, or associated with Grundfos.** This is an
> independent client, built by reverse-engineering the pump's BLE interface.
> Incorrect use of motor control commands could in principle damage hardware,
> though the pump's own firmware limits generally prevent it.

## Features

- Automatic discovery and guidance for pairing/bonding ALPHA HWR pumps
- Stream telemetry data (flow, pressure, power, temperature)
- Set pump modes and setpoints with automatic validation
- Create and manage time-based operation schedules
- Save and restore complete pump configurations
- Full type hints and validation with Pydantic
- Built on async Python for efficient BLE communication
- Command-line interface for quick operations

## Installation

```bash
pip install alpha-hwr
```

**Requirements:** Python 3.13+ with Bluetooth Low Energy support

> **Important:** Most pumps require the host to be paired/bonded before
> telemetry and control work reliably. If your OS prompts for pairing on first
> connect, accept it before trying to read data.

## Quick Start

### Command Line

```bash
# Discover nearby pumps
alpha-hwr device scan

# Monitor telemetry in real-time
alpha-hwr monitor live --device AA:BB:CC:DD:EE:FF

# Check pump status
alpha-hwr control status --device AA:BB:CC:DD:EE:FF

# Set constant pressure mode (1.5 meters)
alpha-hwr control set-pressure 1.5 --device AA:BB:CC:DD:EE:FF
```

### Python Library

```python
import asyncio
from alpha_hwr import AlphaHWRClient


async def main():
    # Connect to pump (auto-discovery or specific address)
    async with AlphaHWRClient("AA:BB:CC:DD:EE:FF") as client:
        # Read telemetry
        telemetry = await client.telemetry.read_once()
        print(f"Flow: {telemetry.flow_m3h} m³/h")
        print(f"Head: {telemetry.head_m} m")
        print(f"Power: {telemetry.power_w} W")

        # Set constant pressure mode
        await client.control.set_constant_pressure(1.5)  # 1.5 meters

        # Read device info
        info = await client.device_info.read_info()
        print(f"Serial: {info.serial_number}")
        print(f"Software: {info.software_version}")


asyncio.run(main())
```

## Supported Control Modes

The ALPHA HWR supports 5 primary modes optimized for domestic hot water recirculation:

| Mode | Setpoint Range | Notes |
|------|---------------|-------|
| **Temperature Control** | 20-60°C | Dual setpoints (min/max), AUTOADAPT flow adjustment, optional Flow Limit |
| **Cycle Time Control** | 1-60 min | Configurable ON/OFF durations |
| **Constant Curve** | 1000-4500 RPM | Fixed speed with optional Flow Limit |
| **Constant Pressure** | 0.5-6.0 m | Fixed head pressure |
| **Constant Flow** | 0.1-3.0 m³/h | Fixed flow rate |

Proportional Pressure (0.5-6.0 m) is also fully supported.

## Documentation

**Complete documentation:** [https://eman.github.io/alpha-hwr/](https://eman.github.io/alpha-hwr/)

- [Installation Guide](https://eman.github.io/alpha-hwr/getting_started/installation/)
- [Quick Start Tutorial](https://eman.github.io/alpha-hwr/getting_started/quick_start/)
- [CLI Reference](https://eman.github.io/alpha-hwr/guides/cli_guide/)
- [Python API Reference](https://eman.github.io/alpha-hwr/api/client/)
- [Control Modes Guide](https://eman.github.io/alpha-hwr/guides/control_modes/)
- [Protocol Documentation](https://eman.github.io/alpha-hwr/protocol/ble_architecture/)

## Examples

### Monitor Telemetry Stream

```python
async with AlphaHWRClient(address) as client:
    # Stream telemetry updates
    async for telemetry in client.telemetry.monitor():
        print(
            f"Flow: {telemetry.flow_m3h:.2f} m³/h, "
            f"Head: {telemetry.head_m:.2f} m, "
            f"Power: {telemetry.power_w:.1f} W"
        )
```

### Manage Schedules

```python
from alpha_hwr.models import ScheduleEntry

async with AlphaHWRClient(address) as client:
    # Create a schedule entry for Monday 6:00 AM - 8:30 AM
    entry = ScheduleEntry(
        day="Monday",
        begin_hour=6,
        begin_minute=0,
        end_hour=8,
        end_minute=30,
        layer=0,
    )

    # Write schedule and enable it
    await client.schedule.write_entries([entry], layer=0)
    await client.schedule.enable()
```

### Backup & Restore Configuration

```python
async with AlphaHWRClient(address) as client:
    # Backup current configuration
    await client.config.backup("pump_backup.json")
    
    # Restore from backup
    await client.config.restore("pump_backup.json")
```

## Project Status

Actively maintained and tested on real ALPHA HWR hardware.

## Home Assistant

For Home Assistant integration, it is suggested to use the ESPHome component instead of this library: [esphome-alpha-hwr](https://github.com/eman/esphome-alpha-hwr). It runs on an ESP32 as a Bluetooth proxy, exposing the pump as native Home Assistant sensors without requiring a Python host.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - See [LICENSE](LICENSE) for details.

## Links

- **PyPI:** https://pypi.org/project/alpha-hwr/
- **Documentation:** https://eman.github.io/alpha-hwr/
- **Source Code:** https://github.com/eman/alpha-hwr
- **Issue Tracker:** https://github.com/eman/alpha-hwr/issues
