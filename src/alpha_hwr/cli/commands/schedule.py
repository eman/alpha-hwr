"""
Schedule management commands.

Commands:
  - list: Show current schedule
  - add: Add a schedule entry
  - remove: Remove a schedule entry
  - enable: Enable schedule control
  - disable: Disable schedule control
  - clear: Clear all schedule entries
"""

import typer

from ..app import console
from ..common import get_client, handle_error, run_async
from ..output.formatters import format_schedule_table, print_success

app = typer.Typer(help="Manage pump schedules")


@app.command("list")
def cmd_list(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Show current schedule.

    Displays all configured schedule entries and whether scheduling is enabled.

    Example:
      alpha-hwr schedule list
    """
    run_async(_schedule_list(device))


@app.command("add")
def cmd_add(
    day: str = typer.Argument(
        ..., help="Day of week (e.g., monday, tuesday, ...)"
    ),
    start_time: str = typer.Argument(..., help="Start time (HH:MM format)"),
    end_time: str = typer.Argument(..., help="End time (HH:MM format)"),
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Add a schedule entry.

    Adds a time period for the pump to operate on the specified day.

    Example:
      alpha-hwr schedule add monday 06:00 08:30
    """
    run_async(_schedule_add(device, day, start_time, end_time))


@app.command("remove")
def cmd_remove(
    day: str = typer.Argument(..., help="Day of week to clear"),
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Remove a schedule entry.

    Removes the schedule entry for the specified day.

    Example:
      alpha-hwr schedule remove monday
    """
    run_async(_schedule_remove(device, day))


@app.command("enable")
def cmd_enable(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Enable schedule control.

    Activates schedule-based pump operation.

    Example:
      alpha-hwr schedule enable
    """
    run_async(_schedule_enable(device))


@app.command("disable")
def cmd_disable(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Disable schedule control.

    Deactivates schedule-based pump operation.

    Example:
      alpha-hwr schedule disable
    """
    run_async(_schedule_disable(device))


@app.command("clear")
def cmd_clear(
    device: str | None = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """
    Clear all schedule entries.

    Removes all configured schedule entries from all days.

    Example:
      alpha-hwr schedule clear
      alpha-hwr schedule clear --force
    """
    if not force:
        confirm = typer.confirm(
            "Are you sure you want to clear all schedule entries?"
        )
        if not confirm:
            console.print("[info]Operation cancelled[/info]")
            raise typer.Exit(0)

    run_async(_schedule_clear(device))


# Internal async implementations


async def _schedule_list(device: str | None) -> None:
    """Internal async implementation of list command."""
    try:
        async with get_client(device) as client:
            if not client.schedule:
                console.print("[red]Schedule service not available[/red]")
                raise typer.Exit(1)

            # Check if schedule is enabled
            is_enabled = await client.schedule.get_state()

            # Display enabled state
            if is_enabled is True:
                console.print(
                    "[bold green]✓[/bold green] Schedule is ENABLED - pump will follow schedule"
                )
            elif is_enabled is False:
                console.print(
                    "[bold yellow]✗[/bold yellow] Schedule is DISABLED - pump ignores schedule"
                )
            else:
                console.print("[dim]Could not determine schedule state[/dim]")

            console.print()  # Blank line

            # Get schedule entries
            schedule = await client.schedule.read_entries()

            # Display result
            table = format_schedule_table(schedule)
            console.print(table)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to read schedule")


async def _schedule_add(
    device: str | None, day: str, start_time: str, end_time: str
) -> None:
    """Internal async implementation of add command."""
    try:
        from alpha_hwr.models import ScheduleEntry

        async with get_client(device) as client:
            if not client.schedule:
                console.print("[red]Schedule service not available[/red]")
                raise typer.Exit(1)

            # Parse times
            start_parts = start_time.split(":")
            end_parts = end_time.split(":")

            # Read existing entries
            existing = await client.schedule.read_entries()

            # Create new entry
            new_entry = ScheduleEntry(
                day=day,
                begin_hour=int(start_parts[0]),
                begin_minute=int(start_parts[1]),
                end_hour=int(end_parts[0]),
                end_minute=int(end_parts[1]),
                enabled=True,
                layer=0,
            )

            # Add to list
            entries = existing + [new_entry]

            # Write back
            success = await client.schedule.write_entries(entries)

            if success:
                print_success(
                    f"Added schedule entry for {day}: {start_time} - {end_time}"
                )
            else:
                console.print("[error]Failed to add schedule entry[/error]")
                raise typer.Exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to add schedule entry")


async def _schedule_remove(device: str | None, day: str) -> None:
    """Internal async implementation of remove command."""
    try:
        async with get_client(device) as client:
            if not client.schedule:
                console.print("[red]Schedule service not available[/red]")
                raise typer.Exit(1)

            # Read existing entries
            existing = await client.schedule.read_entries()

            # Filter out entries for the specified day
            filtered = [e for e in existing if e.day.lower() != day.lower()]

            if len(filtered) == len(existing):
                console.print(
                    f"[yellow]No schedule entry found for {day}[/yellow]"
                )
                raise typer.Exit(1)

            # Write back
            success = await client.schedule.write_entries(filtered)

            if success:
                print_success(f"Removed schedule entry for {day}")
            else:
                console.print("[error]Failed to remove schedule entry[/error]")
                raise typer.Exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to remove schedule entry")


async def _schedule_enable(device: str | None) -> None:
    """Internal async implementation of enable command."""
    try:
        async with get_client(device) as client:
            if not client.schedule:
                console.print("[red]Schedule service not available[/red]")
                raise typer.Exit(1)

            # Enable schedule
            success = await client.schedule.enable()

            if success:
                print_success("Schedule enabled")
            else:
                console.print("[error]Failed to enable schedule[/error]")
                raise typer.Exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to enable schedule")


async def _schedule_disable(device: str | None) -> None:
    """Internal async implementation of disable command."""
    try:
        async with get_client(device) as client:
            if not client.schedule:
                console.print("[red]Schedule service not available[/red]")
                raise typer.Exit(1)

            # Disable schedule
            success = await client.schedule.disable()

            if success:
                print_success("Schedule disabled")
            else:
                console.print("[error]Failed to disable schedule[/error]")
                raise typer.Exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to disable schedule")


async def _schedule_clear(device: str | None) -> None:
    """Internal async implementation of clear command."""
    try:
        async with get_client(device) as client:
            if not client.schedule:
                console.print("[red]Schedule service not available[/red]")
                raise typer.Exit(1)

            # Clear all schedule entries by writing empty list
            success = await client.schedule.write_entries([])

            if success:
                print_success("All schedule entries cleared")
            else:
                console.print("[error]Failed to clear schedule entries[/error]")
                raise typer.Exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to clear schedule entries")
