# Data Models & Enums

This section details the data structures and enumerations used in the `alpha-hwr` library.

## TelemetryData

The `TelemetryData` class represents a snapshot of the pump's operational state.

### Properties

| Property | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `datetime` | - | Time when the data was received. |
| `flow_m3h` | `float` | $m^3/h$ | Flow rate. |
| `head_m` | `float` | Meters | Head / Differential Pressure. |
| `power_w` | `float` | Watts | Electrical power consumption. |
| `media_temperature_c` | `float` | °C | Temperature of the pumped liquid. |
| `pcb_temperature_c` | `float` | °C | Internal electronics temperature. |
| `control_box_temperature_c` | `float` | °C | Ambient/Box temperature. |
| `voltage_ac_v` | `float` | Volts | Mains input voltage. |
| `voltage_dc_v` | `float` | Volts | Internal DC bus voltage. |
| `current_a` | `float` | Amps | Input current. |
| `speed_rpm` | `float` | RPM | Motor rotational speed. |
| `setpoint_rpm` | `float` | RPM | Target speed (if available). |
| `status_code` | `int` | - | Raw status byte. |
| `control_mode` | `int` | - | Active Control Mode ID. |

### Helper Properties (Conversions)

| Property | Unit | Calculation |
| :--- | :--- | :--- |
| `flow_gpm` | GPM | `flow_m3h / 0.2271` |
| `head_ft` | Feet | `head_m / 0.3048` |
| `head_psi` | PSI | `head_m / 0.70329` |
| `media_temperature_f` | °F | `(media_temperature_c * 1.8) + 32` |

## ControlMode Enum

The `ControlMode` integer enum defines the regulation behavior of the pump.

| ID | Name | Description |
| :--- | :--- | :--- |
| `0` | `CONSTANT_PRESSURE` | Maintains constant head regardless of flow. |
| `1` | `PROPORTIONAL_PRESSURE` | Adjusts head proportional to flow. |
| `2` | `CONSTANT_SPEED` | Runs at a fixed RPM (Manual/Fixed). |
| `5` | `AUTO_ADAPT` | Intelligent self-learning mode (generic). |
| `6` | `CONSTANT_TEMPERATURE` | Maintains constant media temperature. |
| `8` | `CONSTANT_FLOW` | Maintains constant flow rate. |
| `13` | `AUTO_ADAPT_RADIATOR` | AutoAdapt optimized for radiator systems. |
| `14` | `AUTO_ADAPT_UNDERFLOOR` | AutoAdapt optimized for underfloor heating. |
| `15` | `AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR` | AutoAdapt for combined systems. |
| `25` | `DHW_ON_OFF_CONTROL` | Domestic Hot Water specific mode. |
| `27` | `TEMPERATURE_RANGE_CONTROL` | Keeps temperature within a specific band. |

## OperationMode Enum

Defines the high-level state of the device (Stop, Run, Max, etc.).

| ID | Name | Description |
| :--- | :--- | :--- |
| `0` | `AUTO` | Normal running operation. |
| `1` | `STOP` | Pump stopped (Standby). |
| `2` | `MIN` | Forced Minimum Curve. |
| `3` | `MAX` | Forced Maximum Curve. |
| `5` | `FORCED_START` | Override start. |
| `7` | `HAND` | Manual Hand mode. |

## Unit Conversion Factors

The library uses the following standard factors for internal conversions:

| From | To | Factor |
| :--- | :--- | :--- |
| $m^3/h$ | GPM (US) | `/ 0.22712470704` |
| Meters | Feet | `/ 0.3048` |
| Meters | PSI | `/ 0.70329` |
| Celsius | Fahrenheit | `(C * 9/5) + 32` |
| Pascals | Meters (Water Column) | `/ 9806.65` |

## SetpointInfo Model

The `SetpointInfo` class represents the current setpoint configuration with optional factory limits.

### Properties

| Property | Type | Description |
| :--- | :--- | :--- |
| `control_mode` | `int` | Active control mode ID |
| `operation_mode` | `int` | Current operation mode |
| `setpoint` | `float` | Raw setpoint value (units depend on mode) |
| `min_setpoint` | `float \| None` | Factory-configured minimum (converted to display units) |
| `max_setpoint` | `float \| None` | Factory-configured maximum (converted to display units) |
| `unit` | `str \| None` | Unit of measurement for display |

### Methods

#### `get_display_value() -> tuple[float, str]`

Returns the setpoint with appropriate unit conversion.

*   **Pressure modes**: Converts Pascals  meters
*   **Speed modes**: Returns RPM directly
*   **Flow modes**: Returns m³/h directly

#### `get_limits_display() -> str | None`

Returns a formatted string like `"1.00 - 2.45 m"` showing the valid setpoint range.

## Statistics Model

The `Statistics` class represents cumulative pump operational data.

### Properties

| Property | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `operating_hours` | `float` | Hours | Total time the pump has been running |
| `start_count` | `int` | - | Number of times the pump motor has started |

**Example Usage:**
```python
stats = await client.read_statistics()
print(f"Pump has run for {stats.operating_hours:.1f} hours")
print(f"Pump has been started {stats.start_count} times")

# Calculate average runtime per start
if stats.start_count > 0:
    avg_runtime = stats.operating_hours / stats.start_count
    print(f"Average runtime per start: {avg_runtime * 60:.1f} minutes")
```

## AlarmInfo Model

The `AlarmInfo` class represents the current alarm and warning status with human-readable descriptions.

### Properties

| Property | Type | Description |
| :--- | :--- | :--- |
| `alarm_code` | `int \| None` | Current alarm code (0 = no alarm) |
| `warning_code` | `int \| None` | Current warning code (0 = no warning) |
| `alarm_description` | `str \| None` | Human-readable alarm description from ERROR_CODES |
| `warning_description` | `str \| None` | Human-readable warning description from ERROR_CODES |

**Example:**
```python
alarms = await client.read_alarms()
if alarms:
    if alarms.alarm_code and alarms.alarm_code != 0:
        print(f"ALARM {alarms.alarm_code}: {alarms.alarm_description}")
    if alarms.warning_code and alarms.warning_code != 0:
        print(f"WARNING {alarms.warning_code}: {alarms.warning_description}")
```

## ScheduleEntry Model

The `ScheduleEntry` class represents a single schedule time window with comprehensive validation.

### Properties

| Property | Type | Description |
| :--- | :--- | :--- |
| `day` | `str` | Day of week (Monday-Sunday) |
| `begin_hour` | `int` | Start hour (0-23) |
| `begin_minute` | `int` | Start minute (0-59) |
| `end_hour` | `int` | End hour (0-23) |
| `end_minute` | `int` | End minute (0-59) |
| `action` | `int` | Action code (0x02=run, default) |
| `layer` | `int` | Schedule layer (0-4, default 0) |
| `enabled` | `bool` | Whether entry is active (default True) |

### Computed Properties

| Property | Type | Description |
| :--- | :--- | :--- |
| `day_index` | `int` | Day index (0=Monday, 6=Sunday) |
| `begin_time` | `str` | Formatted begin time (HH:MM) |
| `end_time` | `str` | Formatted end time (HH:MM) |
| `begin_time_obj` | `datetime.time` | Begin time as time object |
| `end_time_obj` | `datetime.time` | End time as time object |

### Key Methods

#### Duration and Validation

*   `get_duration_minutes() -> int` - Calculate duration in minutes (handles midnight crossing)
*   `crosses_midnight() -> bool` - Check if schedule crosses midnight
*   `is_valid_time_range() -> tuple[bool, str | None]` - Validate time range
*   `overlaps_with(other) -> bool` - Check for overlap with another entry

#### Serialization

*   `to_bytes() -> bytes` - Convert to 6-byte binary format for pump
*   `from_bytes(data, day, layer) -> ScheduleEntry` - Parse from binary
*   `to_dict() -> dict` - Convert to dictionary
*   `from_dict(data) -> ScheduleEntry` - Create from dictionary

**Example Usage:**
```python
from alpha_hwr import ScheduleEntry

# Create a schedule entry
entry = ScheduleEntry(
    day="Monday",
    begin_hour=6,
    begin_minute=0,
    end_hour=8,
    end_minute=0,
)

# Check properties
print(f"Time: {entry.begin_time} - {entry.end_time}")
print(f"Duration: {entry.get_duration_minutes()} minutes")
print(f"Day index: {entry.day_index}")

# Check for overlaps
other = ScheduleEntry(day="Monday", begin_hour=7, begin_minute=0, end_hour=9, end_minute=0)
if entry.overlaps_with(other):
    print("These schedules overlap!")

# Midnight-crossing example
night = ScheduleEntry(day="Monday", begin_hour=22, begin_minute=0, end_hour=2, end_minute=0)
print(f"Crosses midnight: {night.crosses_midnight()}")
print(f"Duration: {night.get_duration_minutes()} minutes")  # 240 minutes

# Serialization
data = entry.to_bytes()  # 6-byte binary
restored = ScheduleEntry.from_bytes(data, day="Monday")

# Dictionary format
d = entry.to_dict()
restored = ScheduleEntry.from_dict(d)
```