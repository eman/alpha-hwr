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
"""

from .base import BaseService
from .configuration import ConfigurationService
from .control import ControlService
from .device_info import DeviceInfoService
from .event_log import EventLogService
from .history import HistoryService
from .schedule import ScheduleService
from .telemetry import TelemetryService
from .time import TimeService

__all__ = [
    "BaseService",
    "ConfigurationService",
    "ControlService",
    "DeviceInfoService",
    "EventLogService",
    "HistoryService",
    "ScheduleService",
    "TelemetryService",
    "TimeService",
]
