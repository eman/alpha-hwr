# Configuration Backup and Restore Guide

This guide explains how to backup and restore the complete configuration of your Grundfos ALPHA HWR pump using the alpha-hwr library.

## Overview

The backup and restore functionality allows you to:

* **Save your pump configuration** to a JSON file for safekeeping
* **Restore configuration** from a backup file
* **Transfer settings** between pumps (with caution)
* **Version control** your pump configuration using git or other tools
* **Quickly recover** from configuration mistakes

## What Gets Backed Up

A configuration backup includes:

1. **Device Information**
   - Serial number
   - Product name (ALPHA HWR)
   - Hardware version
   - Software version

2. **Control Mode Configuration**
   - Active control mode (e.g., Constant Pressure)
   - Setpoint value
   - Dual setpoints (e.g., Min/Max Temperature for Range Control)
   - Unit of measurement

3. **Schedule Configuration**
   - Global schedule enabled/disabled state
   - All schedule entries for all days
   - All 5 schedule layers (0-4)

## Backup File Format

Backups are stored as human-readable JSON files:

```json
{
  "version": "1.0",
  "timestamp": "2026-01-29T12:00:00Z",
  "device": {
    "serial_number": "12345678",
    "product_name": "ALPHA HWR",
    "hardware_version": "1.0",
    "software_version": "2.0"
  },
  "control_mode": {
    "mode_name": "Constant Pressure",
    "setpoint": 3.5,
    "setpoint_unit": "m"
  },
  "schedule": {
    "enabled": true,
    "days": [
      {
        "day": "Monday",
        "enabled": true,
        "action": 2,
        "begin_hour": 6,
        "begin_minute": 0,
        "end_hour": 8,
        "end_minute": 0,
        "begin_time": "06:00",
        "end_time": "08:00",
        "layer": 0
      }
    ]
  }
}
```

## Using the CLI

### Backup Configuration

The simplest way to backup your pump configuration:

```bash
# Backup to a file
alpha-hwr config backup pump_backup.json

# Backup with timestamp in filename
alpha-hwr config backup "pump_backup_$(date +%Y%m%d_%H%M%S).json"
```

The backup will be saved to the specified file. Parent directories will be created automatically if they don't exist.

### Restore Configuration

To restore a previously saved configuration:

```bash
# Full restore (prompts for confirmation)
alpha-hwr config restore pump_backup.json

# Skip the prompt
alpha-hwr config restore pump_backup.json -f
```

The restore is all-or-nothing: there is no dry run and no way to restore one
component in isolation from the CLI. The Python API's
`ConfigurationService.restore()` takes `verify_device=False` to bypass the
serial-number check.

!!! warning "Restore reports success before the pump has agreed"

    Restore drives the **unverified** setters, which return `bool` and do not
    read back. A value the pump clamps is still reported as restored — ask
    for 600 RPM and you get a success and a pump running at 1650. Read the
    state back with `alpha-hwr control status` afterwards, or restore through
    the [verified write path](verified_writes.md) if you need certainty.

!!! danger "If you restored on 0.6 or earlier, check your schedule"

    Every setpoint write was followed by a configuration commit built from a
    hardcoded blob whose `clock_program_enabled` byte was `0x00` — so a
    restore that set any setpoint **switched off a live weekly schedule**,
    silently. Run `alpha-hwr schedule list` and compare against what you
    expect. Fixed in 0.7.0; the commit is now read-modify-write.

## Using the Python API

### Basic Backup

```python
import asyncio
from alpha_hwr import AlphaHWRClient


async def backup_config():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)

        # Backup current configuration
        success = await client.config.backup("pump_backup.json")
        if success:
            print(" Configuration backed up successfully")
        else:
            print(" Backup failed")


asyncio.run(backup_config())
```

### Basic Restore

```python
import asyncio
from alpha_hwr import AlphaHWRClient


async def restore_config():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)

        # Restore configuration with all safety checks
        success = await client.config.restore("pump_backup.json")
        if success:
            print(" Configuration restored successfully")
        else:
            print(" Restore failed")


asyncio.run(restore_config())
```

### Selective Restore

You can restore only specific parts of the configuration:

```python
async def selective_restore():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)

        # Restore only control mode (skip schedule)
        await client.config.restore(
            "pump_backup.json", restore_mode=True, restore_schedule=False
        )

        # Or restore only schedule (skip control mode)
        await client.config.restore(
            "pump_backup.json", restore_mode=False, restore_schedule=True
        )
```

### Device Verification

By default, the restore process verifies that the serial number in the backup matches the connected pump. This prevents accidentally restoring to the wrong device.

```python
async def restore_with_verification():
    async with AlphaHWRClient("YOUR-DEVICE-UUID") as client:
        await client.authenticate(fast_mode=True)

        # Restore with device verification (default)
        success = await client.config.restore(
            "pump_backup.json",
            verify_device=True,  # This is the default
        )

        if not success:
            print("Restore failed - serial number mismatch")
```

To transfer a backup to a **different pump**, you must explicitly skip device verification:

```python
async def transfer_to_different_pump():
    async with AlphaHWRClient("DIFFERENT-PUMP-UUID") as client:
        await client.authenticate(fast_mode=True)

        # Skip device verification to restore to different pump
        success = await client.config.restore(
            "pump_backup.json",
            verify_device=False,  # Allow restoring to different device
        )

        if success:
            print(" Configuration transferred to new pump")
```

## Common Use Cases

### 1. Before Making Changes

Always backup before experimenting with settings:

```bash
# Backup current working configuration
alpha-hwr config backup pump_working.json

# Make experimental changes...
alpha-hwr control set-pressure 5.0

# If something goes wrong, restore
alpha-hwr config restore pump_working.json
```

### 2. Configuration Versioning

Store backups in a git repository for version control:

```bash
# Create dated backup
alpha-hwr config backup "backups/pump_$(date +%Y%m%d).json"

# Commit to git
git add backups/
git commit -m "Pump configuration backup - $(date)"

# Later, restore specific version
git log --oneline backups/
git checkout <commit> -- backups/pump_20260115.json
alpha-hwr config restore backups/pump_20260115.json
```

### 3. Scheduled Backups

Automate regular backups with a cron job or systemd timer:

```bash
# Create backup script
cat > /usr/local/bin/backup-pump.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/alpha-hwr"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
alpha-hwr config backup "$BACKUP_DIR/pump_$DATE.json"
# Keep only last 30 days
find "$BACKUP_DIR" -name "pump_*.json" -mtime +30 -delete
EOF

chmod +x /usr/local/bin/backup-pump.sh

# Add to crontab (daily at 2am)
# 0 2 * * * /usr/local/bin/backup-pump.sh
```

### 4. Deployment Across Multiple Pumps

Transfer a tested configuration to multiple identical pumps:

```python
import asyncio
from alpha_hwr import AlphaHWRClient


async def deploy_config_to_pumps():
    pump_addresses = ["PUMP-UUID-1", "PUMP-UUID-2", "PUMP-UUID-3"]

    for address in pump_addresses:
        print(f"Deploying to {address}...")
        async with AlphaHWRClient(address) as client:
            await client.authenticate(fast_mode=True)

            # Skip device verification for deployment
            success = await client.config.restore(
                "standard_config.json", verify_device=False
            )

            if success:
                print(f"   {address} configured")
            else:
                print(f"   {address} failed")


asyncio.run(deploy_config_to_pumps())
```

## Safety Features

### Version Checking

The restore process verifies that the backup file format version is supported. If you try to restore an incompatible backup:

```
ERROR: Unsupported backup version: 2.0
```

### Device Serial Number Verification

By default, the restore process checks that the backup was created from the same pump:

```
ERROR: Device serial number mismatch
  Backup:    12345678
  Connected: 87654321
Pass verify_device=False to restore anyway
```

### Validation

All restored values are validated before being applied to the pump.

### Logging

All backup and restore operations are logged for troubleshooting:

```python
import logging

logging.basicConfig(level=logging.INFO)

# You'll see detailed logs like:
# INFO: Reading device information...
# INFO: Reading control mode...
# INFO: Reading schedule configuration...
# INFO: Configuration backed up successfully
```

## Troubleshooting

### "Backup failed"

Check:
- Pump is connected and authenticated
- You have write permissions to the output directory
- Disk space is available

### "Restore failed - version mismatch"

The backup file was created with a newer version of the library. Update alpha-hwr:

```bash
pip install --upgrade alpha-hwr
```

### "Device serial number mismatch"

You're trying to restore a backup from a different pump. Either:
- Use the correct backup file for this pump
- Call `ConfigurationService.restore(..., verify_device=False)` from Python if you intentionally want to transfer settings between pumps

### "Restore succeeded but pump didn't change"

Check the logs for skipped steps. Note that restore uses the unverified setters, so a step can report success while the pump clamped or ignored the value — confirm with `alpha-hwr control status`.

## Best Practices

1. **Backup before changes**: Always create a backup before modifying pump settings
2. **Label backups**: Use descriptive filenames with dates and descriptions
3. **Test restores**: Periodically test that your backups can be restored
4. **Store safely**: Keep backups in a safe location (e.g., version control, cloud storage)
5. **Document changes**: Add comments in commit messages when storing backups in git
6. **Verify after restore**: Check that the pump is operating correctly after restoration

## API Reference

For complete API documentation, see:
- [`ConfigurationService`](../api/services.md#configurationservice)
