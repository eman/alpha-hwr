"""
Output formatting and theming for CLI.

Provides Rich-based formatters and color themes.
"""

from .formatters import (
    format_alarm_panel,
    format_device_info_panel,
    format_json,
    format_schedule_table,
    format_setpoint_panel,
    format_statistics_panel,
    format_telemetry_table,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from .themes import default_theme

__all__ = [
    "default_theme",
    "format_alarm_panel",
    "format_device_info_panel",
    "format_json",
    "format_schedule_table",
    "format_setpoint_panel",
    "format_statistics_panel",
    "format_telemetry_table",
    "print_error",
    "print_info",
    "print_success",
    "print_warning",
]
