"""
Output formatting and theming for CLI.

Provides Rich-based formatters and color themes.
"""

from .formatters import (
    format_telemetry_table,
    format_device_info_panel,
    format_schedule_table,
    format_setpoint_panel,
    format_statistics_panel,
    format_alarm_panel,
    format_json,
    print_success,
    print_error,
    print_warning,
    print_info,
)
from .themes import default_theme

__all__ = [
    "format_telemetry_table",
    "format_device_info_panel",
    "format_schedule_table",
    "format_setpoint_panel",
    "format_statistics_panel",
    "format_alarm_panel",
    "format_json",
    "print_success",
    "print_error",
    "print_warning",
    "print_info",
    "default_theme",
]
