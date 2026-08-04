"""
Main Typer application for alpha-hwr CLI.

Provides a modern command-line interface with Rich formatting.
"""

import logging

import typer
from rich.console import Console

from .output.themes import default_theme

# Initialize Typer app
app = typer.Typer(
    name="alpha-hwr",
    help="Grundfos ALPHA HWR Pump Control - Monitor and control your pump via BLE",
    add_completion=False,
    rich_markup_mode="rich",
)

# Initialize Rich console with theme
console = Console(theme=default_theme)


@app.callback()
def global_options(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
) -> None:
    """Configure global options for all commands."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
        # Set bleak/asyncio to INFO to avoid too much noise
        logging.getLogger("bleak").setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)


def main() -> None:
    """Entry point for the CLI application."""
    app()


# Import and register command groups
# These will be imported when the module loads
try:
    from .commands import (
        clock,
        config,
        control,
        device,
        events,
        history,
        monitor,
        schedule,
    )

    app.add_typer(monitor.app, name="monitor", help="Monitor pump telemetry")  # type: ignore[has-type]
    app.add_typer(control.app, name="control", help="Control pump operations")  # type: ignore[has-type]
    app.add_typer(device.app, name="device", help="Device information")  # type: ignore[has-type]
    app.add_typer(schedule.app, name="schedule", help="Schedule management")  # type: ignore[has-type]
    app.add_typer(
        config.app,  # type: ignore[has-type]
        name="config",
        help="Backup and restore configuration",
    )
    app.add_typer(clock.app, name="clock", help="View and sync pump clock")  # type: ignore[has-type]
    app.add_typer(
        history.app,  # type: ignore[has-type]
        name="history",
        help="Historical data and trends",
    )
    app.add_typer(events.app, name="events", help="View event log entries")  # type: ignore[has-type]
except ImportError:
    # Commands not yet implemented, will be added later
    pass


if __name__ == "__main__":
    main()
