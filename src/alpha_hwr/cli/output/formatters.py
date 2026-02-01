"""
Output formatters for CLI using Rich.

Provides consistent, beautiful output formatting for telemetry,
device info, schedules, and other data.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ...models import (
    TelemetryData,
    DeviceInfo,
    ScheduleEntry,
    SetpointInfo,
    Statistics,
    AlarmInfo,
)

console = Console()


def format_telemetry_table(data: TelemetryData) -> Table:
    """
    Format telemetry data as Rich table.

    Args:
        data: Telemetry data to format

    Returns:
        Rich Table object
    """
    table = Table(
        title="Pump Telemetry", show_header=True, header_style="bold cyan"
    )
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")
    table.add_column("Unit")

    # Flow
    if data.flow_m3h is not None:
        table.add_row("Flow", f"{data.flow_m3h:.2f}", "m³/h")

    # Head/Pressure
    if data.head_m is not None:
        table.add_row("Head", f"{data.head_m:.2f}", "m")

    # Power
    if data.power_w is not None:
        table.add_row("Power", f"{data.power_w:.1f}", "W")

    # Speed
    if data.speed_rpm is not None:
        table.add_row("Speed", f"{data.speed_rpm:.0f}", "RPM")

    # Setpoint
    if data.setpoint_rpm is not None:
        table.add_row("Setpoint", f"{data.setpoint_rpm:.0f}", "RPM")

    # Temperatures
    if data.media_temperature_c is not None:
        table.add_row("Media Temp", f"{data.media_temperature_c:.1f}", "°C")

    if data.pcb_temperature_c is not None:
        table.add_row("PCB Temp", f"{data.pcb_temperature_c:.1f}", "°C")

    if data.control_box_temperature_c is not None:
        table.add_row("Box Temp", f"{data.control_box_temperature_c:.1f}", "°C")

    # Electrical
    if data.voltage_ac_v is not None:
        table.add_row("Voltage AC", f"{data.voltage_ac_v:.1f}", "V")

    if data.voltage_dc_v is not None:
        table.add_row("Voltage DC", f"{data.voltage_dc_v:.1f}", "V")

    if data.current_a is not None:
        table.add_row("Current", f"{data.current_a:.2f}", "A")

    # Timestamp
    if data.timestamp:
        table.add_row("", "", "")  # Separator
        table.add_row("Updated", data.timestamp.strftime("%H:%M:%S"), "")

    return table


def format_device_info_panel(info: DeviceInfo) -> Panel:
    """
    Format device info as Rich panel.

    Args:
        info: Device information to format

    Returns:
        Rich Panel object
    """
    lines = []

    # Product identification
    if info.product_family is not None and info.product_type is not None:
        product_str = f"Family {info.product_family}, Type {info.product_type}"
        if info.product_version is not None:
            product_str += f", Version {info.product_version}"
        lines.append(f"[bold]Product:[/bold] {product_str}")

    if info.product_name:
        lines.append(f"[bold]Product Name:[/bold] {info.product_name}")

    if info.product_number:
        lines.append(f"[bold]Product Number:[/bold] {info.product_number}")

    if info.serial_number:
        lines.append(f"[bold]Serial:[/bold] {info.serial_number}")

    if info.production_year_week:
        lines.append(
            f"[bold]Production Code:[/bold] {info.production_year_week}"
        )

    # Firmware versions
    if info.software_version:
        lines.append(f"[bold]Software:[/bold] {info.software_version}")

    if info.hardware_version:
        lines.append(f"[bold]Hardware:[/bold] {info.hardware_version}")

    if info.ble_version:
        lines.append(f"[bold]BLE Software:[/bold] {info.ble_version}")

    content = (
        "\n".join(lines)
        if lines
        else "[dim]No device information available[/dim]"
    )

    return Panel(content, title="Device Information", border_style="blue")


def format_discovery_table(devices: list[DeviceInfo]) -> Table:
    """
    Format discovered devices as Rich table.

    Args:
        devices: List of discovered device info

    Returns:
        Rich Table object
    """
    table = Table(
        title="Discovered ALPHA HWR Pumps",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Device Name", style="cyan")
    table.add_column("Address", style="green")
    table.add_column("Product", style="blue")

    for device in devices:
        table.add_row(
            device.name or "Unknown",
            device.address or "Unknown",
            device.product_name or "ALPHA HWR",
        )

    return table


def format_schedule_table(entries: list[ScheduleEntry]) -> Table:
    """
    Format schedule entries as Rich table.

    Args:
        entries: List of schedule entries

    Returns:
        Rich Table object
    """
    table = Table(
        title="Weekly Schedule", show_header=True, header_style="bold cyan"
    )
    table.add_column("Day", style="cyan")
    table.add_column("Start", justify="center")
    table.add_column("End", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Layer", justify="center", style="dim")

    # Sort by day and start time
    sorted_entries = sorted(
        entries, key=lambda e: (e.day_index, e.begin_hour, e.begin_minute)
    )

    for entry in sorted_entries:
        duration_min = entry.get_duration_minutes()
        duration_str = f"{duration_min // 60}h {duration_min % 60}m"

        table.add_row(
            entry.day,
            entry.begin_time,
            entry.end_time,
            duration_str,
            str(entry.layer),
        )

    return table


def format_setpoint_panel(info: SetpointInfo) -> Panel:
    """
    Format setpoint information as Rich panel.

    Args:
        info: Setpoint information

    Returns:
        Rich Panel object
    """
    lines = []

    # Current setpoint
    value, unit = info.get_display_value()
    lines.append(f"[bold]Current Setpoint:[/bold] {value:.2f} {unit}")

    # Operational Status
    if info.is_running is not None:
        status_str = (
            "[green]Started[/green]"
            if info.is_running
            else "[red]Stopped[/red]"
        )
        lines.append(f"[bold]Pump Status:[/bold] {status_str}")

    if info.is_remote is not None:
        remote_str = (
            "[green]Enabled[/green]"
            if info.is_remote
            else "[yellow]Disabled (Local)[/yellow]"
        )
        lines.append(f"[bold]Remote Control:[/bold] {remote_str}")

    if info.schedule_enabled is not None:
        sched_str = (
            "[green]Active[/green]"
            if info.schedule_enabled
            else "[yellow]Inactive[/yellow]"
        )
        lines.append(f"[bold]Internal Schedule:[/bold] {sched_str}")

    # Limits
    if info.min_setpoint is not None and info.max_setpoint is not None:
        limits = info.get_limits_display()
        if limits:
            (min_val, min_unit), (max_val, max_unit) = limits
            lines.append(
                f"[bold]Range:[/bold] {min_val:.2f} - {max_val:.2f} {max_unit}"
            )

    # Mode-specific info
    if info.control_mode is not None:
        from ...constants import ControlMode

        try:
            mode_name = ControlMode(info.control_mode).name
            lines.append(f"[dim]Mode: {mode_name} ({info.control_mode})[/dim]")
        except ValueError:
            lines.append(f"[dim]Mode: {info.control_mode}[/dim]")

    content = "\n".join(lines)

    return Panel(content, title="Setpoint Information", border_style="green")


def format_statistics_panel(stats: Statistics) -> Panel:
    """
    Format statistics as Rich panel.

    Args:
        stats: Device statistics

    Returns:
        Rich Panel object
    """
    lines = []

    if stats.operating_hours is not None:
        lines.append(
            f"[bold]Operating Hours:[/bold] {stats.operating_hours:.1f} h"
        )

    if stats.start_count is not None:
        lines.append(f"[bold]Start Count:[/bold] {stats.start_count:,}")

    if stats.energy_kwh is not None:
        lines.append(
            f"[bold]Energy Consumed:[/bold] {stats.energy_kwh:.2f} kWh"
        )

    content = (
        "\n".join(lines) if lines else "[dim]No statistics available[/dim]"
    )

    return Panel(content, title="Pump Statistics", border_style="yellow")


def format_alarm_panel(alarm: AlarmInfo) -> Panel:
    """
    Format alarm information as Rich panel.

    Args:
        alarm: Alarm information

    Returns:
        Rich Panel object
    """
    if not alarm.alarm_code or alarm.alarm_code == 0:
        content = "[green]✓ No active alarms[/green]"
        style = "green"
    else:
        lines = [
            f"[bold red]⚠ ALARM {alarm.alarm_code}[/bold red]",
            f"[bold]Description:[/bold] {alarm.alarm_description or 'Unknown'}",
        ]

        if alarm.warning_code and alarm.warning_code != 0:
            lines.append("")
            lines.append(f"[yellow]⚠ WARNING {alarm.warning_code}[/yellow]")
            lines.append(
                f"[bold]Description:[/bold] {alarm.warning_description or 'Unknown'}"
            )

        content = "\n".join(lines)
        style = "red"

    return Panel(content, title="Alarm Status", border_style=style)


def format_json(data: Any) -> None:
    """
    Format data as JSON output.

    Args:
        data: Data to format (must be JSON-serializable)
    """
    import json

    if hasattr(data, "model_dump"):
        # Pydantic model
        json_str = data.model_dump_json(indent=2)
    elif hasattr(data, "to_dict"):
        # Has to_dict method
        json_str = json.dumps(data.to_dict(), indent=2)
    else:
        # Raw dict or list
        json_str = json.dumps(data, indent=2, default=str)

    console.print(json_str)


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[blue]ℹ[/blue] {message}")
