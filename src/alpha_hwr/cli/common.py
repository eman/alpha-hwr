"""
Common utilities for CLI commands.

Provides shared functionality like client creation, error handling,
and configuration loading.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from rich.console import Console

from ..client import AlphaHWRClient
from ..config import get_settings
from ..exceptions import AlphaHWRError
from .config_manager import ConfigManager

console = Console()


def require_service[T](service: T | None, name: str) -> T:
    """
    Check that a service is available.

    Args:
        service: Service instance or None
        name: Service name for error message

    Returns:
        The service instance

    Raises:
        SystemExit: If service is None
    """
    if service is None:
        console.print(f"[red]Error:[/red] {name} service not available")
        sys.exit(1)
    return service


@asynccontextmanager
async def get_client(
    device: str | None = None,
) -> AsyncIterator[AlphaHWRClient]:
    """
    Get configured client for CLI commands.

    Args:
        device: Optional device address override

    Yields:
        Connected and authenticated AlphaHWRClient

    Example:
        >>> async with get_client() as client:  # doctest: +SKIP
        ...     data = await client.telemetry.read_once()
    """
    settings = get_settings()
    # Priority: explicit device > config manager > env var
    address = (
        device or ConfigManager.get_default_device() or settings.device_address
    )

    if not address:
        console.print("[red]Error:[/red] No device address configured.")
        console.print(
            "Use 'alpha-hwr device scan' to find devices, then save with 'alpha-hwr device set <mac>'"
        )
        sys.exit(1)

    client = AlphaHWRClient(address)

    try:
        console.print(f"[dim]Connecting to {address}...[/dim]")
        await client.connect()
        console.print("[green]✓[/green] Connected and authenticated")

        yield client

    except AlphaHWRError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        console.print(f"[red]Unexpected error:[/red] {e}")
        sys.exit(1)

    finally:
        if client.is_connected:
            await client.disconnect()
            console.print("[dim]Disconnected[/dim]")


def handle_error(error: Exception, message: str | None = None) -> None:
    """
    Handle CLI errors with formatted output.

    Args:
        error: Exception to handle
        message: Optional context message
    """
    if message:
        console.print(f"[red]{message}:[/red] {error}")
    elif isinstance(error, AlphaHWRError):
        console.print(f"[red]Error:[/red] {error}")
    else:
        console.print(f"[red]Unexpected error:[/red] {error}")
        console.print("[dim]Use --verbose for more details[/dim]")

    sys.exit(1)


def run_async(coro):
    """
    Run async coroutine in CLI context.

    Handles KeyboardInterrupt and proper event loop cleanup.

    Args:
        coro: Coroutine to run
    """
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:  # noqa: BLE001 - top-level CLI error boundary
        handle_error(e)
