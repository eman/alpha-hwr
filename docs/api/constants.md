# API Constants

The `alpha_hwr.constants` module defines the static values, protocol constants, and enumerations used throughout the library.

```python
from alpha_hwr import constants
```

## Bluetooth UUIDs

Standard identifiers for the Grundfos BLE service.

| Constant | Value | Description |
| :--- | :--- | :--- |
| `GENI_SERVICE_UUID` | `0000fdd0-0000-1000-8000-00805f9b34fb` | Main Service UUID |
| `GENI_CHAR_UUID` | `859cffd1-036e-432a-aa28-1a0085b87ba9` | GENI Read/Write/Notify Characteristic |

## Protocol Constants

| Constant | Value | Description |
| :--- | :--- | :--- |
| `FRAME_START` | `0x27` | Start Byte for Requests |
| `RESPONSE_START` | `0x24` | Start Byte for Responses |
| `CLASS_10` | `0x0A` | ID for DataObject Class |

## ControlMode (Enum)

Defines the pump regulation mode.

| Member | ID | Description |
| :--- | :--- | :--- |
| `CONSTANT_PRESSURE` | 0 | Constant Pressure |
| `PROPORTIONAL_PRESSURE` | 1 | Proportional Pressure |
| `CONSTANT_SPEED` | 2 | Constant Speed (Fixed RPM) |
| `AUTO_ADAPT` | 5 | AutoAdapt (Generic) |
| `CONSTANT_TEMPERATURE` | 6 | Constant Media Temperature |
| `CONSTANT_FLOW` | 8 | Constant Flow Rate |
| `AUTO_ADAPT_RADIATOR` | 13 | AutoAdapt Radiator System |
| `AUTO_ADAPT_UNDERFLOOR` | 14 | AutoAdapt Underfloor Heating |
| `AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR` | 15 | AutoAdapt Combined System |
| `DHW_ON_OFF_CONTROL` | 25 | Domestic Hot Water |
| `TEMPERATURE_RANGE_CONTROL` | 27 | Temperature Range |
| `SYSTEM_AIR_VENTING` | 128 | Air Venting Sequence |

## OperationMode (Enum)

Defines the high-level operational state.

| Member | ID | Description |
| :--- | :--- | :--- |
| `AUTO` | 0 | Normal Automatic Operation |
| `STOP` | 1 | Stopped |
| `MIN` | 2 | Minimum Curve |
| `MAX` | 3 | Maximum Curve |
| `USER_DEFINED` | 4 | User Defined |
| `FORCED_START` | 5 | Forced Start |
| `HAND` | 7 | Hand / Manual Mode |

## Register (Enum)

Addresses for Legacy Class 3 Register Polling.

| Member | Address (Hex) | Description |
| :--- | :--- | :--- |
| `ELECTRICAL` | `0x570045` | Voltage, Current, Power, RPM |
| `EXTENDED_FLOW` | `0x5D0122` | Flow and Head |
| `TEMPERATURE_MULTI` | `0x5D012C` | Media, PCB, Control Box Temps |
| `STATUS` | `0x5E0004` | Alarm/Status Code |

## ERROR_CODES (Dictionary)

A lookup table mapping error codes to human-readable descriptions. Extracted from the GENI profile.

```python
from alpha_hwr.constants import ERROR_CODES

# Usage example
alarm_code = 160
description = ERROR_CODES.get(alarm_code, "Unknown Error")
print(f"Alarm {alarm_code}: {description}")
```

**Sample Error Codes:**

| Code | Description |
| :--- | :--- |
| 0 | OK |
| 1 | Leakage Current |
| 57 | Dry Run |
| 64 | Over Temperature |
| 160 | Unknown Error (Not in GENI Profile) |
| 207 | Water Leakage |
| 208 | Cavitation |

*Note: The complete dictionary contains 98+ error codes. See `constants.py` for the full list.*