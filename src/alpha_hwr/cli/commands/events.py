"""
Event log commands.

Commands:
  - list: Show all event log entries
  - show: Show a specific event log entry
  - metadata: Show event log metadata
"""

from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ..app import console
from ..common import require_service, get_client, handle_error, run_async

app = typer.Typer(
    help="View pump event log entries",
    no_args_is_help=True,
)


@app.command("list")
def cmd_list(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        help="Limit number of entries to show",
    ),
    detailed: bool = typer.Option(
        False,
        "--detailed",
        help="Show detailed information including raw hex data",
    ),
) -> None:
    """
    Show all event log entries.

    Displays the pump's event log, which records historical events such as
    start/stop cycles, mode changes, and errors. The pump maintains 20 entries
    in a circular buffer.

    Example:
      alpha-hwr events list
      alpha-hwr events list --limit 10
      alpha-hwr events list --detailed
    """
    run_async(_show_list(device, limit, detailed))


@app.command("show")
def cmd_show(
    index: int = typer.Argument(
        ...,
        help="Entry index (0=newest, 19=oldest)",
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Show a specific event log entry.

    Displays detailed information about a single event log entry.

    Example:
      alpha-hwr events show 0    # Show newest entry
      alpha-hwr events show 19   # Show oldest entry
    """
    if not 0 <= index <= 19:
        console.print(
            f"[red]Error:[/red] Index must be 0-19, got {index}",
            style="bold",
        )
        raise typer.Exit(1)

    run_async(_show_entry(device, index))


@app.command("metadata")
def cmd_metadata(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Show event log metadata.

    Displays metadata about the event log including current cycle information.

    Example:
      alpha-hwr events metadata
    """
    run_async(_show_metadata(device))


# Internal async implementations


async def _show_list(
    device: Optional[str], limit: Optional[int], detailed: bool
) -> None:
    """Internal async implementation of list command."""
    try:
        async with get_client(device) as client:
            event_log = require_service(client.event_log, "EventLog")
            console.print(
                "[bold cyan]Fetching event log entries...[/bold cyan]",
                style="italic",
            )

            # Get all entries
            entries = await event_log.get_all_entries()

            if not entries:
                console.print("[yellow]No event log entries available[/yellow]")
                return

            # Apply limit if specified
            if limit is not None:
                entries = entries[:limit]

            # Build table
            if detailed:
                # Detailed view with all fields
                table = Table(
                    title=f"Event Log Entries ({len(entries)} shown)",
                    show_header=True,
                    header_style="bold cyan",
                    show_lines=True,
                )
                table.add_column("#", justify="right", style="dim", width=3)
                table.add_column("Timestamp", justify="left", width=19)
                table.add_column("Cycle", justify="right", width=5)
                table.add_column("Mode", justify="center", width=6)
                table.add_column("Event", justify="center", width=7)
                table.add_column("SubID", justify="right", style="dim", width=5)
                table.add_column("Raw Hex", justify="left", style="dim")

                for entry in entries:
                    table.add_row(
                        str(entry.index),
                        entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        str(entry.cycle_counter),
                        f"0x{entry.mode_byte:02X}",
                        f"0x{entry.event_type_flag:02X}",
                        str(entry.subid),
                        entry.raw_hex,
                    )
            else:
                # Compact view
                table = Table(
                    title=f"Event Log Entries ({len(entries)} shown)",
                    show_header=True,
                    header_style="bold cyan",
                )
                table.add_column("#", justify="right", style="dim", width=3)
                table.add_column("Timestamp", justify="left", width=19)
                table.add_column(
                    "Relative Time", justify="left", style="dim", width=12
                )
                table.add_column("Cycle", justify="right", width=6)
                table.add_column("Mode", justify="center", width=6)
                table.add_column("Event", justify="center", width=7)

                from datetime import datetime

                now = datetime.now(entries[0].timestamp.tzinfo)
                for entry in entries:
                    # Calculate relative time
                    delta = now - entry.timestamp
                    if delta.days > 0:
                        relative = f"{delta.days}d ago"
                    elif delta.seconds > 3600:
                        relative = f"{delta.seconds // 3600}h ago"
                    elif delta.seconds > 60:
                        relative = f"{delta.seconds // 60}m ago"
                    else:
                        relative = f"{delta.seconds}s ago"

                    table.add_row(
                        str(entry.index),
                        entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        relative,
                        str(entry.cycle_counter),
                        f"0x{entry.mode_byte:02X}",
                        f"0x{entry.event_type_flag:02X}",
                    )

            console.print()
            console.print(table)
            console.print()

            # Add legend
            legend = Text()
            legend.append("\n💡 ", style="dim")
            legend.append("Event Log Guide:\n", style="dim italic")
            legend.append("  • ", style="dim")
            legend.append("#", style="dim bold")
            legend.append(" = Entry index (0=newest, 19=oldest)\n", style="dim")
            legend.append("  • ", style="dim")
            legend.append("Cycle", style="dim bold")
            legend.append(
                " = Pump cycle counter at time of event\n", style="dim"
            )
            legend.append("  • ", style="dim")
            legend.append("Mode", style="dim bold")
            legend.append(" = Operating mode byte (hex)\n", style="dim")
            legend.append("  • ", style="dim")
            legend.append("Event", style="dim bold")
            legend.append(" = Event type flag (hex)\n", style="dim")

            console.print(legend)

    except Exception as e:
        handle_error(e, "Failed to fetch event log entries")


async def _show_entry(device: Optional[str], index: int) -> None:
    """Internal async implementation of show command."""
    try:
        async with get_client(device) as client:
            event_log = require_service(client.event_log, "EventLog")
            console.print(
                f"[bold cyan]Fetching event log entry {index}...[/bold cyan]",
                style="italic",
            )

            # Get single entry
            entry = await event_log.get_entry(index)

            if not entry:
                console.print(
                    f"[yellow]Event log entry {index} not available[/yellow]"
                )
                return

            # Build detailed panel
            from datetime import datetime

            # Create info text
            info = Text()
            info.append("Index:          ", style="cyan")
            info.append(f"{entry.index}\n")
            info.append("SubID:          ", style="cyan")
            info.append(f"{entry.subid}\n")
            info.append("Timestamp:      ", style="cyan")
            info.append(f"{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")

            # Calculate relative time
            now = datetime.now(entry.timestamp.tzinfo)
            delta = now - entry.timestamp
            if delta.days > 0:
                relative = f"{delta.days} days ago"
            elif delta.seconds > 3600:
                relative = f"{delta.seconds // 3600} hours ago"
            elif delta.seconds > 60:
                relative = f"{delta.seconds // 60} minutes ago"
            else:
                relative = f"{delta.seconds} seconds ago"

            info.append("Relative Time:  ", style="cyan")
            info.append(f"{relative}\n", style="dim italic")
            info.append("\n")
            info.append("Cycle Counter:  ", style="cyan")
            info.append(f"{entry.cycle_counter}\n")
            info.append("Mode Byte:      ", style="cyan")
            info.append(
                f"0x{entry.mode_byte:02X} (decimal {entry.mode_byte})\n"
            )
            info.append("Event Type:     ", style="cyan")
            info.append(
                f"0x{entry.event_type_flag:02X} (decimal {entry.event_type_flag})\n"
            )
            info.append("\n")
            info.append("Raw Hex Data:\n", style="cyan")
            info.append(f"{entry.raw_hex}\n", style="dim")

            # Create panel
            panel = Panel(
                info,
                title=f"[bold cyan]Event Log Entry #{entry.index}[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )

            console.print()
            console.print(panel)
            console.print()

    except Exception as e:
        handle_error(e, f"Failed to fetch event log entry {index}")


async def _show_metadata(device: Optional[str]) -> None:
    """Internal async implementation of metadata command."""
    try:
        async with get_client(device) as client:
            event_log = require_service(client.event_log, "EventLog")
            console.print(
                "[bold cyan]Fetching event log metadata...[/bold cyan]",
                style="italic",
            )

            # Get metadata
            metadata = await event_log.get_metadata()

            if not metadata:
                console.print(
                    "[yellow]Event log metadata not available[/yellow]"
                )
                return

            # Build panel with decoded fields
            info = Text()
            info.append("Current Cycle Counter:  ", style="cyan")
            info.append(f"{metadata.current_cycle}\n", style="bold")
            info.append("Available Entries:      ", style="cyan")
            info.append(f"{metadata.available_entries}\n", style="bold")
            info.append("Max Buffer Size:        ", style="cyan")
            info.append(f"{metadata.max_buffer_size}\n", style="bold")
            info.append("Reserved Byte:          ", style="cyan")
            info.append(f"0x{metadata.reserved:02X}\n", style="dim")
            info.append("\n")
            info.append("Raw Hex Data:\n", style="cyan")
            info.append(f"{metadata.raw_hex}\n", style="dim")
            info.append("\n")
            info.append("Structure (7 bytes):\n", style="cyan italic")
            info.append(
                "  • Bytes 0-1: Current cycle counter (uint16 BE)\n",
                style="dim italic",
            )
            info.append(
                "  • Bytes 2-3: Available entries (uint16 BE)\n",
                style="dim italic",
            )
            info.append(
                "  • Bytes 4-5: Max buffer size (uint16 BE)\n",
                style="dim italic",
            )
            info.append(
                "  • Byte  6:   Reserved/flags (uint8)\n",
                style="dim italic",
            )

            panel = Panel(
                info,
                title="[bold cyan]Event Log Metadata[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )

            console.print()
            console.print(panel)
            console.print()

    except Exception as e:
        handle_error(e, "Failed to fetch event log metadata")
