# Data Models

The `alpha_hwr.models` module contains Pydantic models representing the pump's state and configuration. All models are fully typed and validated.

## Telemetry Models

### TelemetryData

Real-time telemetry data from the pump including flow, pressure, power, temperature, and electrical measurements.

::: alpha_hwr.models.TelemetryData
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

## Control Models

### SetpointInfo

Current pump control configuration including mode, setpoint value, and operational limits.

::: alpha_hwr.models.SetpointInfo
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

### AlarmInfo

Current alarm and warning status with human-readable descriptions.

::: alpha_hwr.models.AlarmInfo
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

## Device Models

### DeviceInfo

Device identification information including serial number, firmware versions, and product details.

::: alpha_hwr.models.DeviceInfo
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

### Statistics

Cumulative pump statistics including operating hours and start count.

::: alpha_hwr.models.Statistics
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

## Schedule Models

### ScheduleEntry

A single schedule time window for pump operation. Supports 5 independent schedule layers.

::: alpha_hwr.models.ScheduleEntry
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

## Historical Data Models

### EventLogEntry

A single event log entry from the pump's event history.

::: alpha_hwr.models.EventLogEntry
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

### EventLogMetadata

Metadata for event log entries.

::: alpha_hwr.models.EventLogMetadata
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

### TrendDataPoint

A single data point in a trend series.

::: alpha_hwr.models.TrendDataPoint
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

### TrendDataSeries

A series of trend data points for a single parameter.

::: alpha_hwr.models.TrendDataSeries
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4

### TrendDataCollection

Collection of all trend data series (flow, head, temperature, power).

::: alpha_hwr.models.TrendDataCollection
    options:
      show_root_heading: false
      show_source: false
      heading_level: 4
