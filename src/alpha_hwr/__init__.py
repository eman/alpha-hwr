"""
Grundfos ALPHA HWR Client Library
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("alpha-hwr")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

from .client import AlphaHWRClient, discover_devices
from .constants import ERROR_CODES, MODE_NAMES, ControlMode
from .exceptions import AlphaHWRError
from .models import (
    AlarmInfo,
    DeviceInfo,
    ScheduleEntry,
    SetpointInfo,
    Statistics,
    TelemetryData,
)

# Service modules (for advanced usage)
from .services import (
    ConfigurationService,
    ControlService,
    DeviceInfoService,
    ScheduleService,
    TelemetryService,
)

# Grouped by category rather than sorted: the groups document the
# shape of the public API.
__all__ = [  # noqa: RUF022
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
