"""
Configuration backup and restore commands.

Commands:
  - backup: Backup pump configuration to file
  - restore: Restore pump configuration from file
"""

from pathlib import Path
from typing import Optional

import typer

from ..app import console
from ..common import require_service,  get_client, handle_error, run_async
from ..output.formatters import print_success

app = typer.Typer(help="Backup and restore pump configuration")


@app.command("backup")
def cmd_backup(
    output_file: Path = typer.Argument(
        ..., help="Output file path (JSON format)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing file without confirmation",
    ),
) -> None:
    """
    Backup pump configuration to file.

    Saves all pump settings, schedules, and configuration to a JSON file.

    Example:
      alpha-hwr config backup pump_backup.json
      alpha-hwr config backup --force pump_backup.json
    """
    # Check if file exists and not forcing
    if output_file.exists() and not force:
        confirm = typer.confirm(
            f"File {output_file} already exists. Overwrite?"
        )
        if not confirm:
            console.print("[info]Operation cancelled[/info]")
            raise typer.Exit(0)

    run_async(_config_backup(device, output_file))


@app.command("restore")
def cmd_restore(
    input_file: Path = typer.Argument(
        ..., help="Input file path (JSON format)"
    ),
    device: Optional[str] = typer.Option(
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
    Restore pump configuration from file.

    Loads pump settings from a previously saved backup file.
    This will overwrite current pump configuration.

    Example:
      alpha-hwr config restore pump_backup.json
      alpha-hwr config restore --force pump_backup.json
    """
    # Check if file exists
    if not input_file.exists():
        console.print(f"[error]File not found: {input_file}[/error]")
        raise typer.Exit(1)

    # Confirm unless forcing
    if not force:
        confirm = typer.confirm(
            "This will overwrite current pump configuration. Continue?"
        )
        if not confirm:
            console.print("[info]Operation cancelled[/info]")
            raise typer.Exit(0)

    run_async(_config_restore(device, input_file))


# Internal async implementations


async def _config_backup(device: Optional[str], output_file: Path) -> None:
    """Internal async implementation of backup command."""
    try:
        async with get_client(device) as client:
            config = require_service(client.config, "Configuration")
            # Backup configuration
            success = await config.backup(str(output_file))

            if success:
                print_success(f"Configuration backed up to {output_file}")
            else:
                console.print("[error]Failed to backup configuration[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to backup configuration")


async def _config_restore(device: Optional[str], input_file: Path) -> None:
    """Internal async implementation of restore command."""
    try:
        async with get_client(device) as client:
            config = require_service(client.config, "Configuration")
            # Restore configuration
            success = await config.restore(str(input_file))

            if success:
                print_success(f"Configuration restored from {input_file}")
            else:
                console.print("[error]Failed to restore configuration[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to restore configuration")
