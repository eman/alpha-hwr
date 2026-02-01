# Time Management

The Grundfos ALPHA HWR pump maintains an internal real-time clock (RTC) used for schedule execution (e.g., Comfort Level scheduling) and event logging. This guide explains how to read, synchronize, and understand the pump's timekeeping mechanism.

## Overview

The pump's timekeeping is managed via GENI DataObjects (Class 10). While older protocols used simple Unix timestamps (Class 14/16), modern firmware relies on **Object 94**, which provides a structured date and time representation (Year, Month, Day, Hour, Minute, Second, etc.).

### Key Objects

| Object | SubID | Name | Description |
| :--- | :--- | :--- | :--- |
| **Object 94** | 101 | `DateTimeActual` | The actual local Date and Time. |
| **Object 94** | 100 | `DateTimeConfig` | Configuration for setting the local Date and Time. |
| **Object 94** | 102 | `DaylightSavingTime` | DST configuration. |
| **Object 94** | 103 | `UtcOffset` | UTC offset (default is CET/UTC+1). |

## Using the CLI

The simplest way to manage the pump's clock is via the `alpha-hwr clock` command group.

### View Clock

To check the current pump time vs. your system time:

```bash
alpha-hwr clock view
```

Example output:

```text
Connecting to configured device...
Pump Clock:   2026-01-30 11:35:42
System Clock: 2026-01-30 11:55:12
Offset:       +1170.0 seconds
```

### Sync Clock

If the pump clock has drifted or was never set (often showing dates in 1970-1974), you can synchronize it with your current system time:

```bash
alpha-hwr clock sync
```

This command performs several steps:

1. Constructs a `DateTimeConfig` payload matching your system time.
2. Sends the command using MTU fragmentation (required for the 21-byte packet).
3. Sends a mandatory **Configuration Commit** to persist the changes.

## Using the Python API

You can programmatically manage the clock using the `AlphaHWRClient` and its `clock` service.

### Read via API

```python
from alpha_hwr import AlphaHWRClient

async with AlphaHWRClient(address) as client:
    await client.authenticate(fast_mode=True)
    
    clock = await client.clock.get_clock()
    if clock:
        print(f"Pump time: {clock}")
    else:
        print("Clock is unset or failed to read.")
```

`get_clock()` returns a standard Python `datetime` object. If the pump returns an uninitialized state, it may return epoch time (1970-01-01).

### Sync via API

```python
await client.clock.set_clock()  # Synchronizes with current LOCAL system time
# OR
from datetime import datetime
await client.clock.set_clock(datetime(2026, 12, 25, 10, 0, 0))
```

## Protocol Details

### MTU Fragmentation

The ALPHA HWR has a strict **20-byte MTU limit** for BLE writes. Setting the clock requires a 21-byte GENI packet. The library automatically splits this into two writes (20 bytes + 1 byte) with a small delay.

### Configuration Commit

After writing to `DateTimeConfig` (SubID 100), the motor controller requires a **Commit** command to apply the changes. The library automatically handles this to finalize the synchronization.