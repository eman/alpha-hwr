# Services API

Services provide specialized interfaces for different aspects of pump communication. Each service is accessed as a property on the client instance.

## Service Overview

| Service | Property | Purpose |
|---------|----------|---------|
| TelemetryService | `client.telemetry` | Real-time sensor data and monitoring |
| ControlService | `client.control` | Pump control operations (start, stop, modes) |
| ScheduleService | `client.schedule` | Weekly schedule management (5 layers) |
| DeviceInfoService | `client.device_info` | Device identification and statistics |
| ConfigurationService | `client.config` | Backup and restore operations |
| TimeService | `client.clock` | Real-time clock management |
| HistoryService | `client.history` | Historical trend data (100 cycles) |
| EventLogService | `client.events` | Pump event history (20 entries) |

## TelemetryService

Read telemetry data from the pump, either as a single snapshot or as a continuous stream.

::: alpha_hwr.services.telemetry.TelemetryService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## ControlService

Control pump operations including starting, stopping, and setting control modes with automatic validation.

::: alpha_hwr.services.control.ControlService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## ScheduleService

Manage weekly operation schedules across 5 independent layers with full CRUD operations.

::: alpha_hwr.services.schedule.ScheduleService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## DeviceInfoService

Read device identification information, firmware versions, and cumulative statistics.

::: alpha_hwr.services.device_info.DeviceInfoService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## ConfigurationService

Backup and restore complete pump configurations to JSON files.

::: alpha_hwr.services.configuration.ConfigurationService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## TimeService

Read and synchronize the pump's real-time clock.

::: alpha_hwr.services.time.TimeService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## HistoryService

Access historical trend data for flow, head, temperature, and power over the last 100 cycles.

::: alpha_hwr.services.history.HistoryService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## EventLogService

Access the pump's event log containing the last 20 pump events with timestamps.

::: alpha_hwr.services.event_log.EventLogService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3
