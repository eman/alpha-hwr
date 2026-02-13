"""
Control commands for pump operations.

Commands:
  - status: Show current control mode and setpoint
  - start: Start the pump motor
  - stop: Stop the pump motor
  - enable-remote: Enable remote control mode
  - disable-remote: Disable remote control mode (return to auto)
  - set-pressure: Set constant pressure mode
  - set-proportional: Set proportional pressure mode
  - set-flow: Set constant flow mode
  - set-speed: Set constant speed mode (RPM)
  - set-temperature: Set temperature range control
  - set-cycle-time: Set DHW cycle time control
  - set-flow-limit: Set maximum flow limit (GPM)
  - get-cycle-time: Get DHW cycle time configuration
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


@app.command("set-proportional")
def cmd_set_proportional(
    setpoint: float = typer.Argument(
        ..., help="Proportional pressure setpoint in meters (m)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set proportional pressure mode.

    Sets the pump to adjust pressure proportionally to flow.

    Example:
      alpha-hwr control set-proportional 1.2
    """
    run_async(_control_set_mode(device, "proportional_pressure", setpoint))


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
    flow_limit: Optional[float] = typer.Option(
        None, "--flow-limit", "-f", help="Maximum flow limit in GPM (e.g. 1.5)"
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
    Optionally sets a flow limit (often used for 'Continuous operation').

    Example:
      alpha-hwr control set-speed 2500 --flow-limit 1.5
    """
    run_async(_control_set_speed(device, setpoint, flow_limit))


@app.command("set-mode")
def cmd_set_mode(
    mode: str = typer.Argument(
        ...,
        help="Mode name: constant-pressure, constant-speed (or constant-curve), constant-flow, cycle-time (or dhw), temperature-range",
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

    Examples:
      alpha-hwr control set-mode constant-pressure 1.5
      alpha-hwr control set-mode constant-speed 2500
      alpha-hwr control set-mode constant-flow 0.5
    """
    # Normalize mode name
    normalized_mode = mode.lower().replace("-", "_")
    run_async(_control_set_mode(device, normalized_mode, setpoint))


@app.command("set-temperature")
def cmd_set_temperature(
    min_temp: float = typer.Option(
        ..., "--min", help="Minimum temperature (°C)"
    ),
    max_temp: float = typer.Option(
        ..., "--max", help="Maximum temperature (°C)"
    ),
    autoadapt: bool = typer.Option(
        True,
        "--autoadapt/--no-autoadapt",
        help="Enable/disable AutoAdapt flow adjustment",
    ),
    flow_limit: Optional[float] = typer.Option(
        None, "--flow-limit", "-f", help="Maximum flow limit in GPM (e.g. 1.5)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set temperature control mode (Mode 27).

    This mode maintains hot water temperature within the specified range.
    If AutoAdapt is enabled, flow is automatically adjusted (1-4 gpm).
    If a flow limit is provided, it will be applied to the pump.

    Examples:
      alpha-hwr control set-temperature --min 35 --max 39
      alpha-hwr control set-temperature --min 45 --max 50 --no-autoadapt --flow-limit 1.5
    """
    run_async(
        _control_set_temperature(
            device, min_temp, max_temp, autoadapt, flow_limit
        )
    )


@app.command("set-cycle-time")
def cmd_set_cycle_time(
    on_minutes: int = typer.Option(
        ..., "--on", help="Pump on duration (minutes)"
    ),
    off_minutes: int = typer.Option(
        ..., "--off", help="Pump off duration (minutes)"
    ),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set cycle time control mode (Mode 25 / DHW On/Off Control).

    This mode operates the pump in on/off cycles at configurable intervals,
    suitable for domestic hot water (DHW) recirculation applications.

    Examples:
      alpha-hwr control set-cycle-time --on 5 --off 15
      alpha-hwr control set-cycle-time --on 10 --off 20
    """
    run_async(_control_set_cycle_time(device, on_minutes, off_minutes))


@app.command("get-cycle-time")
def cmd_get_cycle_time(
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Get current cycle time configuration.

    Shows the current on/off cycle times for Mode 25 (DHW On/Off Control).

    Example:
      alpha-hwr control get-cycle-time
    """
    run_async(_control_get_cycle_time(device))


@app.command("set-flow-limit")
def cmd_set_flow_limit(
    limit_gpm: float = typer.Argument(..., help="Maximum flow limit in GPM"),
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Device address (from config if not specified)",
    ),
) -> None:
    """
    Set the maximum flow limit (GPM).

    Common limits by pipe diameter:
    - 1/2": 1.5 GPM
    - 3/4": 2.3 GPM
    - 1": 3.8 GPM

    Example:
      alpha-hwr control set-flow-limit 1.5
    """
    run_async(_control_set_flow_limit(device, limit_gpm))


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
            # Read current mode so the start command doesn't
            # accidentally switch the pump to a different mode.
            info = await control.get_mode()
            mode_val: int | None = None
            if info is not None:
                mode_val = int(info.control_mode)

            success = await control.start(mode=mode_val)

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
            # Read current mode so the stop command doesn't
            # accidentally switch the pump to a different mode.
            info = await control.get_mode()
            mode_val: int | None = None
            if info is not None:
                mode_val = int(info.control_mode)

            success = await control.stop(mode=mode_val)

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
                "constant_flow": control.set_constant_flow,
                "constant_speed": control.set_constant_speed,
                "constant_curve": control.set_constant_speed,  # Alias
                "proportional_pressure": control.set_proportional_pressure,
            }

            if mode in ("temperature_range", "temperature_control"):
                console.print(
                    "[yellow]Note: For temperature control, use 'set-temperature' command to specify min/max values.[/yellow]"
                )
                raise typer.Exit(1)

            if mode in ("cycle_time", "dhw"):
                console.print(
                    "[yellow]Note: For cycle time control, use 'set-cycle-time' command to specify on/off values.[/yellow]"
                )
                raise typer.Exit(1)

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
    device: Optional[str],
    min_temp: float,
    max_temp: float,
    autoadapt: bool,
    flow_limit: Optional[float] = None,
) -> None:
    """Internal async implementation of set-temperature command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Set temperature range control
            success = await control.set_temperature_range_control(
                min_temp, max_temp, autoadapt
            )

            if success:
                msg = f"Set Temperature Range Control to {min_temp}°C - {max_temp}°C (autoadapt={autoadapt})"
                if flow_limit is not None:
                    if await control.set_flow_limit(flow_limit):
                        msg += f" with {flow_limit} GPM flow limit"
                    else:
                        console.print(
                            "[yellow]Warning: Mode set, but flow limit failed[/yellow]"
                        )
                print_success(msg)
            else:
                console.print("[error]Failed to set temperature range[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to set temperature range")


async def _control_set_cycle_time(
    device: Optional[str], on_minutes: int, off_minutes: int
) -> None:
    """Internal async implementation of set-cycle-time command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Set cycle time control
            success = await control.set_cycle_time_control(
                on_minutes, off_minutes
            )

            if success:
                print_success(
                    f"Set Cycle Time Control to {on_minutes} min on, {off_minutes} min off"
                )
            else:
                console.print("[error]Failed to set cycle time control[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to set cycle time control")


async def _control_get_cycle_time(device: Optional[str]) -> None:
    """Internal async implementation of get-cycle-time command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Get cycle time config
            config = await control.get_cycle_time_config()

            if config:
                on_time, off_time = config
                console.print(
                    f"[success]Cycle Time: {on_time} min on, {off_time} min off[/success]"
                )
            else:
                console.print(
                    "[error]Failed to read cycle time configuration[/error]"
                )

    except Exception as e:
        handle_error(e, "Failed to read cycle time configuration")


async def _control_set_speed(
    device: Optional[str], setpoint: float, flow_limit: Optional[float] = None
) -> None:
    """Internal async implementation of set-speed command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Set speed
            success = await control.set_constant_speed(setpoint)

            if success:
                msg = f"Set Constant Speed to {setpoint} RPM"
                if flow_limit is not None:
                    if await control.set_flow_limit(flow_limit):
                        msg += f" with {flow_limit} GPM flow limit"
                    else:
                        console.print(
                            "[yellow]Warning: Speed set, but flow limit failed[/yellow]"
                        )
                print_success(msg)
            else:
                console.print("[error]Failed to set constant speed[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to set constant speed")


async def _control_set_flow_limit(
    device: Optional[str], limit_gpm: float
) -> None:
    """Internal async implementation of set-flow-limit command."""
    try:
        async with get_client(device) as client:
            control = require_service(client.control, "Control")
            # Set flow limit
            success = await control.set_flow_limit(limit_gpm)

            if success:
                print_success(f"Successfully set flow limit to {limit_gpm} GPM")
            else:
                console.print("[error]Failed to set flow limit[/error]")
                raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "Failed to set flow limit")
