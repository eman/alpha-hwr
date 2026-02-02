# Device Profiles & Configuration

The CLI supports saving and managing multiple device addresses so you don't have to remember MAC addresses or repeatedly scan for devices.

## Saving Device Addresses

### Quick Save During Scan

Discover and save a device in one command:

```bash
# Scan and save the first device found as "basement"
alpha-hwr device scan --save basement

# Or save as the default device
alpha-hwr device scan --save default
```

### Manual Save

If you already know the MAC address:

```bash
# Save a specific device
alpha-hwr device set AA:BB:CC:DD:EE:FF --name basement

# Set it as the default device
alpha-hwr device set AA:BB:CC:DD:EE:FF --name basement --default

# Save without a friendly name
alpha-hwr device set AA:BB:CC:DD:EE:FF
```

## Listing Saved Devices

View all saved devices and their configuration:

```bash
alpha-hwr device list
```

Output:
```
Saved Devices
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Name     ┃ Address           ┃ Default ┃ Saved At            ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ basement │ AA:BB:CC:DD:EE:FF │ ✓       │ 2026-02-01T19:01:24 │
│ kitchen  │ 11:22:33:44:55:66 │         │ 2026-02-01T19:01:45 │
└──────────┴───────────────────┴─────────┴─────────────────────┘
```

## Using Saved Devices

Once a device is saved as the default, you can omit the `--device` option:

```bash
# Uses the default device
alpha-hwr monitor live

# Override with a specific device
alpha-hwr monitor live --device 11:22:33:44:55:66
```

## Configuration Storage

Device profiles are stored in your system's XDG config directory:

```
~/.config/alpha-hwr/config.json
```

Example configuration file:

```json
{
  "default_device": "AA:BB:CC:DD:EE:FF",
  "devices": {
    "basement": {
      "address": "AA:BB:CC:DD:EE:FF",
      "saved_at": "2026-02-01T19:01:24.447024"
    },
    "kitchen": {
      "address": "11:22:33:44:55:66",
      "saved_at": "2026-02-01T19:01:45.436923"
    }
  },
  "last_used": "11:22:33:44:55:66",
  "version": "1.0",
  "last_used_at": "2026-02-01T19:01:45.436973"
}
```

## Priority Order

When you run a command, the device address is resolved in this order:

1. **Explicit `--device` option** (if provided)
2. **Default device** (from config file)
3. **Environment variable** `ALPHA_HWR_DEVICE_ADDRESS`
4. **Error** (if none specified)

Example:

```bash
# Uses device specified in config as default
alpha-hwr device info

# Overrides default with CLI option
alpha-hwr device info --device 11:22:33:44:55:66

# Or use environment variable
ALPHA_HWR_DEVICE_ADDRESS=11:22:33:44:55:66 alpha-hwr device info
```

## Getting Started with Profiles

### First Time Setup

1. Scan for your pump:
   ```bash
   alpha-hwr device scan
   ```

2. Save it with a friendly name:
   ```bash
   alpha-hwr device set AA:BB:CC:DD:EE:FF --name my-pump --default
   ```

3. Verify it's saved:
   ```bash
   alpha-hwr device list
   ```

4. Now you can use commands without specifying the device:
   ```bash
   alpha-hwr monitor live
   alpha-hwr device info
   alpha-hwr control status
   ```

### Multiple Pumps

If you have multiple pumps, save each with a different name:

```bash
alpha-hwr device set AA:BB:CC:DD:EE:FF --name basement
alpha-hwr device set 11:22:33:44:55:66 --name kitchen
alpha-hwr device set 22:33:44:55:66:77 --name garage --default
```

Then use them:

```bash
# Use default
alpha-hwr monitor live

# Use specific pump
alpha-hwr monitor live --device AA:BB:CC:DD:EE:FF
```

## Troubleshooting

### No Device Configured

If you see this error:

```
Error: No device address configured.
Use 'alpha-hwr device scan' to find devices, then save with 'alpha-hwr device set <mac>'
```

Save a device first:

```bash
alpha-hwr device scan --save my-pump
```

### Clearing Configuration

To start fresh, delete the config file:

```bash
rm ~/.config/alpha-hwr/config.json
```

The next time you run a command, it will ask you to configure a device.
