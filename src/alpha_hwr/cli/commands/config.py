"""
Configuration backup and restore commands.

Commands:
  - backup: Backup pump configuration to file
  - restore: Restore pump configuration from file
"""

from datetime import UTC, datetime
from pathlib import Path

import typer

from ..app import console
from ..common import get_client, handle_error, require_service, run_async
from ..output.formatters import print_success

app = typer.Typer(help="Backup and restore pump configuration")


@app.command("backup")
def cmd_backup(
    output_file: Path | None = typer.Argument(
        None, help="Output file path (JSON format)"
    ),
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
        help="Overwrite existing file without confirmation",
    ),
) -> None:
    """
    Backup pump configuration to file.

    Saves all pump settings, schedules, and configuration to a JSON file.
    If no file is specified, a default will be created in ~/.config/alpha-hwr/backups/

    Example:
      alpha-hwr config backup
      alpha-hwr config backup pump_backup.json
      alpha-hwr config backup --force
    """
    # Check if file exists and not forcing (only if output_file is provided)
    if output_file and output_file.exists() and not force:
        confirm = typer.confirm(
            f"File {output_file} already exists. Overwrite?"
        )
        if not confirm:
            console.print("[info]Operation cancelled[/info]")
            raise typer.Exit(0)

    run_async(_config_backup(device, output_file, force))


@app.command("restore")
def cmd_restore(
    input_file: Path | None = typer.Argument(
        None, help="Input file path (JSON format)"
    ),
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
    Restore pump configuration from file.

    Loads pump settings from a previously saved backup file.
    If no file is specified, the latest backup from ~/.config/alpha-hwr/backups/ is used.
    This will overwrite current pump configuration.

    Example:
      alpha-hwr config restore
      alpha-hwr config restore pump_backup.json
      alpha-hwr config restore --force
    """
    # If no file provided, find the latest one in the default directory
    if input_file is None:
        backup_dir = Path.home() / ".config" / "alpha-hwr" / "backups"
        if not backup_dir.exists():
            console.print(
                f"[error]No backup directory found at {backup_dir}[/error]"
            )
            raise typer.Exit(1)

        backups = sorted(
            backup_dir.glob("alpha_hwr_backup_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not backups:
            console.print(
                f"[error]No automatic backups found in {backup_dir}[/error]"
            )
            raise typer.Exit(1)

        input_file = backups[0]
        console.print(f"[info]Selected latest backup: {input_file.name}[/info]")

    # Check if file exists
    if not input_file.exists():
        console.print(f"[error]File not found: {input_file}[/error]")
        raise typer.Exit(1)

    # Confirm unless forcing
    if not force:
        confirm = typer.confirm(
            f"This will overwrite current pump configuration using '{input_file.name}'. Continue?"
        )
        if not confirm:
            console.print("[info]Operation cancelled[/info]")
            raise typer.Exit(0)

    run_async(_config_restore(device, input_file))


# Internal async implementations


async def _config_backup(
    device: str | None, output_file: Path | None, force: bool
) -> None:
    """Internal async implementation of backup command."""
    try:
        async with get_client(device) as client:
            config_service = require_service(client.config, "Configuration")
            device_info_service = require_service(
                client.device_info, "DeviceInfo"
            )

            # Determine final output path
            if output_file is None:
                # Get serial number for filename
                info = await device_info_service.read_info()
                serial = (
                    info.serial_number
                    if info and info.serial_number
                    else "unknown"
                )

                # Standard backup directory: ~/.config/alpha-hwr/backups/
                backup_dir = Path.home() / ".config" / "alpha-hwr" / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)

                # Local time: the filename is for the operator, not for sorting
                # against machine timestamps.
                timestamp = (
                    datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M%S")
                )
                filename = f"alpha_hwr_backup_{serial}_{timestamp}.json"
                output_file = backup_dir / filename

            # Re-check overwrite if we just generated a path that might exist
            if output_file.exists() and not force:
                confirm = typer.confirm(
                    f"File {output_file} already exists. Overwrite?"
                )
                if not confirm:
                    console.print("[info]Operation cancelled[/info]")
                    return

            # Perform backup
            success = await config_service.backup(str(output_file))

            if success:
                print_success(
                    f"Configuration backed up to: [bold]{output_file}[/bold]"
                )
            else:
                console.print("[error]Failed to backup configuration[/error]")
                raise typer.Exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to backup configuration")


async def _config_restore(device: str | None, input_file: Path) -> None:
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

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e, "Failed to restore configuration")
