# Quick Start Guide

This guide will help you connect to your Grundfos ALPHA HWR pump, authenticate, and read live telemetry data using Python.

## 1. Scan for the Device

First, you need to find the Bluetooth address of your pump. You can use any BLE scanner app (like nRF Connect) or a simple Python script using `bleak`.

The pump usually advertises with a name like `Grundfos` or `HWR`.

```python
import asyncio
from bleak import BleakScanner

async def scan():
    devices = await BleakScanner.discover()
    for d in devices:
        print(f"Address: {d.address} | Name: {d.name}")

asyncio.run(scan())
```

**Note the Address:**
*   **macOS:** It will be a UUID (e.g., `A1B2C3D4-E5F6-...`).
*   **Linux/Windows:** It will be a MAC address (e.g., `00:11:22:33:44:55`).

## 2. Basic Connection Script

Create a file named `monitor_pump.py`. This script connects to the pump, performs the required handshake, and prints telemetry updates.

```python
import asyncio
import logging
from alpha_hwr.client import AlphaHWRClient

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

async def main():
    # Replace with your pump's address found in Step 1
    # address = "00:11:22:33:44:55"  # Linux/Windows
    address = "YOUR-DEVICE-UUID-HERE" # macOS

    client = AlphaHWRClient(address=address)

    try:
        # 1. Connect
        await client.connect()
        print("Connected!")

        # 2. Authenticate (Critical Step)
        # Without this, the pump will not accept commands or stream full data.
        success = await client.authenticate(fast_mode=True)
        if not success:
            print("Authentication failed!")
            return
        print("Authenticated successfully.")

        # 3. Monitor Telemetry
        print("Listening for data... (Press Ctrl+C to stop)")
        while True:
            # The client automatically processes incoming notifications
            data = client.telemetry.current
            
            # Print latest known state
            if data:
                print(f"Flow: {data.flow_m3h} m³/h | Power: {data.power_w} W")
            
            await asyncio.sleep(2.0)

    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

## 3. Running the Script

Run the script from your terminal:

```bash
python monitor_pump.py
```

**Expected Output:**

```text
INFO:alpha_hwr.client:Connecting to BLE device...
INFO:alpha_hwr.client:BLE Connection successful...
Connected!
INFO:alpha_hwr.client:Starting authentication handshake...
INFO:alpha_hwr.client:Authentication handshake sent.
Authenticated successfully.
Listening for data...
Flow: 0.0 m³/h | Power: 0.0 W
Flow: 1.2 m³/h | Power: 25.0 W
...
```

## 4. Using the CLI

### Finding Your Device

The library includes a convenient CLI for device discovery and management:

```bash
# Discover nearby pumps
alpha-hwr device scan

# Save a device for later use (no need to remember the address!)
alpha-hwr device set AA:BB:CC:DD:EE:FF --name my-pump --default

# List all saved devices
alpha-hwr device list
```

See the [Device Profiles Guide](../guides/device-profiles.md) for more details on managing multiple devices.

### Monitoring:**
```bash
# Continuously monitor telemetry
alpha-hwr monitor live

# JSON output for automation
alpha-hwr monitor live --format json
```

**Status Commands:**
```bash
# Check current control mode and setpoint
alpha-hwr control status

# Check for alarms and warnings
alpha-hwr device alarms

# Read cumulative statistics (operating hours, start count)
alpha-hwr device stats

# Get device information
alpha-hwr device info
```

**Control Commands:**
```bash
# Start/Stop pump
alpha-hwr control start
alpha-hwr control stop

# Set control modes with setpoint values
alpha-hwr control set-pressure 1.5
alpha-hwr control set-speed 2500
alpha-hwr control set-flow 0.8
```

## 5. Reading Status Information

Beyond telemetry, you can read the pump's current configuration and status:

```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def read_status():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)
        
        # Get current control mode and setpoint
        info = await client.control.get_mode()
        if info:
            print(f"Control Mode: {info.control_mode.name}")
            value, unit = info.get_display_value()
            print(f"Setpoint: {value:.2f} {unit}")
        
        # Read cumulative statistics
        stats = await client.device_info.read_statistics()
        if stats:
            print(f"Operating hours: {stats.operating_hours:.1f} h")
            print(f"Start count: {stats.start_count}")
        
        # Check for alarms/warnings
        alarms = await client.device_info.read_alarms()
        if alarms:
            if alarms.active_alarms:
                print(f"ALARMS: {alarms.active_alarms}")
            if alarms.active_warnings:
                print(f"WARNINGS: {alarms.active_warnings}")

asyncio.run(read_status())
```

## 6. Controlling the Pump

You can change control modes and setpoints programmatically:

```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def control_pump():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)
        
        # Set constant pressure mode
        await client.control.set_constant_pressure(1.5)  # 1.5 meters
        print("Set to Constant Pressure: 1.5m")
        
        # Set constant speed mode
        await client.control.set_constant_speed(2500)  # 2500 RPM
        print("Set to Constant Speed: 2500 RPM")
        
        # Start/Stop pump
        await client.control.start()
        print("Pump started")
        
        await asyncio.sleep(5)
        
        await client.control.stop()
        print("Pump stopped")

asyncio.run(control_pump())
```

## 7. Working with Schedules

You can read and validate pump schedules:

```python
import asyncio
from alpha_hwr import AlphaHWRClient, ScheduleEntry

async def work_with_schedules():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)
        
        # Check if schedule is enabled
        enabled = await client.schedule.get_state()
        print(f"Schedule enabled: {enabled}")
        
        # Read current schedule
        entries = await client.schedule.read_entries()
        for entry in entries:
            print(f"  {entry.day}: {entry.begin_time} - {entry.end_time}")
        
        # Enable the schedule
        await client.schedule.enable()
        print("\nSchedule enabled")

asyncio.run(work_with_schedules())
```

## 8. Backup and Restore Configuration

You can backup and restore the complete pump configuration:

```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def backup_restore_config():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)
        
        # Backup current configuration
        success = await client.config.backup("pump_backup.json")
        if success:
            print("Configuration backed up to pump_backup.json")
        
        # Restore configuration
        success = await client.config.restore("pump_backup.json")
        if success:
            print("Configuration restored from backup")

asyncio.run(backup_restore_config())
```

**CLI Commands:**
```bash
# Backup current configuration
alpha-hwr config backup pump_backup.json

# Restore configuration (with confirmation prompt)
alpha-hwr config restore pump_backup.json
```

## 9. Next Steps

*   Learn how to [Control the Pump](../protocol/control.md) (Start/Stop/Set Mode).
*   Understand the [Telemetry Data](../protocol/telemetry.md) in detail.
*   Read about the [Connection Protocol](../protocol/connection.md) if you are building a custom integration.
*   Explore the [API Reference](../api/client.md) for all available methods.