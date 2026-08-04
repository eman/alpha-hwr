"""
Monitor commands for real-time telemetry.

Commands:
  - live: Continuous real-time monitoring
  - snapshot: Single telemetry reading
"""

import asyncio

import typer
from rich.live import Live

from ..app import console
from ..common import get_client, handle_error, require_service, run_async
from ..output.formatters import format_json, format_telemetry_table

app = typer.Typer(help="Monitor pump telemetry in real-time")


@app.command("live")
def cmd_live(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
    interval: float = typer.Option(
        1.0,
        "--interval",
        "-i",
        help="Update interval in seconds",
        min=0.1,
        max=10.0,
    ),
    format_type: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table or json",
    ),
) -> None:
    """
    Monitor pump telemetry in real-time.

    Continuously updates with latest telemetry data from the pump.
    Press Ctrl+C to stop monitoring.

    Examples:
      alpha-hwr monitor live
      alpha-hwr monitor live --interval 2.0
      alpha-hwr monitor live --format json
    """
    run_async(_monitor_live(device, interval, format_type))


@app.command("snapshot")
def cmd_snapshot(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
    format_type: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table or json",
    ),
) -> None:
    """
    Take a single telemetry snapshot.

    Reads current telemetry data once and displays it.

    Examples:
      alpha-hwr monitor snapshot
      alpha-hwr monitor snapshot --format json
    """
    run_async(_monitor_snapshot(device, format_type))


async def _monitor_live(
    device: str | None, interval: float, format_type: str
) -> None:
    """Internal async implementation of live monitoring."""
    try:
        async with get_client(device) as client:
            telemetry = require_service(client.telemetry, "Telemetry")
            if format_type == "table":
                # Use Rich Live display for continuous updates
                with Live(console=console, refresh_per_second=4) as live:
                    while True:
                        # Read telemetry
                        data = await telemetry.read_once()

                        # Update display
                        table = format_telemetry_table(data)
                        live.update(table)

                        # Wait for next update
                        await asyncio.sleep(interval)

            else:  # json format
                while True:
                    # Read telemetry
                    data = await telemetry.read_once()

                    # Print JSON
                    format_json(data)

                    # Wait for next update
                    await asyncio.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[info]Monitoring stopped[/info]")
    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to monitor pump")


async def _monitor_snapshot(device: str | None, format_type: str) -> None:
    """Internal async implementation of snapshot."""
    try:
        async with get_client(device) as client:
            telemetry = require_service(client.telemetry, "Telemetry")
            # Read telemetry once
            data = await telemetry.read_once()

            # Display result
            if format_type == "table":
                table = format_telemetry_table(data)
                console.print(table)
            else:  # json
                format_json(data)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to read telemetry")
