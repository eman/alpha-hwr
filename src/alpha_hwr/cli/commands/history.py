"""
Historical data and trend commands.

Commands:
  - trends: Show historical trend data (flow, head, temperature)
  - timestamps: Show pump cycle timestamps
"""

from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.console import Group

from ..app import console
from ..common import require_service, get_client, handle_error, run_async

app = typer.Typer(
    help="Historical trend data and cycle timestamps",
    no_args_is_help=True,  # Show help when no subcommand provided
)


@app.command("trends")
def cmd_trends(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
    detailed: bool = typer.Option(
        False,
        "--detailed",
        help="Show all 100-cycle historical data (not just 10-cycle)",
    ),
) -> None:
    """
    Show historical trend data.

    Displays flow, head, and temperature measurements over the last
    10 pump cycles (or 100 cycles with --detailed flag).

    Example:
      alpha-hwr history trends
      alpha-hwr history trends --detailed
    """
    run_async(_show_trends(device, detailed))


@app.command("timestamps")
def cmd_timestamps(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
    count: int = typer.Option(
        10,
        "--count",
        "-n",
        help="Number of timestamps to show (10 or 100)",
    ),
) -> None:
    """
    Show pump cycle timestamps.

    Displays the timestamps of recent pump cycles.

    Example:
      alpha-hwr history timestamps
      alpha-hwr history timestamps --count 100
    """
    if count not in (10, 100):
        console.print("[red]Error:[/red] Count must be 10 or 100", style="bold")
        raise typer.Exit(1)

    run_async(_show_timestamps(device, count))


# Internal async implementations


async def _show_trends(device: Optional[str], detailed: bool) -> None:
    """Internal async implementation of trends command."""
    try:
        async with get_client(device) as client:
            history = require_service(client.history, "History")
            console.print(
                "[bold cyan]Fetching trend data...[/bold cyan]",
                style="italic",
            )

            # Get trend data
            trends = await history.get_trend_data()

            if not trends:
                console.print("[yellow]No trend data available[/yellow]")
                return

            # Build panels for each series
            panels = []

            if trends.flow_series:
                panels.append(
                    _format_series_panel(trends.flow_series, detailed)
                )

            if trends.head_series:
                panels.append(
                    _format_series_panel(trends.head_series, detailed)
                )

            if trends.media_temperature_series:
                panels.append(
                    _format_series_panel(
                        trends.media_temperature_series, detailed
                    )
                )

            if trends.power_on_time_series:
                panels.append(
                    _format_series_panel(trends.power_on_time_series, detailed)
                )

            # Display panels
            if panels:
                console.print()
                for panel in panels:
                    console.print(panel)
                    console.print()
            else:
                console.print("[yellow]No trend data series available[/yellow]")

    except Exception as e:
        handle_error(e, "Failed to fetch trend data")


async def _show_timestamps(device: Optional[str], count: int) -> None:
    """Internal async implementation of timestamps command."""
    try:
        async with get_client(device) as client:
            history = require_service(client.history, "History")
            console.print(
                f"[bold cyan]Fetching last {count} cycle timestamps...[/bold cyan]",
                style="italic",
            )

            # Get timestamps
            timestamps = await history.get_cycle_timestamps(count=count)

            if not timestamps:
                console.print("[yellow]No timestamp data available[/yellow]")
                return

            # Build table
            table = Table(
                title=f"Last {count} Pump Cycles",
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("#", justify="right", style="dim")
            table.add_column("Timestamp", justify="left")
            table.add_column("Relative Time", justify="left", style="dim")

            # Add rows
            from datetime import datetime

            now = datetime.now()
            for i, ts in enumerate(timestamps, 1):
                # Calculate relative time
                delta = now - ts
                if delta.days > 0:
                    relative = f"{delta.days}d ago"
                elif delta.seconds > 3600:
                    relative = f"{delta.seconds // 3600}h ago"
                elif delta.seconds > 60:
                    relative = f"{delta.seconds // 60}m ago"
                else:
                    relative = f"{delta.seconds}s ago"

                table.add_row(
                    str(i),
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    relative,
                )

            console.print()
            console.print(table)
            console.print()

    except Exception as e:
        handle_error(e, "Failed to fetch cycle timestamps")


# Helper functions


def _format_series_panel(series, detailed: bool) -> Panel:
    """
    Format a trend data series as a Rich panel.

    Args:
        series: TrendDataSeries object
        detailed: Whether to show 100-cycle data

    Returns:
        Rich Panel with formatted series data
    """
    # Build table for 10-cycle data
    table_10 = Table(
        title="Last 10 Cycles (High Resolution)",
        show_header=True,
        header_style="bold green",
        show_lines=False,
    )
    table_10.add_column("#", justify="right", style="dim", width=3)
    table_10.add_column("Timestamp", justify="left", width=19)
    table_10.add_column("Value", justify="right", style="bold")

    for i, point in enumerate(series.cycle_10_points, 1):
        table_10.add_row(
            str(i),
            point.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            f"{point.value:.2f} {series.unit}",
        )

    if not series.cycle_10_points:
        table_10.add_row("", "No data", "", style="dim italic")

    # Build content - default to just the 10-cycle table
    content: Table | Group = table_10

    # Add 100-cycle table if detailed
    if detailed and series.cycle_100_points:
        table_100 = Table(
            title="Last 100 Cycles (Historical)",
            show_header=True,
            header_style="bold blue",
            show_lines=False,
        )
        table_100.add_column("#", justify="right", style="dim", width=3)
        table_100.add_column("Timestamp", justify="left", width=19)
        table_100.add_column("Value", justify="right", style="bold")

        for i, point in enumerate(series.cycle_100_points, 1):
            table_100.add_row(
                str(i),
                point.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                f"{point.value:.2f} {series.unit}",
            )

        # Combine both tables
        content = Group(table_10, "", table_100)

    elif series.cycle_100_points:
        # Add note about 100-cycle data
        from rich.text import Text

        note = Text(
            f"\n💡 {len(series.cycle_100_points)} historical points available "
            "(use --detailed to view)",
            style="dim italic",
        )
        content = Group(table_10, note)

    # Create panel
    panel = Panel(
        content,
        title=f"[bold cyan]{series.name}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )

    return panel
