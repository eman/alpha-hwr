"""
Control commands for pump operations.

Commands:
  - status: Show current control mode and setpoint
  - start: Start the pump motor
  - stop: Stop the pump motor
  - enable-remote: Enable remote control mode
  - disable-remote: Disable remote control mode (return to auto)
  - set-pressure: Set constant pressure mode
  - set-differential: Set differential pressure mode
  - set-flow: Set constant flow mode
  - set-speed: Set constant speed mode (RPM)
  - set-mode: Set a specific control mode by name
  - set-autoadapt: Set AutoAdapt mode (radiator, underfloor, or combined)
  - set-temperature: Set temperature range control
"""

from typing import Optional

import typer

from ..app import console
from ..common import require_service, get_client, handle_error, run_async
from ..output.formatters import format_setpoint_panel, print_success

app = typer.Typer(help="Control pump operations")


@app.command("status")
def cmd_status(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Show current control mode and setpoint.

    Displays the current operating mode and setpoint value.

    Example:
      alpha-hwr control status
    """
    run_async(_control_status(device))


@app.command("start")
def cmd_start(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Start the pump motor.

    Enables pump operation in the current control mode.

    Example:
      alpha-hwr control start
    """
    run_async(_control_start(device))


@app.command("stop")
def cmd_stop(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Stop the pump motor.

    Disables pump operation while maintaining the control mode.

    Example:
      alpha-hwr control stop
    """
    run_async(_control_stop(device))


@app.command("enable-remote")
def cmd_enable_remote(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Enable remote control mode.

    Allows external control of the pump via BLE/API commands.
    When enabled, the pump accepts control commands and ignores local controls.

    Example:
      alpha-hwr control enable-remote
    """
    run_async(_control_enable_remote(device))


@app.command("disable-remote")
def cmd_disable_remote(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Disable remote control mode (return to Auto).

    Returns the pump to automatic operation based on its internal logic
    and local controls.

    Example:
      alpha-hwr control disable-remote
    """
    run_async(_control_disable_remote(device))


@app.command("set-pressure")
def cmd_set_pressure(
    setpoint: float = typer.Argument(
        ..., help="Pressure setpoint in meters (m)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set constant pressure mode.

    Sets the pump to maintain a constant outlet pressure.

    Example:
      alpha-hwr control set-pressure 1.5
    """
    run_async(_control_set_mode(device, "constant_pressure", setpoint))


@app.command("set-differential")
def cmd_set_differential(
    setpoint: float = typer.Argument(
        ..., help="Differential pressure setpoint in meters (m)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set differential pressure mode.

    Sets the pump to maintain a constant pressure difference.

    Example:
      alpha-hwr control set-differential 2.0
    """
    run_async(_control_set_mode(device, "differential_pressure", setpoint))


@app.command("set-flow")
def cmd_set_flow(
    setpoint: float = typer.Argument(..., help="Flow setpoint in m³/h"),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set constant flow mode.

    Sets the pump to maintain a constant flow rate.

    Example:
      alpha-hwr control set-flow 0.5
    """
    run_async(_control_set_mode(device, "constant_flow", setpoint))


@app.command("set-speed")
def cmd_set_speed(
    setpoint: float = typer.Argument(
        ..., help="Speed setpoint in RPM (e.g., 2500)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set constant speed mode.

    Sets the pump to run at a fixed rotational speed (RPM).

    Example:
      alpha-hwr control set-speed 2500
    """
    run_async(_control_set_mode(device, "constant_speed", setpoint))


@app.command("set-mode")
def cmd_set_mode(
    mode: str = typer.Argument(
        ...,
        help="Mode name (constant-pressure, proportional-pressure, constant-speed, constant-flow, autoadapt-radiator, autoadapt-underfloor, autoadapt-combined)",
    ),
    setpoint: float = typer.Argument(..., help="Setpoint value"),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set a specific control mode by name.

    Example:
      alpha-hwr control set-mode constant-pressure 1.5
      alpha-hwr control set-mode autoadapt-radiator 3.0
    """
    # Normalize mode name
    normalized_mode = mode.lower().replace("-", "_")
    run_async(_control_set_mode(device, normalized_mode, setpoint))


@app.command("set-autoadapt")
def cmd_set_autoadapt(
    variant: str = typer.Argument(
        "radiator",
        help="Variant: radiator, underfloor, or combined",
    ),
    setpoint: float = typer.Argument(
        2.5, help="Setpoint in meters (default 2.5m)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set AutoAdapt mode.

    Examples:
      alpha-hwr control set-autoadapt radiator 3.0
      alpha-hwr control set-autoadapt underfloor 2.0
      alpha-hwr control set-autoadapt combined 3.5
    """
    mode_map = {
        "radiator": "autoadapt_radiator",
        "underfloor": "autoadapt_underfloor",
        "combined": "autoadapt_combined",
    }
    mode = mode_map.get(variant.lower())
    if not mode:
        console.print(
            f"[error]Invalid variant: {variant}. Choose radiator, underfloor, or combined.[/error]"
        )
        raise typer.Exit(1)

    run_async(_control_set_mode(device, mode, setpoint))


@app.command("set-temperature")
def cmd_set_temperature(
    min_temp: float = typer.Argument(..., help="Minimum temperature (°C)"),
    max_temp: float = typer.Argument(45.0, help="Maximum temperature (°C)"),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set temperature range control.

    Example:
      alpha-hwr control set-temperature 35.0 45.0
    """
    run_async(_control_set_temperature(device, min_temp, max_temp))


# Internal async implementations


async def _control_status(device: Optional[str]) -> None:
    """Internal async implementation of status command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Get current mode and setpoint
            setpoint_info = await control.get_mode()

            if not setpoint_info:
                console.print("[yellow]Could not read control mode[/yellow]")
                return

            # Display result
            panel = format_setpoint_panel(setpoint_info)
            console.print(panel)

    except Exception as e:
        handle_error(e, "Failed to read control status")


async def _control_start(device: Optional[str]) -> None:
    """Internal async implementation of start command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Start pump
            success = await control.start()

            if success:
                print_success("Pump started successfully")
            else:
                console.print("[error]Failed to start pump[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to start pump")


async def _control_stop(device: Optional[str]) -> None:
    """Internal async implementation of stop command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Stop pump
            success = await control.stop()

            if success:
                print_success("Pump stopped successfully")
            else:
                console.print("[error]Failed to stop pump[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to stop pump")


async def _control_enable_remote(device: Optional[str]) -> None:
    """Internal async implementation of enable-remote command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Enable remote mode
            success = await control.enable_remote_mode()

            if success:
                print_success("Remote control mode enabled")
            else:
                console.print("[error]Failed to enable remote mode[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to enable remote mode")


async def _control_disable_remote(device: Optional[str]) -> None:
    """Internal async implementation of disable-remote command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Disable remote mode
            success = await control.disable_remote_mode()

            if success:
                print_success("Remote control mode disabled (returned to Auto)")
            else:
                console.print("[error]Failed to disable remote mode[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to disable remote mode")


async def _control_set_mode(
    device: Optional[str], mode: str, setpoint: float
) -> None:
    """Internal async implementation of set mode commands."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")

            # Map mode string to appropriate method
            mode_methods = {
                "constant_pressure": control.set_constant_pressure,
                "differential_pressure": control.set_constant_pressure,  # Same method
                "constant_flow": control.set_constant_flow,
                "constant_speed": control.set_constant_speed,
                "proportional_pressure": control.set_proportional_pressure,
                "autoadapt_radiator": control.set_autoadapt_radiator,
                "autoadapt_underfloor": control.set_autoadapt_underfloor,
                "autoadapt_combined": control.set_autoadapt_combined,
            }

            method = mode_methods.get(mode)
            if not method:
                console.print(f"[error]Unknown mode: {mode}[/error]")
                raise typer.Exit(1)

            # Call the appropriate method
            success = await method(setpoint)

            if success:
                print_success(f"Set {mode.replace('_', ' ')} to {setpoint}")
            else:
                console.print("[error]Failed to set control mode[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, f"Failed to set {mode}")


async def _control_set_temperature(
    device: Optional[str], min_temp: float, max_temp: float
) -> None:
    """Internal async implementation of set-temperature command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Set temperature range control
            success = await control.set_temperature_range_control(
                min_temp, max_temp
            )

            if success:
                print_success(
                    f"Set Temperature Range Control to {min_temp}°C - {max_temp}°C"
                )
            else:
                console.print("[error]Failed to set temperature range[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to set temperature range")
