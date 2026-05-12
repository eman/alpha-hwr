# Command Line Interface (CLI) Guide

The `alpha-hwr` command-line tool for interacting with Grundfos ALPHA HWR pumps. Built on Typer and Rich.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Basic Usage](#basic-usage)
- [Monitoring Commands](#monitoring-commands)
- [History and Events](#history-and-events)
- [Control Commands](#control-commands)
- [Device Information](#device-information)
- [Clock Management](#clock-management)
- [Schedule Management](#schedule-management)
- [Configuration Backup & Restore](#configuration-backup-restore)
- [Output Formats](#output-formats)
- [Troubleshooting](#troubleshooting)

---

## Installation

The CLI is automatically installed with the alpha-hwr package:

```bash
pip install alpha-hwr
```

Verify installation:

```bash
alpha-hwr --version
```

Get help:

```bash
alpha-hwr --help
```

---

## Configuration

### Device Address

The CLI needs your pump's Bluetooth address. You can provide it in two ways:

**1. Command-line option (recommended for scripts):**

```bash
alpha-hwr monitor live --device "YOUR-DEVICE-ADDRESS"
```

**2. Configuration file (recommended for interactive use):**

Create `~/.config/alpha-hwr/config.json`:

```json
{
  "device_address": "YOUR-DEVICE-ADDRESS"
}
```

**Address Format:**

- **macOS**: UUID format (e.g., `A1B2C3D4-E5F6-7890-1234-567890ABCDEF`)
- **Linux/Windows**: MAC address (e.g., `00:11:22:33:44:55`)

### Finding Your Pump's Address

Use a BLE scanner app (nRF Connect, LightBlue) or run this Python snippet:

```bash
python -c "
import asyncio
from bleak import BleakScanner

async def scan():
    devices = await BleakScanner.discover(timeout=10.0)
    for d in devices:
        if d.name and 'ALPHA' in d.name:
            print(f'{d.address} - {d.name}')

asyncio.run(scan())
"
```

---

## Basic Usage

All commands follow this pattern:

```bash
alpha-hwr [GROUP] [COMMAND] [OPTIONS]
```

**Command Groups:**

- `monitor` - Real-time telemetry monitoring
- `history` - Historical trends and timestamps
- `events` - Event log access
- `control` - Pump control operations
- `device` - Device information and statistics
- `clock` - Real-time clock management
- `schedule` - Schedule management
- `config` - Configuration backup/restore

**Global Options:**

- `--device/-d ADDRESS` - Device address (overrides config file)
- `--help` - Show help message
- `--version` - Show version

**Get help for any command:**

```bash
alpha-hwr monitor --help
alpha-hwr control start --help
```

---

## Monitoring Commands

### Live Monitoring

Continuously display real-time telemetry data:

```bash
# Default: table format, 1-second updates
alpha-hwr monitor live

# Custom update interval
alpha-hwr monitor live --interval 2.0

# JSON output (for automation)
alpha-hwr monitor live --format json

# Specify device explicitly
alpha-hwr monitor live --device "AA:BB:CC:DD:EE:FF"
```

**Example Output (Table)**:

```
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Metric         ┃ Value    ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Flow Rate      │ 2.5 m³/h │
│ Head Pressure  │ 1.5 m    │
│ Power          │ 50.0 W   │
│ Speed          │ 2500 RPM │
│ Water Temp     │ 45.5 °C  │
│ Electronics    │ 35.2 °C  │
│ Status         │ Running  │
└────────────────┴──────────┘
```

**Press Ctrl+C to stop monitoring.**

### Single Snapshot

Take a one-time telemetry reading:

```bash
# Table format (default)
alpha-hwr monitor snapshot

# JSON format
alpha-hwr monitor snapshot --format json
```

**Example JSON Output**:

```json
{
  "timestamp": "2026-01-30T12:00:00Z",
  "flow_m3h": 2.5,
  "head_m": 1.5,
  "power_w": 50.0,
  "speed_rpm": 2500,
  "media_temp_c": 45.5,
  "pcb_temp_c": 35.2,
  "running": true
}
```

## History and Events

### Historical Trends

View historical trend data for flow, head, temperature, and power-on time:

```bash
# Show last 10 cycles (high resolution)
alpha-hwr history trends

# Show last 100 cycles (full history)
alpha-hwr history trends --detailed
```

### Event Log

View the pump's event log (last 20 entries):

```bash
# List all events
alpha-hwr events list

# Show specific entry details
alpha-hwr events show 0

# Show event metadata
alpha-hwr events metadata
```

### Cycle Timestamps

View timestamps for recent pump cycles:

```bash
# Show last 10 cycle timestamps
alpha-hwr history timestamps

# Show last 100 cycle timestamps
alpha-hwr history timestamps --count 100
```

---

## Control Commands

### Start and Stop

```bash
# Start with specific mode
alpha-hwr control start --mode constant_pressure

# Stop the pump
alpha-hwr control stop
```

### Remote Control Mode

By default, the pump operates in "Auto" mode where both the physical panel and Bluetooth commands are accepted. You can use Remote Mode to prioritize digital control:

```bash
# Prioritize Bluetooth commands and lock physical panel
alpha-hwr control enable-remote

# Return to normal operation (physical panel enabled)
alpha-hwr control disable-remote
```

**Note**: Use Remote Mode when you want to ensure your automation logic isn't overridden by someone pressing buttons on the pump.

### Set Control Mode

The pump supports multiple control modes specifically optimized for hot water recirculation.

#### Temperature Control

Maintains temperature within a specified range (Mode 27):

```bash
# Set range 35-39°C with AUTOADAPT enabled (default)
alpha-hwr control set-temperature --min 35 --max 39

# Set custom range with no autoadapt and a flow limit
alpha-hwr control set-temperature --min 40 --max 45 --no-autoadapt --flow-limit 1.5
```

#### Cycle Time Control

Operates the pump in on/off cycles (Mode 25):

```bash
# Set 5 minutes ON, 15 minutes OFF
alpha-hwr control set-cycle-time --on 5 --off 15

# View current cycle times
alpha-hwr control get-cycle-time
```

#### Constant Speed

Runs at fixed RPM (Mode 2):

```bash
# Set to 2500 RPM with 2.3 GPM flow limit
alpha-hwr control set-speed 2500 --flow-limit 2.3
```

#### Constant Pressure

Maintains fixed head pressure (Mode 0):

```bash
# Set to 1.5 meters head
alpha-hwr control set-pressure 1.5
```

#### Constant Flow

Maintains specific flow rate (Mode 8):

```bash
# Set to 0.5 m³/h
alpha-hwr control set-flow 0.5
```

#### Proportional Pressure

Adjusts pressure based on flow rate (Mode 1):

```bash
# Set proportional pressure with 1.2m base
alpha-hwr control set-proportional 1.2
```

#### Flow Limitation

Set a global maximum flow limit to prevent corrosion:

```bash
# Set 1.5 GPM limit (recommended for 1/2" pipe)
alpha-hwr control set-flow-limit 1.5
```

---

## Device Information

### Scan for Pumps

Scan for nearby ALPHA HWR pumps advertising on BLE:

```bash
# Default: 10-second scan
alpha-hwr device scan

# Custom timeout
alpha-hwr device scan --timeout 5.0
```

### Basic Information

Display pump identification and firmware details:

```bash
# Table format (default)
alpha-hwr device info

# JSON format
alpha-hwr device info --format json
```

**Example Output**:

```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Field              ┃ Value                ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ Product Name       │ ALPHA HWR            │
│ Product Family     │ ALPHA (52)           │
│ Product Type       │ HWR (7)              │
│ Serial Number      │ 12345678             │
│ Software Version   │ 2.34.0               │
│ Hardware Version   │ 1.5.2                │
│ BLE Version        │ 1.2.3                │
└────────────────────┴──────────────────────┘
```

### Device Statistics

View cumulative operating statistics:

```bash
# Show operating hours and start count
alpha-hwr device stats

# JSON format
alpha-hwr device stats --format json
```

**Example Output**:

```
Operating Time: 1,234 hours
Start Count: 5,678 starts
Average Runtime: 13 minutes per cycle
```

### Active Alarms

Check for active alarms and warnings:

```bash
# Show current alarms
alpha-hwr device alarms

# JSON format for automation
alpha-hwr device alarms --format json
```

---

## Clock Management

### View Clock

Check the pump's internal real-time clock (RTC) and compare it with system time:

```bash
alpha-hwr clock view
```

### Synchronize Clock

Synchronize the pump's clock with your computer's time:

```bash
alpha-hwr clock sync
```

**Note**: Correct clock time is essential for accurate scheduling and event logging.

---

## Schedule Management

The pump supports weekly schedules across 5 independent layers (0-4).

### View Schedule

Display current schedule configuration:

```bash
# Show all schedule layers
alpha-hwr schedule show

# Show specific layer
alpha-hwr schedule show --layer 0

# JSON format
alpha-hwr schedule show --format json
```

**Example Output**:

```
Schedule Status: Enabled

Layer 0:
  Monday:    06:00 - 08:00 (Enabled)
  Tuesday:   06:00 - 08:00 (Enabled)
  Wednesday: 06:00 - 08:00 (Enabled)
  Thursday:  06:00 - 08:00 (Enabled)
  Friday:    06:00 - 08:00 (Enabled)
  Saturday:  (Disabled)
  Sunday:    (Disabled)

Layer 1:
  Monday:    18:00 - 22:00 (Enabled)
  Tuesday:   18:00 - 22:00 (Enabled)
  ...
```

### Enable/Disable Schedule

```bash
# Enable the schedule globally
alpha-hwr schedule enable

# Disable the schedule globally
alpha-hwr schedule disable
```

### Set Schedule Entry

Add or modify a schedule entry:

```bash
# Set Monday 06:00-08:00 on Layer 0
alpha-hwr schedule set-entry \
  --day monday \
  --start 06:00 \
  --end 08:00 \
  --layer 0

# Set multiple days with weekday shorthand
alpha-hwr schedule set-entry \
  --days mon,tue,wed,thu,fri \
  --start 06:00 \
  --end 08:00 \
  --layer 0
```

### Clear Schedule

Remove schedule entries:

```bash
# Clear specific layer
alpha-hwr schedule clear --layer 0

# Clear all layers
alpha-hwr schedule clear --all
```

### Import/Export Schedule

```bash
# Export current schedule to JSON
alpha-hwr schedule export my_schedule.json

# Import schedule from JSON
alpha-hwr schedule import my_schedule.json
```

**Schedule JSON Format**:

```json
{
  "enabled": true,
  "layers": [
    {
      "layer": 0,
      "entries": [
        {
          "day": "Monday",
          "enabled": true,
          "start_hour": 6,
          "start_minute": 0,
          "end_hour": 8,
          "end_minute": 0
        }
      ]
    }
  ]
}
```

---

## Configuration Backup & Restore

### Backup Configuration

Save current pump configuration to a file:

```bash
# Backup to default location (~/.config/alpha-hwr/backup.json)
alpha-hwr config backup

# Backup to specific file
alpha-hwr config backup --output my_backup.json

# Include schedule in backup
alpha-hwr config backup --include-schedule

# Compact JSON format
alpha-hwr config backup --compact
```

**What's backed up:**
- Control mode and setpoint
- Device settings
- Optionally: weekly schedule (all layers)

### Restore Configuration

Restore configuration from a backup file:

```bash
# Restore from default backup
alpha-hwr config restore

# Restore from specific file
alpha-hwr config restore --input my_backup.json

# Dry run (show what would be restored without applying)
alpha-hwr config restore --dry-run

# Restore only specific components
alpha-hwr config restore --mode-only
alpha-hwr config restore --schedule-only
```

### List Backups

Show available backup files:

```bash
# List backups in default directory
alpha-hwr config list-backups

# Show backup details
alpha-hwr config list-backups --details
```

---

## Output Formats

Most commands support multiple output formats:

### Table Format (Default)

Beautiful formatted tables with Rich:

```bash
alpha-hwr monitor snapshot
alpha-hwr device info
alpha-hwr schedule show
```

### JSON Format

Machine-readable output for scripts:

```bash
alpha-hwr monitor snapshot --format json
alpha-hwr device info --format json
alpha-hwr schedule show --format json
```

**Use cases:**
- Automation scripts
- Integration with other tools
- Data logging and analysis

**Example: Log telemetry to file**

```bash
while true; do
  alpha-hwr monitor snapshot --format json >> telemetry.log
  sleep 60
done
```

---

## Troubleshooting

### Connection Issues

**Symptom**: `Failed to connect to device`

**Solutions:**

1. **Verify device address:**
   ```bash
   # Scan for devices
   python -m alpha_hwr.utils.scan
   ```

2. **Check Bluetooth is enabled:**
   - macOS: System Preferences → Bluetooth
   - Linux: `sudo systemctl status bluetooth`
   - Windows: Settings → Bluetooth

3. **Disconnect from other apps:**
   - Ensure no other applications are connected to the pump
   - Disconnect from other BLE connections

4. **Increase connection timeout:**
   ```bash
   alpha-hwr monitor live --timeout 30
   ```

### Authentication Failed

**Symptom**: `Authentication failed`

**Solutions:**

1. **Restart pump:** Power cycle the pump
2. **Reset BLE:** Restart Bluetooth adapter
3. **Clear pairing:** Re-pair the device

### Command Not Found

**Symptom**: `alpha-hwr: command not found`

**Solutions:**

1. **Verify installation:**
   ```bash
   pip show alpha-hwr
   ```

2. **Check PATH:**
   ```bash
   echo $PATH
   ```

3. **Reinstall:**
   ```bash
   pip uninstall alpha-hwr
   pip install alpha-hwr
   ```

### No Telemetry Data

**Symptom**: Telemetry shows all zeros or times out

**Solutions:**

1. **Check pump is running:** Pump must be started
2. **Wait after start:** Allow 2-3 seconds for telemetry to stabilize
3. **Verify authentication:** Ensure authentication succeeded

---

## Advanced Usage

### Scripting Examples

**Log telemetry every minute:**

```bash
#!/bin/bash
while true; do
    timestamp=$(date -Iseconds)
    telemetry=$(alpha-hwr monitor snapshot --format json)
    echo "$timestamp $telemetry" >> pump_log.jsonl
    sleep 60
done
```

**Set mode based on time of day:**

```bash
#!/bin/bash
hour=$(date +%H)

if [ $hour -ge 6 ] && [ $hour -lt 9 ]; then
    # Morning: high pressure
    alpha-hwr control set-mode constant-pressure --setpoint 3.0
elif [ $hour -ge 18 ] && [ $hour -lt 22 ]; then
    # Evening: medium pressure
    alpha-hwr control set-mode constant-pressure --setpoint 2.0
else
    # Off hours: stop
    alpha-hwr control stop
fi
```

**Monitor and alert on low flow:**

```bash
#!/bin/bash
while true; do
    flow=$(alpha-hwr monitor snapshot --format json | jq -r '.flow_m3h')
    if (( $(echo "$flow < 0.5" | bc -l) )); then
        echo "ALERT: Low flow detected: $flow m³/h"
        # Send notification (e.g., via email, SMS, webhook)
    fi
    sleep 10
done
```

### Environment Variables

Configure via environment variables:

```bash
# Set device address
export ALPHA_HWR_DEVICE_ADDRESS="AA:BB:CC:DD:EE:FF"

# Set Bluetooth adapter (Linux)
export ALPHA_HWR_ADAPTER="hci0"

# Enable debug logging
export ALPHA_HWR_DEBUG=1

# Now use CLI without --device flag
alpha-hwr monitor live
```

---

## Command Reference

### Monitor Commands

| Command | Description |
|---------|-------------|
| `monitor live` | Continuous real-time monitoring |
| `monitor snapshot` | Single telemetry reading |

### History Commands

| Command | Description |
|---------|-------------|
| `history trends` | Show historical trend data |
| `history timestamps` | Show cycle timestamps |

### Event Commands

| Command | Description |
|---------|-------------|
| `events list` | List event log entries |
| `events show` | Show entry details |
| `events metadata` | Show event log metadata |

### Control Commands

| Command | Description |
|---------|-------------|
| `control start` | Start pump |
| `control stop` | Stop pump |
| `control set-temperature` | Set temperature range control (Mode 27) |
| `control set-cycle-time` | Set DHW cycle time control (Mode 25) |
| `control get-cycle-time` | Get DHW cycle time configuration |
| `control set-pressure` | Set constant pressure mode (Mode 0) |
| `control set-speed` | Set constant speed mode (Mode 2) |
| `control set-flow` | Set constant flow mode (Mode 8) |
| `control set-proportional` | Set proportional pressure mode (Mode 1) |
| `control set-flow-limit` | Set maximum flow limit (GPM) |
| `control set-mode <mode>` | Set control mode with setpoint (generic) |

### Device Commands

| Command | Description |
|---------|-------------|
| `device scan` | Scan for nearby pumps |
| `device info` | Show device information |
| `device stats` | Show operating statistics |
| `device alarms` | Show active alarms |

### Clock Commands

| Command | Description |
|---------|-------------|
| `clock view` | View pump clock |
| `clock sync` | Sync pump clock with system |

### Schedule Commands

| Command | Description |
|---------|-------------|
| `schedule show` | Display current schedule |
| `schedule enable` | Enable schedule globally |
| `schedule disable` | Disable schedule globally |
| `schedule set-entry` | Add/modify schedule entry |
| `schedule clear` | Clear schedule entries |
| `schedule export` | Export schedule to JSON |
| `schedule import` | Import schedule from JSON |

### Config Commands

| Command | Description |
|---------|-------------|
| `config backup` | Backup pump configuration |
| `config restore` | Restore from backup |
| `config list-backups` | List available backups |

---

## Getting Help

For command-specific help, use `--help`:

```bash
alpha-hwr --help
alpha-hwr monitor --help
alpha-hwr control set-mode --help
alpha-hwr schedule set-entry --help
```

For issues or questions:
- GitHub Issues: https://github.com/eman/alpha-hwr
- Documentation: See `docs/` directory
- Protocol Reference: See `docs/protocol/`
