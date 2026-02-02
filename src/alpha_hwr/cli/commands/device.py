"""
Device information commands.

Commands:
  - info: Show device information
  - stats: Show operating statistics
  - alarms: Check for active alarms
  - scan: Scan for nearby pumps
  - set: Save a device address
  - list: List saved devices
"""

from typing import Optional

import typer

from ...client import AlphaHWRClient
from ..app import console
from ..common import require_service, get_client, handle_error, run_async
from ..config_manager import ConfigManager
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
    save: Optional[str] = typer.Option(
        None, "--save", "-s", help="Save device with this name (or 'default')"
    ),
) -> None:
    """
    Scan for nearby ALPHA HWR pumps.

    Searches for devices advertising the GENI service.

    Example:
      alpha-hwr device scan
      alpha-hwr device scan --save basement
    """
    run_async(_device_scan(timeout, save))


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


@app.command("set")
def cmd_set(
    address: str = typer.Argument(..., help="MAC address of the pump"),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Friendly name for this device"
    ),
    default: bool = typer.Option(
        False, "--default", "-d", help="Set as default device"
    ),
) -> None:
    """
    Save a device address with optional friendly name.

    Example:
      alpha-hwr device set AA:BB:CC:DD:EE:FF
      alpha-hwr device set AA:BB:CC:DD:EE:FF --name basement
      alpha-hwr device set AA:BB:CC:DD:EE:FF --name basement --default
    """
    try:
        ConfigManager.save_device(address, name, set_default=default)
        device_name = name or address
        console.print(
            f"[green]✓[/green] Saved device '{device_name}' ({address})"
        )
        if default:
            console.print("[green]✓[/green] Set as default device")
    except Exception as e:
        handle_error(e, "Failed to save device")


@app.command("list")
def cmd_list() -> None:
    """
    List all saved device addresses.

    Shows friendly names, MAC addresses, and which is default.

    Example:
      alpha-hwr device list
    """
    devices = ConfigManager.list_devices()

    if not devices:
        console.print("[yellow]No saved devices.[/yellow]")
        console.print(
            "[dim]Use 'alpha-hwr device scan' to find devices.[/dim]"
        )
        return

    # Display table
    from rich.table import Table

    table = Table(title="Saved Devices")
    table.add_column("Name", style="cyan")
    table.add_column("Address", style="magenta")
    table.add_column("Default", style="yellow")
    table.add_column("Saved At", style="dim")

    for device in devices:
        default_marker = "[green]✓[/green]" if device["is_default"] else ""
        table.add_row(
            device["name"],
            device["address"],
            default_marker,
            device["saved_at"][:19] if device["saved_at"] else "",
        )

    console.print(table)


# Internal async implementations


async def _device_scan(timeout: float, save: Optional[str] = None) -> None:
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

        # Auto-save if requested
        if save and devices:
            # Use first device if multiple found
            first_device = devices[0]
            device_address = first_device.address
            if not device_address:
                console.print(
                    "[yellow]Cannot save device without address[/yellow]"
                )
                return

            if save.lower() == "default":
                ConfigManager.set_default_device(device_address)
                console.print(
                    f"[green]✓[/green] Set default device to {device_address}"
                )
            else:
                ConfigManager.save_device(device_address, name=save)
                console.print(
                    f"[green]✓[/green] Saved device '{save}' ({device_address})"
                )

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
