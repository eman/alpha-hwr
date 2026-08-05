"""
Services layer for Alpha HWR pump operations.

This package contains high-level business logic services that coordinate
protocol operations and provide clean APIs for pump interaction.

Services:
- telemetry: Reading sensor data and telemetry streams
- control: Pump control operations (start, stop, mode changes)
- schedule: Schedule management (read, write, enable/disable)
- device_info: Device information and metadata
- configuration: Backup and restore operations
- time: Real-time clock management (read and sync)
- history: Historical trend data (flow, head, temperature)
- event_log: Event log entries (start/stop cycles, errors)
- write_operation: The single serialized path for every write
- single_event: One-off scheduled runs and vacations
- run_state: How the run flag and schedule flag combine
"""

from .base import BaseService
from .configuration import ConfigurationService
from .control import ControlService
from .device_info import DeviceInfoService
from .event_log import EventLogService
from .history import HistoryService
from .run_state import RunState, is_stalled, run_state
from .schedule import ScheduleService
from .single_event import SingleEvent, SingleEventService
from .telemetry import TelemetryService
from .time import TimeService
from .write_operation import WriteOperationService

__all__ = [
    "BaseService",
    "ConfigurationService",
    "ControlService",
    "DeviceInfoService",
    "EventLogService",
    "HistoryService",
    "RunState",
    "ScheduleService",
    "SingleEvent",
    "SingleEventService",
    "TelemetryService",
    "TimeService",
    "WriteOperationService",
    "is_stalled",
    "run_state",
]
