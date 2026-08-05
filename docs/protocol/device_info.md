# Device Information

The Grundfos ALPHA HWR provides limited device identification information.

## BLE Advertisement Data

The pump broadcasts device info in its BLE advertisement service data.

### Service UUID

`0000fdd0-0000-1000-8000-00805f9b34fb` (GENI service)

### Service Data Format

```text
[flags...][product_family][product_type][product_version][...]
```

**Fields:**

- **Byte 3:** Product Family (52 = ALPHA)
- **Byte 4:** Product Type (7 = HWR)
- **Byte 5:** Product Version (firmware-dependent)

## Class 7 String Reading -  SUPPORTED

The ALPHA HWR (Family 52, Type 7) supports reading detailed device identification via **Class 7 ReadString** operations.

### Supported Parameters

The following string parameters can be read when the device is connected and authenticated:

- **ID 1**: Product Name (e.g., `LPHA HWR`, cleaned up to `ALPHA HWR`)
- **ID 9**: Serial Number Suffix (e.g., `0000479`)
- **ID 50**: Software Version String (e.g., `2601618V04.02.01.02539`)
- **ID 52**: Hardware Version (reported as Backend SW, e.g., `2601617V01.03.00.00469`)
- **ID 58**: BLE Version (e.g., `2811431V06.00.01.00001`)

### Response Behavior

The pump returns the string encoded as UTF-8 (or ASCII), typically null-terminated and padded with trailing nulls.

**Note on Serial Number:** The full serial number is formed by prepending a "1" to the suffix from ID 9 (e.g., `1` + `0000479` = `10000479`).

```text
Request:  2707e7f8070109...  (Read String ID 9)
Response: 240ef8e70701093030303034373900... (Suffix: "0000479")
```

### Authentication Requirement

Class 7 reading requires the device to be **Authenticated** via the handshake sequence (Legacy Magic + Class 10 Magic + Auth Extend). If the device is not authenticated, Class 7 requests may return empty payloads or fail.

## Available Information

1.  **Product Identification** (BLE Advertisement):
    - Broad scan for ALPHA HWR pumps.
    - Match by Service UUID `0000fdd0-0000-1000-8000-00805f9b34fb` or Grundfos Company ID `0000fe5d-0000-1000-8000-00805f9b34fb` in service data.
    - Extract Family (Byte 3), Type (Byte 4), and Version (Byte 5) from service data.


### Via Class 7 Strings (Detailed Info)

Detailed information, including serial numbers and firmware versions, is available via **Class 7 ReadString** operations. This requires an active, authenticated connection.

```python
# Full device info - connects and reads Class 7 strings
device_info = await client.device_info.read_info(connect=True)
if device_info:
    print(f"Serial Number: {device_info.serial_number}")
    print(f"SW Version: {device_info.software_version}")
    print(f"HW Version: {device_info.hardware_version}")
    print(f"BLE Version: {device_info.ble_version}")
```

## Implementation

### Python API

```python
from alpha_hwr import AlphaHWRClient

async with AlphaHWRClient(address) as client:
    # Get full device info (connects if necessary)
    device_info = await client.device_info.read_info(connect=True)
    
    if device_info:
        print(f"Serial: {device_info.serial_number}")
        print(f"Software: {device_info.software_version}")
        print(f"Hardware: {device_info.hardware_version}")
    else:
        print("Device info not available")
```

### CLI

```bash
# Read detailed info from a connected device
alpha-hwr info
```

## Capabilities Summary

-  **Serial number**: Available via Class 7 (ID 9)
-  **Software version**: Available via Class 7 (ID 50)
-  **Hardware version**: Available via Class 7 (ID 52)
-  **BLE version**: Available via Class 7 (ID 58)
-  **Product family/type/version**: Available via BLE advertisement or Class 2 registers

## Related

- **Class 2 Registers:** See `docs/protocol/telemetry.md`
- **Authentication Handshake:** Required for Class 7 string reading (see `docs/protocol/connection.md`)
