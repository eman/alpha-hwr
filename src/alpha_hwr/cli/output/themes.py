"""
Rich color themes for the CLI.

Provides consistent color schemes for terminal output.
"""

from rich.theme import Theme

# Default theme with consistent color choices
default_theme = Theme(
    {
        # Status colors
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "bold cyan",
        # Data colors
        "value": "bright_white",
        "label": "dim",
        "unit": "dim italic",
        # Header colors
        "header": "bold magenta",
        "subheader": "bold blue",
        # Pump status colors
        "running": "bold green",
        "stopped": "bold red",
        "alarm": "bold red blink",
        # Schedule colors
        "enabled": "green",
        "disabled": "dim",
        # Control mode colors
        "mode": "bold cyan",
        "setpoint": "bold yellow",
    }
)

__all__ = ["default_theme"]
