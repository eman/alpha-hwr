"""
Grundfos ALPHA HWR Client Library
"""

__version__ = "0.1.0"

from .client import AlphaHWRClient, discover_devices
from .models import (
    TelemetryData,
    ScheduleEntry,
    SetpointInfo,
    Statistics,
    AlarmInfo,
    DeviceInfo,
)
from .exceptions import AlphaHWRError
from .constants import ControlMode, MODE_NAMES, ERROR_CODES

# Service modules (for advanced usage)
from .services import (
    ConfigurationService,
    ControlService,
    DeviceInfoService,
    ScheduleService,
    TelemetryService,
)

__all__ = [
    # Main client
    "AlphaHWRClient",
    "discover_devices",
    # Data models
    "TelemetryData",
    "ScheduleEntry",
    "SetpointInfo",
    "Statistics",
    "AlarmInfo",
    "DeviceInfo",
    # Services (for advanced usage)
    "TelemetryService",
    "ControlService",
    "ScheduleService",
    "DeviceInfoService",
    "ConfigurationService",
    # Exceptions
    "AlphaHWRError",
    # Constants
    "ControlMode",
    "MODE_NAMES",
    "ERROR_CODES",
]
