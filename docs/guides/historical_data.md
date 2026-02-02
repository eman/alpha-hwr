# Historical Data & Event Log Guide

This guide explains how to access pump cycle history, trend data, and event logs from the Grundfos ALPHA HWR pump.

## Overview

The ALPHA HWR pump stores historical data about its operation, including:

- **Historical Trends**: 100 cycles of flow, head, temperature, and power-on time (Object 53).
- **Cycle Timestamps**: Exact times when the last 100 cycles occurred (Object 88).
- **Event Log**: A detailed record of the last 20 operational events (Object 88).

Unlike basic telemetry which is real-time, historical data allows you to analyze pump performance over days or weeks.

---

## Historical Trends (Object 53)

The pump maintains two resolutions of trend data for key metrics:
1. **High Resolution**: Last 10 cycles.
2. **Standard Resolution**: Last 100 cycles.

Supported metrics:
- **Flow Rate** ($m^3/h$)
- **Head Pressure** (meters)
- **Media Temperature** (°C)
- **Power-On Time** (hours)

### CLI Usage

```bash
# Show last 10 cycles of trend data (table format)
alpha-hwr history trends

# Show full 100-cycle history
alpha-hwr history trends --detailed
```

---

## Event Log (Object 88)

The pump maintains a rolling buffer of the last **20 operational events**. Each entry captures:
- Pump Cycle Number
- Event Timestamp (UTC)
- Active Control Mode at time of event
- Event Type (Start or Stop)

### CLI Usage

```bash
# List all events
alpha-hwr events list

# Show metadata (cycle counter, buffer status)
alpha-hwr events metadata

# Show specific event details
alpha-hwr events show 0
```

---

## Library Usage (Python)

### Get Trend Data

```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def main():
    async with AlphaHWRClient("DEVICE_UUID") as client:
        await client.authenticate(fast_mode=True)
        
        # Get all trend data
        trends = await client.history.get_trend_data()
        
        if trends and trends.flow_series:
            print(f"Current flow: {trends.flow_series.cycle_10_points[0].value} m\u00b3/h")
            
            # Access historical points
            for point in trends.flow_series.cycle_10_points:
                print(f"  {point.timestamp}: {point.value}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Get Event Log

```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def main():
    async with AlphaHWRClient("DEVICE_UUID") as client:
        await client.authenticate(fast_mode=True)
        
        # Get all event entries
        entries = await client.event_log.get_all_entries()
        
        for entry in entries:
            print(f"Cycle {entry.cycle_counter}: {entry.timestamp}")
            print(f"  Type: {entry.event_type.name}, Mode: {entry.mode_name}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## API Reference

For detailed API documentation, see:

- [`HistoryService`](../api/services.md#historyservice)
- [`EventLogService`](../api/services.md#eventlogservice)
- [`TrendDataCollection`](../api/models.md)
- [`EventLogEntry`](../api/models.md)
