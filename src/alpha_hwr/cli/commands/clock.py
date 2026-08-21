"""
Clock (RTC) management commands.

Commands:
  - view: Display pump clock time and compare with system time
  - sync: Synchronize pump clock with system time
"""

import typer

from ... import pump_time
from ..app import console
from ..common import get_client, handle_error, require_service, run_async
from ..output.formatters import print_success

app = typer.Typer(help="View and synchronize pump real-time clock")


@app.command("view")
def cmd_view(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    View pump clock time and compare with system time.

    Displays:
    - Current pump time
    - Current system time
    - Time offset between them

    Example:
      alpha-hwr clock view
      alpha-hwr clock view --device AA:BB:CC:DD:EE:FF
    """
    run_async(_clock_view(device))


@app.command("sync")
def cmd_sync(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Synchronize pump clock with system time.

    Sets the pump's internal RTC to match your computer's current time.
    This is useful when:
    - The pump clock has never been set (shows dates in 1970s)
    - The pump clock has drifted over time
    - Schedules are not running at the correct times

    Example:
      alpha-hwr clock sync
      alpha-hwr clock sync --device AA:BB:CC:DD:EE:FF

    Note: This operation requires authentication.
    """
    run_async(_clock_sync(device))


# Make 'view' the default command when just 'alpha-hwr clock' is called
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    sync: bool = typer.Option(
        False,
        "--sync",
        "-s",
        help="Synchronize pump clock with system time",
    ),
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    View or synchronize pump real-time clock.

    By default, displays pump time and system time for comparison.
    Use --sync to synchronize the pump clock with system time.

    Examples:
      alpha-hwr clock              # View pump time
      alpha-hwr clock --sync       # Sync pump time
      alpha-hwr clock view         # Explicit view
      alpha-hwr clock sync         # Explicit sync
    """
    # If a subcommand was invoked, don't run the callback logic
    if ctx.invoked_subcommand is not None:
        return

    # Otherwise, run view or sync based on the --sync flag
    if sync:
        run_async(_clock_sync(device))
    else:
        run_async(_clock_view(device))


# Internal async implementations


async def _clock_view(device: str | None) -> None:
    """Internal async implementation of view command."""
    try:
        async with get_client(device) as client:
            time = require_service(client.time, "Time")
            # Read pump time
            pump_clock = await time.get_clock()

            if pump_clock is None:
                console.print(
                    "[error]Failed to read pump clock (no response)[/error]"
                )
                raise typer.Exit(1)

            # Naive local, to match the pump's naive wall clock: this is
            # compared against pump_clock below, and mixing naive and
            # aware datetimes raises.
            system_time = pump_time.now()

            # Check if clock is unset (epoch or very old date)
            if pump_clock.year <= 1980:
                console.print(
                    "[warning]⚠ Pump clock is unset or invalid[/warning]"
                )
                console.print(
                    f"  Pump Clock:   {pump_clock.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                console.print(
                    f"  System Clock: {system_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                console.print(
                    "\n[info]💡 Run 'alpha-hwr clock sync' to synchronize[/info]"
                )
                raise typer.Exit(0)

            # Calculate offset
            offset = (system_time - pump_clock).total_seconds()

            # Display results
            console.print(
                f"  Pump Clock:   {pump_clock.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            console.print(
                f"  System Clock: {system_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # Format offset
            if abs(offset) < 1:
                console.print(
                    f"  Offset:       [green]±{abs(offset):.1f} seconds (synchronized)[/green]"
                )
            elif abs(offset) < 60:
                console.print(
                    f"  Offset:       [yellow]{offset:+.1f} seconds[/yellow]"
                )
            elif abs(offset) < 3600:
                minutes = offset / 60
                console.print(
                    f"  Offset:       [yellow]{minutes:+.1f} minutes[/yellow]"
                )
            else:
                hours = offset / 3600
                console.print(f"  Offset:       [red]{hours:+.1f} hours[/red]")
                console.print(
                    "\n[info]💡 Run 'alpha-hwr clock sync' to synchronize[/info]"
                )

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to read pump clock")


async def _clock_sync(device: str | None) -> None:
    """Internal async implementation of sync command."""
    try:
        async with get_client(device) as client:
            time = require_service(client.time, "Time")
            # Sync clock
            success = await time.set_clock()

            if success:
                print_success("Pump clock synchronized with system time")
            else:
                console.print("[error]Failed to synchronize pump clock[/error]")
                raise typer.Exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to synchronize pump clock")
