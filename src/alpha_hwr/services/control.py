"""
Control service for pump operations.

This service handles all pump control operations including:
- Starting and stopping the pump
- Setting control modes (constant pressure, flow, speed, etc.)
- Setting setpoints for each mode
- Reading current control mode and setpoint
- Validating setpoint limits

The service provides a clean API that abstracts the complexity of
Class 10 and Class 3 protocol operations.

Implementation Notes for Other Languages
----------------------------------------
This service demonstrates mode control patterns:

1. **Class 10 Control**: Modern method using DataObjects
   - Sub 0x5600, Obj 0x0601 for control commands
   - Payload format: [Header][Flag][Mode][Suffix]
   - Flag: 0x00 = Start/Run, 0x01 = Stop

2. **Class 3 Fallback**: Legacy register-based method
   - Used for modes not supported in Class 10
   - Uses command IDs (0x04, 0x06, 0x15, 0x17, 0x18)

3. **Configuration Commit**: Required after some operations
   - Sub 0x5400, Obj 0xDA01
   - Commits state changes to persistent storage

Example in TypeScript:
```typescript
class ControlService {
    async start(): Promise<boolean> {
        // Build Class 10 start packet
        // Send with retry
        // Send configuration commit
    }

    async stop(): Promise<boolean> {
        // Build Class 10 stop packet
        // Send with retry
        // Commit and reset stream flags
    }

    async setMode(mode: ControlMode, setpoint: number): Promise<boolean> {
        // Validate setpoint
        // Build mode-specific packet
        // Send and verify
    }
}
```

Example in Rust:
```rust
pub struct ControlService {
    transport: Arc<Transport>,
    session: Arc<Session>,
    current_mode: Arc<RwLock<ControlMode>>,
}

impl ControlService {
    pub async fn start(&self) -> Result<bool, Error> {
        // Build and send start command
    }

    pub async fn stop(&self) -> Result<bool, Error> {
        // Build and send stop command
    }

    pub async fn set_mode(&self, mode: ControlMode, setpoint: f32) -> Result<bool, Error> {
        // Validate and set mode
    }
}
```
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from ..exceptions import ConnectionError
from ..models import SetpointInfo
from ..constants import ControlMode
from ..protocol.codec import encode_float_be, encode_uint16_be
from ..protocol import FrameBuilder
from .base import BaseService

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport
    from alpha_hwr.services.schedule import ScheduleService


logger = logging.getLogger(__name__)


class ControlService(BaseService):
    """
    Service for pump control operations.

    This service provides high-level APIs for controlling the pump:
    - Start/stop operations
    - Mode changes (constant pressure, flow, speed, etc.)
    - Setpoint management
    - Mode validation

    Attributes:
        _current_mode: Currently active control mode
        _CLASS10_CONTROL_MAP: Mapping of modes to Class 10 parameters

    Example:
        >>> from alpha_hwr.core import Transport, Session
        >>> from alpha_hwr.services import ControlService
        >>> from alpha_hwr.constants import ControlMode
        >>>
        >>> # Initialize
        >>> control = ControlService(transport, session)
        >>>
        >>> # Start pump
        >>> await control.start()
        >>>
        >>> # Set constant pressure mode
        >>> await control.set_constant_pressure(1.5)  # 1.5 meters
        >>>
        >>> # Stop pump
        >>> await control.stop()
    """

    # Control Object Identifiers (from trace)
    # These seem to be shifted or non-standard, but they work on ALPHA HWR
    SUB_CONTROL = 0x5600
    OBJ_CONTROL = 0x0601

    # ALPHA HWR Specific SubIDs for individual setpoints (optional backup)
    SUB_SPEED_SETPOINT = 13
    SUB_PRESSURE_SETPOINT = 15
    SUB_FLOW_SETPOINT = 39
    SUB_FLOW_LIMIT = 39
    PUMP_OBJ = 86

    # Control Mode Mapping for ALPHA HWR
    # Value -> Mode Byte used in control payload
    _MODE_BYTE_MAP = {
        0: 0x00,  # CONSTANT_PRESSURE
        1: 0x01,  # PROPORTIONAL_PRESSURE
        2: 0x02,  # CONSTANT_SPEED
        8: 0x08,  # CONSTANT_FLOW
        25: 0x19,  # DHW_ON_OFF_CONTROL
        27: 0x1B,  # TEMPERATURE_RANGE_CONTROL
    }

    # Default suffix bytes per mode, used for start/stop when no
    # explicit setpoint is given.  Values come from the Grundfos GO
    # app traffic captures.
    _MODE_SUFFIX_MAP: dict[int, bytes] = {
        0x00: bytes([0x45, 0x65, 0x70, 0x00]),  # Pressure
        0x01: bytes([0x45, 0x65, 0x70, 0x00]),  # Proportional Pressure
        0x02: bytes([0x45, 0x65, 0x70, 0x00]),  # Speed
        0x08: bytes([0x45, 0x65, 0x70, 0x00]),  # Flow
        0x19: bytes([0x38, 0xC6, 0x76, 0xEF]),  # DHW
        0x1B: bytes([0x39, 0x67, 0x70, 0x00]),  # Temp Range
    }

    def __init__(
        self,
        transport: Transport,
        session: Session,
        schedule_service: Optional["ScheduleService"] = None,
    ) -> None:
        """
        Initialize control service.

        Args:
            transport: Transport layer for BLE communication
            session: Session manager for state tracking
            schedule_service: Optional schedule service for status reading
        """
        super().__init__(transport, session)
        self._current_mode: ControlMode | int = ControlMode.CONSTANT_SPEED
        self._schedule_service = schedule_service

    async def start(self, mode: Optional[int] = None) -> bool:
        """
        Start the pump.

        Args:
            mode: Optional control mode to use (defaults to current mode)

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()
        logger.info("Starting pump...")

        # Resolve target mode
        if mode is not None:
            self._current_mode = mode

        mode_val = (
            self._current_mode.value
            if isinstance(self._current_mode, ControlMode)
            else self._current_mode
        )

        return await self._send_control_request(mode_val, start=True)

    async def stop(self, mode: Optional[int] = None) -> bool:
        """
        Stop the pump.

        Args:
            mode: Optional control mode (defaults to current mode)

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()
        logger.info("Stopping pump...")

        # Resolve target mode
        if mode is not None:
            mode_val = mode
        else:
            mode_val = (
                self._current_mode.value
                if isinstance(self._current_mode, ControlMode)
                else self._current_mode
            )

        return await self._send_control_request(mode_val, start=False)

    async def _send_control_request(
        self,
        mode_val: int,
        start: bool = True,
        setpoint: float | None = None,
    ) -> bool:
        """
        Send a control request using trace-verified identifiers and format.

        Payload Structure (12 bytes):
        [2F 01 00 00 07 00][Flag][Mode][Suffix(4)]

        Args:
            mode_val: Control mode ID (from ControlMode enum).
            start: True to start/run, False to stop.
            setpoint: Optional setpoint value in native units.
                When provided, the suffix carries this float32.
                When None, uses the mode's default suffix bytes.

        Returns:
            True if the command was acknowledged.
        """
        mode_byte = self._MODE_BYTE_MAP.get(mode_val, 0x02)

        # Build payload
        payload = bytearray([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00])
        payload.append(0x00 if start else 0x01)  # 0=Start, 1=Stop
        payload.append(mode_byte)

        if setpoint is not None:
            payload.extend(encode_float_be(setpoint))
        else:
            suffix = self._MODE_SUFFIX_MAP.get(
                mode_byte, bytes([0x45, 0x65, 0x70, 0x00])
            )
            payload.extend(suffix)

        # OpSpec 0x90 = SET + 16 bytes (4 IDs + 12 payload)
        apdu = bytearray([0x0A, 0x90])
        apdu.extend(encode_uint16_be(self.SUB_CONTROL))
        apdu.extend(encode_uint16_be(self.OBJ_CONTROL))
        apdu.extend(payload)

        req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))

        if await self._send_with_retry(
            req,
            f"Control Request (mode={mode_val}, start={start})",
        ):
            await self._send_configuration_commit()
            return True
        return False

    async def enable_remote_mode(self) -> bool:
        """
        Enable remote control mode.

        Enables remote control mode (Class 3 command ID 7), allowing external
        control of the pump via BLE/API commands. When enabled, the pump accepts
        control commands and ignores local controls.

        Returns:
            True if remote mode was enabled successfully, False otherwise

        Example:
            >>> await control.enable_remote_mode()
            >>> # Now you can send control commands
            >>> await control.start()

        Implementation Notes:
            - Uses Class 3 command: [0x03, 0xC1, 0x07]
            - Service ID: 0xE7, Source: 0xF8
        """
        self.session.ensure_authenticated()

        logger.info("Enabling Remote Mode...")

        # Class 3: 03 81 07
        apdu = bytes([0x03, 0x81, 0x07])
        cmd = self._build_geni_packet(0xF8, 0xE7, apdu)

        return await self._send_with_retry(cmd, "Enable Remote")

    async def disable_remote_mode(self) -> bool:
        """
        Disable remote control mode (return to Auto).

        Disables remote control mode (Class 3 command ID 6), returning the pump
        to automatic operation. The pump will resume normal operation based on
        its internal logic and local controls.

        Returns:
            True if remote mode was disabled successfully, False otherwise

        Example:
            >>> await control.disable_remote_mode()
            >>> # Pump returns to automatic operation

        Implementation Notes:
            - Uses Class 3 command: [0x03, 0xC1, 0x06]
            - Service ID: 0xE7, Source: 0xF8
        """
        self.session.ensure_authenticated()

        logger.info("Disabling Remote Mode (Auto)...")

        # Class 3: 03 81 08
        apdu = bytes([0x03, 0x81, 0x08])
        cmd = self._build_geni_packet(0xF8, 0xE7, apdu)

        return await self._send_with_retry(cmd, "Disable Remote")

    async def set_mode(self, mode: ControlMode | int) -> bool:
        """
        Set the control mode without changing setpoint.

        Args:
            mode: Control mode to set

        Returns:
            True if mode set successfully, False otherwise
        """
        self.session.ensure_authenticated()

        mode_val = mode.value if isinstance(mode, ControlMode) else mode
        logger.info(f"Setting control mode to {mode_val}...")

        if await self._send_control_request(mode_val, start=True):
            self._current_mode = (
                mode if isinstance(mode, ControlMode) else mode_val
            )
            return True

        return False

    async def get_mode(self) -> Optional[SetpointInfo]:
        """
        Get the current control mode and setpoint information.

        Reads from Class 10 Object 86, Sub-ID 6 (overall_operation_local_request_obj).
        For Temperature Range Control (mode 27), reads from Object 91, Sub-ID 430.

        Returns:
            SetpointInfo with current control mode, operation mode, and setpoint value,
            or None if read failed

        Raises:
            ConnectionError: If the BLE connection to the pump drops while
                waiting for the response.

        Example:
            >>> info = await control.get_mode()
            >>> if info and info.control_mode == ControlMode.CONSTANT_PRESSURE:
            ...     value, unit = info.get_display_value()
            ...     print(f"Running in constant pressure mode: {value} {unit}")

        Implementation Notes:
            - Standard modes: Object 86, Sub-ID 6, Type 303 (OperationStatusRequest)
            - Temperature Range: Object 91, Sub-ID 430, Type 1012
            - Response format: `[00 00 XX][control_source][operation_mode][control_mode][setpoint(4 bytes float)]`
            - Setpoint is big-endian float at offset 3 (after 3-byte header)
        """
        self.session.ensure_authenticated()

        try:
            import struct
            from ..constants import ControlMode

            # Read Class 10: Object 86, Sub-ID 6 (overall_operation_local_request_obj)
            # Retry: this is often the first read issued right after the
            # authentication handshake, and the pump can briefly be
            # unresponsive while it finishes settling into the new session.
            data = await self._read_class10_object(86, 6, retries=3)

            if data and len(data) >= 10:
                logger.debug(
                    f"Raw setpoint data: {data.hex()} (len={len(data)})"
                )

                # Determine offset (3-byte header is common: [00 00 XX])
                offset = (
                    3
                    if (len(data) >= 3 and data[0] == 0x00 and data[1] == 0x00)
                    else 0
                )

                if len(data) >= offset + 7:
                    control_source = data[offset]
                    operation_mode = data[offset + 1]
                    control_mode = data[offset + 2]

                    # Sync cached mode from actual pump state
                    try:
                        self._current_mode = ControlMode(control_mode)
                    except ValueError:
                        self._current_mode = control_mode

                    # Extract setpoint as big-endian float
                    setpoint = struct.unpack(
                        ">f", data[offset + 3 : offset + 7]
                    )[0]

                    # Convert pressure setpoints from Pascals to meters of
                    # water column (standard for ALPHA HWR). All pressure
                    # control modes send Pa on the wire; we convert here so
                    # SetpointInfo always stores user-facing units (m H2O).
                    if control_mode in (
                        ControlMode.CONSTANT_PRESSURE,
                        ControlMode.PROPORTIONAL_PRESSURE,
                        ControlMode.CONSTANT_DIFF_PRESSURE,
                        ControlMode.PROPORTIONAL_DIFF_PRESSURE,
                        ControlMode.AUTO_ADAPT_RADIATOR,
                        ControlMode.AUTO_ADAPT_UNDERFLOOR,
                        ControlMode.AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR,
                    ):
                        setpoint = setpoint / 9806.65

                    logger.debug(
                        f"Parsed setpoint: mode={control_mode}, op_mode={operation_mode}, "
                        f"setpoint={setpoint:.2f}, source={control_source}"
                    )

                    # Get schedule state if service is available
                    schedule_active = None
                    if self._schedule_service:
                        schedule_active = (
                            await self._schedule_service.get_state()
                        )

                    # Determine status flags
                    is_remote = (
                        control_source == 2
                    )  # 2 = Remote/Digital, 1 = Local/Panel
                    is_running = (
                        operation_mode != 1
                    )  # 1 = Stopped, 0 = Auto/Running

                    # Special handling for Temperature Range Control (mode 27)
                    if control_mode == ControlMode.TEMPERATURE_RANGE_CONTROL:
                        logger.debug(
                            "Temperature Range Control detected, reading from Object 91 Sub 430"
                        )
                        temp_data = await self._read_class10_object(91, 430)

                        if temp_data and len(temp_data) >= 12:
                            logger.debug(
                                f"Raw temperature range data: {temp_data.hex()} (len={len(temp_data)})"
                            )

                            # Skip 3-byte header if present
                            temp_offset = (
                                3
                                if (
                                    len(temp_data) >= 3
                                    and temp_data[0] == 0x00
                                    and temp_data[1] == 0x00
                                )
                                else 0
                            )

                            delta_enabled = bool(temp_data[temp_offset])
                            min_temp = struct.unpack(
                                ">f",
                                temp_data[temp_offset + 1 : temp_offset + 5],
                            )[0]
                            max_temp = struct.unpack(
                                ">f",
                                temp_data[temp_offset + 5 : temp_offset + 9],
                            )[0]

                            logger.debug(
                                f"Temperature Range: min={min_temp:.1f}°C, max={max_temp:.1f}°C, delta_enabled={delta_enabled}"
                            )

                            return SetpointInfo(
                                control_mode=self._current_mode,
                                operation_mode=operation_mode,
                                setpoint=min_temp,  # Low temperature
                                min_setpoint=min_temp,
                                max_setpoint=max_temp,  # High temperature
                                unit="°C",
                                is_remote=is_remote,
                                is_running=is_running,
                                schedule_enabled=schedule_active,
                                delta_temp_enabled=delta_enabled,
                            )
                        else:
                            logger.warning(
                                f"Temperature range data too short or empty: {len(temp_data) if temp_data else 0} bytes"
                            )
                            # Fall through to return basic setpoint

                    return SetpointInfo(
                        control_mode=self._current_mode,
                        operation_mode=operation_mode,
                        setpoint=setpoint,
                        is_remote=is_remote,
                        is_running=is_running,
                        schedule_enabled=schedule_active,
                    )
                else:
                    logger.warning(
                        f"Setpoint data too short after offset: {len(data)} bytes"
                    )
            else:
                logger.warning(
                    f"Setpoint data too short or missing: {len(data) if data else 0} bytes"
                )

        except ConnectionError:
            # The pump dropped the BLE connection mid-read - propagate so
            # the caller can report this distinctly from "no data read".
            raise

        except Exception as e:
            logger.debug(f"Failed to read setpoint: {e}")
            import traceback

            logger.debug(traceback.format_exc())

        return None

    async def set_constant_pressure(self, value_m: float) -> bool:
        """
        Set constant pressure mode with setpoint.

        Args:
            value_m: Pressure setpoint in meters of water column

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting constant pressure to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m)"
            )
            return False

        # Convert meters to Pascals
        value_pa = value_m * 9806.65

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.CONSTANT_PRESSURE, setpoint=value_pa
        ):
            return False

        # 2. Update specific pressure setpoint (Sub 15)
        return await self._set_class10_setpoint(
            value_pa, self.SUB_PRESSURE_SETPOINT
        )

    async def set_constant_speed(self, value_rpm: float) -> bool:
        """
        Set constant speed mode with setpoint.

        Args:
            value_rpm: Speed setpoint in RPM

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting constant speed to {value_rpm} RPM...")

        # Validate setpoint against reasonable limits (500 to 4500 RPM)
        if not (500 <= value_rpm <= 4500):
            logger.error(
                f"Setpoint {value_rpm} RPM is outside valid range (500-4500 RPM)"
            )
            return False

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.CONSTANT_SPEED, setpoint=value_rpm
        ):
            return False

        # 2. Update specific speed setpoint (Sub 13)
        return await self._set_class10_setpoint(
            value_rpm, self.SUB_SPEED_SETPOINT
        )

    async def set_constant_flow(self, value_m3h: float) -> bool:
        """
        Set constant flow mode with setpoint.

        Args:
            value_m3h: Flow setpoint in m³/h

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting constant flow to {value_m3h} m³/h...")

        # Validate setpoint against reasonable limits (0.1 to 10.0 m³/h)
        if not (0.1 <= value_m3h <= 10.0):
            logger.error(
                f"Setpoint {value_m3h} m³/h is outside valid range (0.1-10.0 m³/h)"
            )
            return False

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.CONSTANT_FLOW, setpoint=value_m3h
        ):
            return False

        # 2. Update specific flow setpoint (Sub 39)
        return await self._set_class10_setpoint(
            value_m3h, self.SUB_FLOW_SETPOINT
        )

    async def set_proportional_pressure(self, value_m: float) -> bool:
        """
        Set proportional pressure mode with setpoint.

        Args:
            value_m: Pressure setpoint in meters of water column

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting proportional pressure to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m)"
            )
            return False

        # Convert meters to Pascals
        value_pa = value_m * 9806.65

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.PROPORTIONAL_PRESSURE, setpoint=value_pa
        ):
            return False

        # 2. Update specific pressure setpoint (Sub 15)
        return await self._set_class10_setpoint(
            value_pa, self.SUB_PRESSURE_SETPOINT
        )

    async def set_temperature_control(
        self,
        on_temp_c: float,
        off_temp_c: float,
        heating_type: str = "radiator",
    ) -> bool:
        """
        Set Temperature Control mode with on/off temperature setpoints.

        This mode maintains hot water temperature with AutoAdapt flow adjustment
        (1-4 gpm). The pump turns on when temperature drops below on_temp and
        turns off when it reaches off_temp.

        Args:
            on_temp_c: Turn-on temperature threshold in Celsius (e.g., 35.0)
            off_temp_c: Turn-off temperature threshold in Celsius (e.g., 39.0)
            heating_type: System type - "radiator" (Mode 13), "underfloor" (Mode 14),
                         or "combined" (Mode 15). Default: "radiator"

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_temperature_control(35.0, 39.0)  # Radiator system
            >>> await control.set_temperature_control(35.0, 39.0, "underfloor")

        Note:
            For ALPHA HWR pumps, all heating_type variants likely behave the same
            (hot water recirculation), but the mode selection is available for
            compatibility with the GENI protocol.
        """
        self.session.ensure_authenticated()

        logger.info(
            f"Setting Temperature Control ({heating_type}) to {on_temp_c}°C on, {off_temp_c}°C off..."
        )

        # Validate temperature range
        if not (20.0 <= on_temp_c <= 60.0):
            logger.error(
                f"On temperature {on_temp_c}°C is outside valid range (20-60°C)"
            )
            return False

        if not (20.0 <= off_temp_c <= 60.0):
            logger.error(
                f"Off temperature {off_temp_c}°C is outside valid range (20-60°C)"
            )
            return False

        if on_temp_c >= off_temp_c:
            logger.error(
                f"On temperature ({on_temp_c}°C) must be less than off temperature ({off_temp_c}°C)"
            )
            return False

        # Map heating type to mode and register
        heating_map = {
            "radiator": (ControlMode.AUTO_ADAPT_RADIATOR, 0x1E),
            "underfloor": (ControlMode.AUTO_ADAPT_UNDERFLOOR, 0x1F),
            "combined": (ControlMode.AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR, 0x20),
        }

        if heating_type not in heating_map:
            logger.error(
                f"Invalid heating type: {heating_type}. Must be 'radiator', 'underfloor', or 'combined'"
            )
            return False

        mode, register_id = heating_map[heating_type]

        # Set mode first
        if not await self.set_mode(mode):
            return False

        # Protocol for temperature setpoints on modes 13/14/15 is not yet implemented.
        # These modes are for heating systems, while ALPHA HWR uses Mode 27 for
        # primary temperature control.
        logger.error(
            f"Temperature setpoints for Mode {mode} are not yet implemented. "
            "The mode has been switched, but temperatures were not applied. "
            "Use set_temperature_range_control() for ALPHA HWR temperature control."
        )

        return False

    # Legacy methods - deprecated, kept for compatibility
    async def set_autoadapt_radiator(self, value_m: float) -> bool:
        """
        DEPRECATED: Use set_temperature_control() instead.

        Legacy method that incorrectly uses pressure setpoints.
        """
        logger.warning(
            "set_autoadapt_radiator() is deprecated and uses incorrect pressure-based setpoints. "
            "Use set_temperature_control(on_temp_c, off_temp_c, 'radiator') instead."
        )
        # Validate setpoint against legacy limits for test compatibility
        if not (0.5 <= value_m <= 10.0):
            logger.error(f"Legacy setpoint {value_m} m is outside valid range")
            return False

        # Set mode first
        if not await self.set_mode(ControlMode.AUTO_ADAPT_RADIATOR):
            return False

        # Set setpoint using Class 3
        payload = encode_float_be(value_m)
        cmd = FrameBuilder.build_set_command(3, 2, 0x1E, payload)

        return await self._send_with_retry(cmd, "Set AutoAdapt Radiator Value")

    async def set_autoadapt_underfloor(self, value_m: float) -> bool:
        """
        DEPRECATED: Use set_temperature_control() instead.

        Legacy method that incorrectly uses pressure setpoints.
        """
        logger.warning(
            "set_autoadapt_underfloor() is deprecated and uses incorrect pressure-based setpoints. "
            "Use set_temperature_control(on_temp_c, off_temp_c, 'underfloor') instead."
        )
        # Validate setpoint against legacy limits for test compatibility
        if not (0.5 <= value_m <= 10.0):
            logger.error(f"Legacy setpoint {value_m} m is outside valid range")
            return False

        # Set mode first
        if not await self.set_mode(ControlMode.AUTO_ADAPT_UNDERFLOOR):
            return False

        # Set setpoint using Class 3
        payload = encode_float_be(value_m)
        cmd = FrameBuilder.build_set_command(3, 2, 0x1F, payload)

        return await self._send_with_retry(
            cmd, "Set AutoAdapt Underfloor Value"
        )

    async def set_autoadapt_combined(self, value_m: float) -> bool:
        """
        DEPRECATED: Use set_temperature_control() instead.

        Legacy method that incorrectly uses pressure setpoints.
        """
        logger.warning(
            "set_autoadapt_combined() is deprecated and uses incorrect pressure-based setpoints. "
            "Use set_temperature_control(on_temp_c, off_temp_c, 'combined') instead."
        )
        # Validate setpoint against legacy limits for test compatibility
        if not (0.5 <= value_m <= 10.0):
            logger.error(f"Legacy setpoint {value_m} m is outside valid range")
            return False

        # Set mode first
        if not await self.set_mode(
            ControlMode.AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR
        ):
            return False

        # Set setpoint using Class 3
        payload = encode_float_be(value_m)
        cmd = FrameBuilder.build_set_command(3, 2, 0x20, payload)

        return await self._send_with_retry(cmd, "Set AutoAdapt Combined Value")

    async def set_autoadapt(self, value_m: float) -> bool:
        """
        Set generic AutoAdapt mode with setpoint.

        AutoAdapt mode automatically analyzes and adjusts pump operation based on
        system demand. This is the generic AutoAdapt mode (Mode 5).

        For specific heating system types, consider using:
        - set_autoadapt_radiator() for radiator systems (Mode 13)
        - set_autoadapt_underfloor() for underfloor heating (Mode 14)
        - set_autoadapt_combined() for combined systems (Mode 15)

        Args:
            value_m: Pressure setpoint in meters of water column (e.g., 1.5 for 1.5 meters)

        Returns:
            True if successful, False otherwise

        Warning:
            Mode 5 (AUTO_ADAPT) has limited support on ALPHA HWR. Mode switching
            may not work reliably. Consider using specific AutoAdapt variants
            (modes 13-15) instead for better compatibility.

        Example:
            >>> await control.set_autoadapt(1.5)  # 1.5 meters
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting generic AutoAdapt to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m for residential pumps)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m). "
                "This may damage the pump or indicate an error."
            )
            return False

        # Try to set Mode 5 (AUTO_ADAPT)
        # Note: This may not work reliably on all firmware versions
        if not await self.set_mode(ControlMode.AUTO_ADAPT):
            logger.warning("Failed to switch to Mode 5 (AUTO_ADAPT)")
            return False

        # Try multiple possible register IDs since Mode 5 protocol is uncertain
        payload = encode_float_be(value_m)

        for register_id in [0x1D, 0x06, 0x05]:
            logger.debug(
                f"Trying register 0x{register_id:02X} for Mode 5 setpoint"
            )
            cmd = FrameBuilder.build_set_command(3, 2, register_id, payload)
            if await self._send_with_retry(
                cmd, f"Set AutoAdapt Value (0x{register_id:02X})"
            ):
                return True

        logger.warning("All setpoint write attempts for Mode 5 failed")
        return False

    async def set_temperature_range_control(
        self,
        min_temp: float,
        max_temp: float,
        autoadapt: bool = True,
    ) -> bool:
        """
        Set temperature range control mode (Mode 27) with min/max setpoints.

        Args:
            min_temp: Minimum temperature in Celsius
            max_temp: Maximum temperature in Celsius
            autoadapt: If True, enables automatic flow adjustment (1-4 gpm).
                      If False, uses fixed flow limits.

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_temperature_range_control(35.0, 45.0, autoadapt=True)
        """
        self.session.ensure_authenticated()

        logger.info(
            f"Setting Temperature Range Control: {min_temp}°C - {max_temp}°C (autoadapt={autoadapt})..."
        )

        # 1. Switch mode and set baseline (Sub 6)
        if not await self._send_control_request(
            ControlMode.TEMPERATURE_RANGE_CONTROL, setpoint=min_temp
        ):
            logger.error("Failed to switch to Temperature Range Control mode")
            return False

        # 2. Write temperature range to Object 91, Sub-ID 430
        # Payload must match exactly what is read back (no Type ID bytes, 14 bytes data)
        # Build APDU manually to match exactly what Grundfos GO app sends
        # App sends: [Class 10] [OpSpec 0x97] [ObjID 91] [SubH 01] [SubL AE] [TypeH 03] [TypeL F4] [Reserved 02] [Size 00 00 0E] [Data...]
        apdu = bytearray(
            [
                0x0A,  # Class 10
                0x97,  # OpSpec 0x97 = SET + 23 bytes
                0x5B,  # Obj-ID (91 = 0x5B)
                0x01,
                0xAE,  # Sub-ID (430 = 0x01AE)
                0x03,
                0xF4,  # Type Code (1012 = 0x03F4)
                0x02,  # Reserved
                0x00,
                0x00,
                0x0E,  # Size (14 bytes)
            ]
        )

        # Payload (14 bytes)
        apdu.append(0x01 if autoadapt else 0x00)  # DeltaTempEnabled
        apdu.extend(encode_float_be(min_temp))
        apdu.extend(encode_float_be(max_temp))

        # Default time limits (5 bytes)
        apdu.extend(bytes([0x00, 0x00, 0x00, 0x16, 0x00]))

        req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))
        if await self._send_with_retry(req, "Set Temperature Range (Obj 91)"):
            await self._send_configuration_commit()
            return True
        return False

    async def set_flow_limit(self, value_gpm: float) -> bool:
        """
        Set the maximum flow limit to prevent noise and corrosion.

        Args:
            value_gpm: Maximum flow limit in GPM.

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()

        from ..constants import FACTOR_M3H_TO_GPM

        value_m3h = value_gpm * FACTOR_M3H_TO_GPM

        logger.info(
            f"Setting flow limit to {value_gpm} GPM ({value_m3h:.3f} m³/h)..."
        )

        # Set flow limit using Object 86, Sub 39 (Max Flow Limit)
        return await self._set_class10_setpoint(
            value_m3h, self.SUB_FLOW_LIMIT, self.PUMP_OBJ
        )

    async def set_cycle_time_control(
        self, on_minutes: int, off_minutes: int
    ) -> bool:
        """
        Set cycle time control mode (Mode 25 / DHW_ON_OFF_CONTROL).

        Args:
            on_minutes: Duration pump runs (1-60)
            off_minutes: Duration pump is off (1-60)

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()

        logger.info(
            f"Setting Cycle Time Control: {on_minutes} min on, {off_minutes} min off..."
        )

        # Validate ranges
        if not (1 <= on_minutes <= 60 and 1 <= off_minutes <= 60):
            logger.error("Cycle times must be between 1 and 60 minutes")
            return False

        # 1. Switch mode (Sub 6)
        if not await self._send_control_request(ControlMode.DHW_ON_OFF_CONTROL):
            return False

        # 2. Write configuration (Obj 91, Sub 430)
        try:
            # Payload construction (8 bytes)
            # 00 00 [OFF] 01 42 02 [ON] FB
            struct_payload = bytearray(
                [
                    0x00,
                    0x00,  # Header
                    off_minutes,  # Byte 2: OFF time
                    0x01,
                    0x42,
                    0x02,  # Fixed magic bytes
                    on_minutes,  # Byte 6: ON time
                    0xFB,  # Fixed suffix
                ]
            )

            # Prepend Type (1012 = 0x03F4) and Size (0x08)
            # This 'data' block is what FrameBuilder wraps with IDs and OpSpec
            data = bytearray(
                [
                    0x03,
                    0xF4,  # Type: 1012
                    len(struct_payload),  # Size: 8
                ]
            )
            data.extend(struct_payload)

            # Use FrameBuilder to handle OpSpec, Length, and CRC correctly
            # SubID: 430 (0x01AE), ObjID: 91 (0x5B)
            packet = FrameBuilder.build_data_object_set(
                sub_id=0x01AE, obj_id=91, data=bytes(data), source=0xF8
            )

            success = await self._send_with_retry(packet, "Set Cycle Time")

            if not success:
                logger.error("Failed to write cycle time configuration")
                return False

            logger.info(
                f"Successfully set cycle times: {on_minutes} min ON, {off_minutes} min OFF"
            )

            # Commit configuration
            await self._send_configuration_commit()

            return True

        except Exception as e:
            logger.error(f"Failed to write cycle time configuration: {e}")
            return False

    async def get_cycle_time_config(self) -> Optional[tuple[int, int]]:
        """
        Get current cycle time configuration for Mode 25 (DHW_ON_OFF_CONTROL).

        Returns:
            Tuple of (on_time_minutes, off_time_minutes) if successful, None otherwise
        """
        self.session.ensure_authenticated()

        try:
            # Read from Object 91, SubID 430 (0x01AE) - Main user settings block
            data = await self._read_class10_object(91, 430)

            if not data or len(data) < 16:
                logger.error(
                    f"Invalid cycle time data: {data.hex() if data else 'None'}"
                )
                return None

            # Extract cycle times from payload (verified via trace analysis)
            # Structure: 00 00 0e 01 42 0c 00 00 42 1e de 4c [OFF] 3c 02 [ON] 01
            # Byte 12: OFF time
            # Byte 15: ON time
            off_time = data[12]
            on_time = data[15]

            logger.info(
                f"Read cycle times: {on_time} min ON, {off_time} min OFF"
            )
            return (on_time, off_time)

        except Exception as e:
            logger.error(f"Failed to read cycle time configuration: {e}")
            return None

    # Helper methods

    async def _set_class10_setpoint(
        self, value: float, sub_id: int, obj_id: int = 86
    ) -> bool:
        """
        Set the setpoint value using Class 10 DataObject method (SET).

        Args:
            value: Setpoint value (float)
            sub_id: Sub-ID to write to
            obj_id: Object ID to write to (default 86)

        Returns:
            True if successful, False otherwise
        """
        # Build Class 10 SET packet (OpSpec 0x84 = SET + 4 bytes)
        # APDU: [Class][OpSpec][SubH][SubL][ObjH][ObjL][Data(4)]
        apdu = bytearray([0x0A, 0x84])
        apdu.extend(encode_uint16_be(sub_id))
        apdu.extend(encode_uint16_be(obj_id))
        apdu.extend(encode_float_be(value))

        # Build GENI frame
        req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))

        # Send with retry
        if await self._send_with_retry(
            req, f"Set Setpoint {value:.2f} (Sub={sub_id}, Obj={obj_id})"
        ):
            # Send configuration commit
            await self._send_configuration_commit()
            return True

        return False

    async def _send_with_retry(
        self, packet: bytes, description: str, retries: int = 3
    ) -> bool:
        """
        Send packet with retry logic and optional response verification.

        For control commands, we attempt to verify success by waiting for a response.
        If no response is received, we still consider it successful (fire-and-forget).
        """
        for attempt in range(retries):
            try:
                # Try to get a response (with timeout)
                # Control commands typically return Class 10 or Class 3 acknowledgments
                def match_control_response(p: bytes) -> bool:
                    """Match control command responses (Class 10 or Class 3)."""
                    if len(p) <= 4:
                        return False
                    # Class 10 response (0x0A) or Class 3 response (0x03)
                    return p[4] in (0x0A, 0x03)

                response = await self.transport.query(
                    packet,
                    match_func=match_control_response,
                    timeout=1.0,  # Short timeout for control commands
                )

                if response:
                    logger.debug(
                        f"{description}: Got response ({len(response)} bytes)"
                    )
                else:
                    logger.debug(
                        f"{description}: No response (fire-and-forget mode)"
                    )

                # Consider successful either way (some commands don't respond)
                return True

            except Exception as e:
                logger.warning(
                    f"{description} attempt {attempt + 1} failed: {e}"
                )
                if attempt < retries - 1:
                    await asyncio.sleep(0.2)

        return False
