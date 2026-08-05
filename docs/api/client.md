# Client API

The `AlphaHWRClient` is the main entry point for interacting with Grundfos ALPHA HWR pumps. It provides a service-oriented architecture where specialized services handle different aspects of pump communication.

## Overview

The client acts as a facade and coordinator for specialized services:

- **Telemetry** - Real-time sensor data and monitoring
- **Control** - Pump control operations (start, stop, mode changes)
- **Schedule** - Weekly schedule management across 5 layers
- **Device Info** - Device identification and statistics
- **Configuration** - Backup and restore operations
- **Time** - Real-time clock management
- **History** - Historical trend data (100 cycles)
- **Event Log** - Pump event history (20 entries)

## Basic Usage

```python
import asyncio
from alpha_hwr import AlphaHWRClient


async def main():
    # Connect using context manager (automatic disconnect)
    async with AlphaHWRClient("AA:BB:CC:DD:EE:FF") as client:
        # Read telemetry
        data = await client.telemetry.read_once()
        print(f"Flow: {data.flow_m3h} m³/h")

        # Control pump
        await client.control.set_constant_pressure(1.5)

        # Manage schedules
        entries = await client.schedule.read_entries()


asyncio.run(main())
```

## API Reference

::: alpha_hwr.client.AlphaHWRClient
    options:
      members:
        - __init__
        - connect
        - disconnect
        - authenticate
        - __aenter__
        - __aexit__
        - telemetry
        - control
        - device_info
        - schedule
        - history
        - event_log
        - time
        - single_events
        - writes
        - config
        - is_ready
        - wait_until_ready
        - get_run_state
        - set_run_state
      show_root_heading: true
      show_source: false
      heading_level: 3
