"""
Device information commands.

Commands:
  - info: Show device information
  - stats: Show operating statistics
  - alarms: Check for active alarms
"""

from typing import Optional

import typer

from ...client import AlphaHWRClient
from ..app import console
from ..common import require_service, get_client, handle_error, run_async
from ..output.formatters import (
    format_device_info_panel,
    format_statistics_panel,
    format_alarm_panel,
    format_discovery_table,
)

app = typer.Typer(help="Device information and status")


@app.command("scan")
def cmd_scan(
    timeout: float = typer.Option(
        10.0, "--timeout", "-t", help="Scan duration in seconds"
    ),
) -> None:
    """
    Scan for nearby ALPHA HWR pumps.

    Searches for devices advertising the GENI service.

    Example:
      alpha-hwr device scan
    """
    run_async(_device_scan(timeout))


@app.command("info")
def cmd_info(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Show device information.

    Displays firmware version, serial number, and other device details.

    Example:
      alpha-hwr device info
    """
    run_async(_device_info(device))


@app.command("stats")
def cmd_stats(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Show operating statistics.

    Displays operating hours, energy consumption, and other statistics.

    Example:
      alpha-hwr device stats
    """
    run_async(_device_stats(device))


@app.command("alarms")
def cmd_alarms(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Check for active alarms.

    Displays any active alarms or errors reported by the pump.

    Example:
      alpha-hwr device alarms
    """
    run_async(_device_alarms(device))


# Internal async implementations


async def _device_scan(timeout: float) -> None:
    """Internal async implementation of scan command."""
    try:
        console.print(
            f"[dim]Scanning for ALPHA HWR pumps ({timeout}s)...[/dim]"
        )
        devices = await AlphaHWRClient.discover(timeout=timeout)

        if not devices:
            console.print("[yellow]No ALPHA HWR pumps found.[/yellow]")
            console.print(
                "[dim]Tip: Ensure the pump is not already connected to another device or mobile app.[/dim]"
            )
            return

        # Display result
        table = format_discovery_table(devices)
        console.print(table)

    except Exception as e:
        handle_error(e, "Scan failed")


async def _device_info(device: Optional[str]) -> None:
    """Internal async implementation of info command."""
    try:
        async with get_client(device) as client:
            device_info = require_service(client.device_info, "DeviceInfo")
            # Get device information
            info = await device_info.read_info()

            if not info:
                console.print(
                    "[yellow]No device information available[/yellow]"
                )
                return

            # Display result
            panel = format_device_info_panel(info)
            console.print(panel)

    except Exception as e:
        handle_error(e, "Failed to read device information")


async def _device_stats(device: Optional[str]) -> None:
    """Internal async implementation of stats command."""
    try:
        async with get_client(device) as client:
            device_info = require_service(client.device_info, "DeviceInfo")
            # Get statistics
            stats = await device_info.read_statistics()

            if not stats:
                console.print("[yellow]No statistics available[/yellow]")
                return

            # Display result
            panel = format_statistics_panel(stats)
            console.print(panel)

    except Exception as e:
        handle_error(e, "Failed to read statistics")


async def _device_alarms(device: Optional[str]) -> None:
    """Internal async implementation of alarms command."""
    try:
        async with get_client(device) as client:
            device_info = require_service(client.device_info, "DeviceInfo")
            # Get alarms
            alarms = await device_info.read_alarms()

            if not alarms:
                console.print("[yellow]No alarm information available[/yellow]")
                return

            # Display result
            panel = format_alarm_panel(alarms)
            console.print(panel)

    except Exception as e:
        handle_error(e, "Failed to read alarms")
