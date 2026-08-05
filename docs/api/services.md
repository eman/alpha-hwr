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
| TimeService | `client.time` | Real-time clock management |
| HistoryService | `client.history` | Historical trend data (100 cycles) |
| EventLogService | `client.event_log` | Pump event history (20 entries) |
| SingleEventService | `client.single_events` | One-off events and vacations |
| WriteOperationService | `client.writes` | The serialized, verified write path |

## TelemetryService

Read telemetry data from the pump, either as a single snapshot or as a continuous stream.

::: alpha_hwr.services.telemetry.TelemetryService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## ControlService

Control pump operations: run state, control mode and setpoints.

The verified setters (`set_enabled`, `set_mode_verified`, `set_setpoint`,
`set_temperature_range`, `set_cycle_times`) return a
[`WriteResult`](models.md) reporting what the pump actually stored. The
older `set_constant_*` setters return `bool` and do not read back — see
[Verified Writes](../guides/verified_writes.md).

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

## SingleEventService

One-off scheduled windows and vacations. See
[Run State and Schedules](../guides/run_state_and_schedules.md) — in
particular the local-Unix timestamp rule, which cannot be caught by
verification.

::: alpha_hwr.services.single_event.SingleEventService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

::: alpha_hwr.services.single_event.SingleEvent
    options:
      show_root_heading: true
      show_source: false
      heading_level: 3

::: alpha_hwr.services.single_event.to_pump_time
    options:
      show_root_heading: true
      show_source: false
      heading_level: 3

::: alpha_hwr.services.single_event.from_pump_time
    options:
      show_root_heading: true
      show_source: false
      heading_level: 3

## WriteOperationService

The single serialized path every verified write passes through. Callers
normally reach it through `client.control`'s verified setters rather than
directly. See [Verified Writes](../guides/verified_writes.md).

::: alpha_hwr.services.write_operation.WriteOperationService
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3

## Run state

Pure logic — no I/O — describing how the run flag and the schedule flag
combine, including the one combination that can never run.

::: alpha_hwr.services.run_state.RunState
    options:
      show_root_heading: true
      show_source: false
      heading_level: 3

::: alpha_hwr.services.run_state.run_state
    options:
      show_root_heading: true
      show_source: false
      heading_level: 3

::: alpha_hwr.services.run_state.is_stalled
    options:
      show_root_heading: true
      show_source: false
      heading_level: 3
