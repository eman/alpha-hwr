# API Models

The `alpha_hwr.models` module contains the data structures used to represent the pump's state.

## TelemetryData

```python
from alpha_hwr.models import TelemetryData
```

A Pydantic model representing a snapshot of the pump's telemetry. This object is immutable (`frozen=True`).

### Fields

All fields are `Optional` (`float | None` or `int | None`) as data availability depends on the current telemetry stream.

| Field | Type | Description |
| :--- | :--- | :--- |
| `timestamp` | `datetime` | Time of reading (default: `datetime.now()`) |
| `flow_m3h` | `float` | Flow rate in $m^3/h$ |
| `head_m` | `float` | Head pressure in meters |
| `power_w` | `float` | Power consumption in Watts |
| `media_temperature_c` | `float` | Media (Water) temperature in Celsius |
| `pcb_temperature_c` | `float` | PCB electronics temperature in Celsius |
| `control_box_temperature_c` | `float` | Control box ambient temperature in Celsius |
| `voltage_ac_v` | `float` | Mains Input Voltage (AC) |
| `voltage_dc_v` | `float` | Internal Bus Voltage (DC) |
| `current_a` | `float` | Input Current in Amps |
| `speed_rpm` | `float` | Actual Motor Speed in RPM |
| `setpoint_rpm` | `float` | Target/Reference Speed in RPM |
| `status_code` | `int` | Raw status byte (Alarm code) |
| `control_mode` | `int` | Active Control Mode ID |

### Computed Properties

These properties provide automatic unit conversion for convenience.

| Property | Return Type | Calculation |
| :--- | :--- | :--- |
| `flow_gpm` | `float` | Converts `flow_m3h` to US GPM |
| `head_ft` | `float` | Converts `head_m` to Feet |
| `head_psi` | `float` | Converts `head_m` to PSI |
| `media_temperature_f` | `float` | Converts `media_temperature_c` to Fahrenheit |

### Methods

#### `formatted_string`

```python
@property
def formatted_string(self) -> str
```

Returns a human-readable summary of the key metrics.

**Example Output:**

```text
Q=1.205m³/h | H=3.50m | P=25.0W | T_media=45.5°C | N=2800rpm
```

## SetpointInfo

```python
from alpha_hwr.models import SetpointInfo
```

A Pydantic model representing the current setpoint configuration.

### Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `control_mode` | `int` | Active control mode ID |
| `operation_mode` | `int` | Current operation mode |
| `setpoint` | `float` | Raw setpoint value (units depend on control mode) |
| `min_setpoint` | `float \| None` | Minimum allowed setpoint (if available) |
| `max_setpoint` | `float \| None` | Maximum allowed setpoint (if available) |
| `unit` | `str \| None` | Unit of measurement |
| `is_remote` | `bool \| None` | `True` if remote control mode is enabled |
| `is_running` | `bool \| None` | `True` if the pump motor is started |
| `schedule_enabled` | `bool \| None` | `True` if internal schedule is active |

### Methods

#### `get_display_value`

```python
def get_display_value(self) -> tuple[float, str]
```

Returns the setpoint value with appropriate unit conversion based on control mode.

**Returns**: Tuple of `(converted_value, unit_string)`

**Unit Conversions:**

* **Pressure modes** (CONSTANT_PRESSURE, PROPORTIONAL_PRESSURE, AutoAdapt): Pascals  meters of water column
* **Flow modes** (CONSTANT_FLOW): m³/h (no conversion)
* **Speed modes** (CONSTANT_SPEED): RPM (no conversion)
* **Temperature modes**: °C (no conversion)

**Example:**

```python
setpoint = await client.read_current_setpoint(include_limits=True)
value, unit = setpoint.get_display_value()
print(f"{value:.2f} {unit}")  # "1.00 m" for pressure mode
if setpoint.min_setpoint and setpoint.max_setpoint:
    print(f"Valid range: {setpoint.min_setpoint:.2f} - {setpoint.max_setpoint:.2f} {unit}")
```

#### `get_limits_display`

```python
def get_limits_display(self) -> tuple[tuple[float, str], tuple[float, str]] | None
```

Get min/max setpoint limits with appropriate unit conversion.

**Returns**: Tuple of `((min_value, unit), (max_value, unit))`, or `None` if limits not available.

**Example:**

```python
setpoint = await client.read_current_setpoint(include_limits=True)
limits = setpoint.get_limits_display()
if limits:
    (min_val, min_unit), (max_val, max_unit) = limits
    print(f"Range: {min_val:.2f} - {max_val:.2f} {max_unit}")
```

## AlarmInfo

```python
from alpha_hwr.models import AlarmInfo
```

A Pydantic model representing current alarm and warning status.

### Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `alarm_code` | `int \| None` | Current alarm code (0 = no alarm) |
| `warning_code` | `int \| None` | Current warning code (0 = no warning) |
| `alarm_description` | `str \| None` | Human-readable alarm description |
| `warning_description` | `str \| None` | Human-readable warning description |

**Example:**

```python
alarms = await client.read_alarms()
if alarms and alarms.alarm_code and alarms.alarm_code != 0:
    print(f"ALARM {alarms.alarm_code}: {alarms.alarm_description}")
```

## DeviceInfo

```python
from alpha_hwr.models import DeviceInfo
```

A Pydantic model representing device identification information.

### Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `address` | `str \| None` | BLE device address |
| `name` | `str \| None` | BLE device name |
| `product_name` | `str \| None` | Full product name (e.g., "ALPHA HWR") |
| `product_family` | `int \| None` | Product family code (52 = ALPHA) |
| `product_type` | `int \| None` | Product type (7 = HWR) |
| `product_version` | `int \| None` | Product version number |
| `serial_number` | `str \| None` | Device serial number |
| `software_version` | `str \| None` | Primary firmware version |
| `hardware_version` | `str \| None` | Hardware board version |
| `ble_version` | `str \| None` | Bluetooth module firmware version |

**Example:**

```python
info = await client.read_device_info()
if info:
    if info.product_family == 52 and info.product_type == 7:
        print("Grundfos ALPHA HWR")
```

## Statistics

```python
from alpha_hwr.models import Statistics
```

A Pydantic model representing cumulative pump statistics.

### Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `operating_hours` | `float` | Total operating time in hours |
| `start_count` | `int` | Number of times the pump has been started |

**Example:**

```python
stats = await client.read_statistics()
if stats:
    print(f"Operating hours: {stats.operating_hours:.1f} h")
    print(f"Start count: {stats.start_count}")
```

## ScheduleEntry

```python
from alpha_hwr.models import ScheduleEntry
```

A Pydantic model representing a single schedule time window for pump operation.

### Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `day` | `str` | Day of week (Monday-Sunday) |
| `begin_hour` | `int` | Start hour (0-23) |
| `begin_minute` | `int` | Start minute (0-59) |
| `end_hour` | `int` | End hour (0-23) |
| `end_minute` | `int` | End minute (0-59) |
| `action` | `int` | Action code (0x02=run pump, default) |
| `layer` | `int` | Schedule layer (0-4, default 0) |
| `enabled` | `bool` | Whether this entry is active (default True) |

### Properties

| Property | Return Type | Description |
| :--- | :--- | :--- |
| `day_index` | `int` | Day index (0=Monday, 6=Sunday) |
| `begin_time` | `str` | Formatted begin time (HH:MM) |
| `end_time` | `str` | Formatted end time (HH:MM) |
| `begin_time_obj` | `datetime.time` | Begin time as time object |
| `end_time_obj` | `datetime.time` | End time as time object |

### Methods

#### `get_duration_minutes`

```python
def get_duration_minutes(self) -> int
```

Calculate entry duration in minutes, handling midnight crossing.

**Returns**: Duration in minutes

**Example:**

```python
entry = ScheduleEntry(day="Monday", begin_hour=22, begin_minute=0, end_hour=2, end_minute=0)
duration = entry.get_duration_minutes()  # 240 (4 hours, crosses midnight)
```

#### `crosses_midnight`

```python
def crosses_midnight(self) -> bool
```

Check if this schedule entry crosses midnight.

**Returns**: True if end time is before begin time

#### `overlaps_with`

```python
def overlaps_with(self, other: ScheduleEntry) -> bool
```

Check if this entry overlaps with another entry on the same day/layer.

**Args**:

* `other`: Another ScheduleEntry to compare with

**Returns**: True if the entries overlap in time

**Example:**

```python
entry1 = ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0)
entry2 = ScheduleEntry(day="Monday", begin_hour=7, begin_minute=0, end_hour=9, end_minute=0)
if entry1.overlaps_with(entry2):
    print("Schedules overlap!")
```

#### `is_valid_time_range`

```python
def is_valid_time_range(self) -> tuple[bool, str | None]
```

Validate that the time range is sensible.

**Returns**: Tuple of `(is_valid, error_message)`

#### `to_bytes`

```python
def to_bytes(self) -> bytes
```

Convert to 6-byte binary format for writing to pump.

**Returns**: 6-byte binary representation

#### `from_bytes`

```python
@classmethod
def from_bytes(cls, data: bytes, day: str, layer: int = 0) -> ScheduleEntry
```

Parse from 6-byte binary format.

**Args**:

* `data`: 6-byte binary data
* `day`: Day name for this entry
* `layer`: Schedule layer (0-4)

**Returns**: ScheduleEntry instance

#### `to_dict` / `from_dict`

```python
def to_dict(self) -> dict
@classmethod
def from_dict(cls, data: dict) -> ScheduleEntry
```

Convert to/from dictionary format for JSON serialization.

**Example:**

```python
entry = ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0)
d = entry.to_dict()
restored = ScheduleEntry.from_dict(d)
```

## Historical Data Models

### EventLogEntry

Represents a single event log entry from the pump.

| Field | Type | Description |
| :--- | :--- | :--- |
| `index` | int | Entry index (0 = newest) |
| `cycle_counter` | int | Pump cycle number |
| `timestamp` | datetime | Event timestamp (UTC) |
| `timestamp_iso` | str | ISO 8601 formatted timestamp |
| `mode_byte` | int | Mode byte value |
| `event_type_flag` | int | Event type identifier (1 or 2) |

### CycleTimestampMap

Represents the cycle timestamp map containing the last 10 cycle end times.

| Field | Type | Description |
| :--- | :--- | :--- |
| `count` | int | Number of timestamps |
| `timestamps` | list[str] | List of ISO format strings |
| `timestamps_unix` | list[int] | List of Unix timestamps |
