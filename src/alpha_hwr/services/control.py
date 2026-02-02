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

from ..models import SetpointInfo
from ..constants import ControlMode
from ..protocol.codec import encode_float_be
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

    # Control Mode Payloads (Class 10, Sub 0x5600, Obj 0x0601)
    # Payload format: 2F 01 00 00 07 00 [Flag] [Mode] [Suffix bytes]
    # Flag: 00=Start/Run, 01=Stop
    # Suffix is invariant to Flag
    # Map: ControlMode.Value -> (ModeByte, SuffixBytes)
    # Based on protocol specification
    _CLASS10_CONTROL_MAP = {
        0: (0x00, bytes([0x45, 0x65, 0x70, 0x00])),  # Constant Pressure
        2: (0x02, bytes([0x45, 0x65, 0x70, 0x00])),  # Constant Speed
        13: (0x0D, bytes([0x45, 0x65, 0x70, 0x00])),  # AutoAdapt Radiator
        14: (0x0E, bytes([0x45, 0x65, 0x70, 0x00])),  # AutoAdapt Underfloor
        15: (0x0F, bytes([0x45, 0x65, 0x70, 0x00])),  # AutoAdapt Combined
        25: (0x19, bytes([0x38, 0xC6, 0x70, 0x00])),  # DHW
        27: (0x1B, bytes([0x39, 0x67, 0x70, 0x00])),  # Temp Range
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

        Sends the start command using Class 10 DataObject method.
        Optionally switches to a different mode before starting.

        Args:
            mode: Optional control mode to use (defaults to current mode)

        Returns:
            True if pump started successfully, False otherwise

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> # Start with current mode
            >>> await control.start()
            >>>
            >>> # Start with specific mode
            >>> await control.start(mode=ControlMode.CONSTANT_PRESSURE)

        Implementation Notes:
            - Uses Class 10 Sub 0x5600, Obj 0x0601
            - Sends configuration commit after start
            - Requires authentication
            - Uses transaction lock to prevent conflicts
        """
        self.session.ensure_authenticated()

        logger.info("Starting pump...")

        # Resolve target mode
        if mode is not None:
            mode_val = mode
            self._current_mode = mode
        else:
            mode_val = (
                self._current_mode.value
                if isinstance(self._current_mode, ControlMode)
                else self._current_mode
            )

        if mode_val in self._CLASS10_CONTROL_MAP:
            mode_byte, suffix = self._CLASS10_CONTROL_MAP[mode_val]

            # Build payload: [Header] [00=Run] [Mode] [Suffix]
            payload = bytearray(
                [0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, mode_byte]
            )
            payload.extend(suffix)

            # Build Class 10 SET packet
            apdu = bytearray([0x0A, 0x90, 0x56, 0x00, 0x06, 0x01])
            apdu.extend(payload)

            # Build GENI frame
            req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))

            # Send with retry
            if await self._send_with_retry(req, "Start Pump"):
                # Send configuration commit (required to persist state)
                await self._send_configuration_commit()
                logger.info("Pump started successfully")
                return True
        else:
            logger.error(f"Mode {mode_val} not supported for Class 10 start")

        return False

    async def stop(self, mode: Optional[int] = None) -> bool:
        """
        Stop the pump.

        Sends the stop command using Class 10 DataObject method.

        Args:
            mode: Optional control mode (defaults to current mode)

        Returns:
            True if pump stopped successfully, False otherwise

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> await control.stop()

        Implementation Notes:
            - Uses Class 10 Sub 0x5600, Obj 0x0601
            - Sets Flag=0x01 for stop operation
            - Sends configuration commit
            - Resets telemetry stream flags (stream may pause when stopped)
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

        if mode_val in self._CLASS10_CONTROL_MAP:
            mode_byte, suffix = self._CLASS10_CONTROL_MAP[mode_val]

            # Build payload: [Header] [01=Stop] [Mode] [Suffix]
            payload = bytearray(
                [0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x01, mode_byte]
            )
            payload.extend(suffix)

            # Build Class 10 SET packet
            apdu = bytearray([0x0A, 0x90, 0x56, 0x00, 0x06, 0x01])
            apdu.extend(payload)

            # Build GENI frame
            req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))

            # Send with retry
            if await self._send_with_retry(req, "Stop Pump"):
                # Send configuration commit
                await self._send_configuration_commit()
                logger.info("Pump stopped successfully")

                # Note: Telemetry stream may pause when stopped
                # Services should re-enable polling if needed

                return True
        else:
            logger.error(f"Mode {mode_val} not supported for Class 10 stop")

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

        # Class 3: 03 C1 07
        apdu = bytes([0x03, 0xC1, 0x07])
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

        # Class 3: 03 C1 06
        apdu = bytes([0x03, 0xC1, 0x06])
        cmd = self._build_geni_packet(0xF8, 0xE7, apdu)

        return await self._send_with_retry(cmd, "Disable Remote")

    async def set_mode(self, mode: ControlMode | int) -> bool:
        """
        Set the control mode without changing setpoint.

        Args:
            mode: Control mode to set

        Returns:
            True if mode set successfully, False otherwise

        Example:
            >>> await control.set_mode(ControlMode.CONSTANT_PRESSURE)
            >>> await control.set_mode(ControlMode.CONSTANT_SPEED)

        Implementation Notes:
            - Tries Class 10 method first (preferred)
            - Falls back to Class 3 for unsupported modes
            - Updates internal mode tracking
        """
        self.session.ensure_authenticated()

        mode_val = mode.value if isinstance(mode, ControlMode) else mode
        logger.info(f"Setting control mode to {mode_val}...")

        # Try Class 10 first
        if mode_val in self._CLASS10_CONTROL_MAP:
            mode_byte, suffix = self._CLASS10_CONTROL_MAP[mode_val]

            # Build payload: [Header] [00=Run] [Mode] [Suffix]
            payload = bytearray(
                [0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, mode_byte]
            )
            payload.extend(suffix)

            # Build Class 10 SET packet
            apdu = bytearray([0x0A, 0x90, 0x56, 0x00, 0x06, 0x01])
            apdu.extend(payload)

            req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))

            if await self._send_with_retry(req, f"Set Mode {mode_val}"):
                self._current_mode = (
                    mode if isinstance(mode, ControlMode) else mode_val
                )
                return True

        # Fallback to Class 3
        logger.debug(f"Mode {mode_val} not in Class 10 map, trying Class 3...")

        CMD_MAP = {
            0: 0x18,  # Const Pressure
            1: 0x17,  # Prop Pressure
            2: 0x04,  # Const Speed
            5: 0x06,  # AutoAdapt (generic)
            8: 0x15,  # Const Flow
            13: 0x1E,  # AutoAdapt Radiator
            14: 0x1F,  # AutoAdapt Underfloor
            15: 0x20,  # AutoAdapt Combined (Radiator + Underfloor)
        }

        cmd_id = CMD_MAP.get(mode_val)
        if cmd_id is None:
            logger.error(f"Unsupported control mode: {mode_val}")
            return False

        cmd = FrameBuilder.build_command_info(3, cmd_id)
        if await self._send_with_retry(cmd, f"Set Mode {mode_val} (Class 3)"):
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
            data = await self._read_class10_object(86, 6)

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

                    # Extract setpoint as big-endian float
                    setpoint = struct.unpack(
                        ">f", data[offset + 3 : offset + 7]
                    )[0]

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
                                control_mode=control_mode,
                                operation_mode=operation_mode,
                                setpoint=min_temp,  # Low temperature
                                min_setpoint=min_temp,
                                max_setpoint=max_temp,  # High temperature
                                unit="°C",
                                is_remote=is_remote,
                                is_running=is_running,
                                schedule_enabled=schedule_active,
                            )
                        else:
                            logger.warning(
                                f"Temperature range data too short or empty: {len(temp_data) if temp_data else 0} bytes"
                            )
                            # Fall through to return basic setpoint

                    return SetpointInfo(
                        control_mode=control_mode,
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

        Example:
            >>> await control.set_constant_pressure(1.5)  # 1.5 meters

        Implementation Notes:
            - Converts meters to Pascals (value_m * 9806.65)
            - Validates against min/max limits
            - Uses Class 3 register write
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting constant pressure to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m for residential pumps)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m). "
                "This may damage the pump or indicate an error."
            )
            return False

        # Set mode first
        if not await self.set_mode(ControlMode.CONSTANT_PRESSURE):
            return False

        # Set setpoint using Class 3
        payload = encode_float_be(value_m)
        cmd = FrameBuilder.build_set_command(3, 2, 0x18, payload)

        return await self._send_with_retry(cmd, "Set Constant Pressure Value")

    async def set_constant_speed(self, value_rpm: float) -> bool:
        """
        Set constant speed mode with setpoint.

        Args:
            value_rpm: Speed setpoint in RPM

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_constant_speed(2500)  # 2500 RPM
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting constant speed to {value_rpm} RPM...")

        # Validate setpoint against reasonable limits (500 to 4500 RPM for residential pumps)
        if not (500 <= value_rpm <= 4500):
            logger.error(
                f"Setpoint {value_rpm} RPM is outside valid range (500-4500 RPM). "
                "This may damage the pump or indicate an error."
            )
            return False

        # Set mode first
        if not await self.set_mode(ControlMode.CONSTANT_SPEED):
            return False

        # Set setpoint using Class 3
        payload = encode_float_be(value_rpm)
        cmd = FrameBuilder.build_set_command(3, 2, 0x04, payload)

        return await self._send_with_retry(cmd, "Set Constant Speed Value")

    async def set_constant_flow(self, value_m3h: float) -> bool:
        """
        Set constant flow mode with setpoint.

        Args:
            value_m3h: Flow setpoint in m³/h

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_constant_flow(2.5)  # 2.5 m³/h
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting constant flow to {value_m3h} m³/h...")

        # Validate setpoint against reasonable limits (0.1 to 10.0 m³/h for residential pumps)
        if not (0.1 <= value_m3h <= 10.0):
            logger.error(
                f"Setpoint {value_m3h} m³/h is outside valid range (0.1-10.0 m³/h). "
                "This may damage the pump or indicate an error."
            )
            return False

        # Set mode first
        if not await self.set_mode(ControlMode.CONSTANT_FLOW):
            return False

        # Set setpoint using Class 3
        payload = encode_float_be(value_m3h)
        cmd = FrameBuilder.build_set_command(3, 2, 0x15, payload)

        return await self._send_with_retry(cmd, "Set Constant Flow Value")

    async def set_proportional_pressure(self, value_m: float) -> bool:
        """
        Set proportional pressure mode with setpoint.

        In Proportional Pressure mode, the pump adjusts pressure based on flow,
        maintaining a linear relationship between flow and pressure.

        Args:
            value_m: Pressure setpoint in meters of water column (e.g., 1.0 for 1 meter)

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_proportional_pressure(1.5)  # 1.5 meters
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting proportional pressure to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m for residential pumps)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m). "
                "This may damage the pump or indicate an error."
            )
            return False

        # Set mode first
        if not await self.set_mode(ControlMode.PROPORTIONAL_PRESSURE):
            return False

        # Set setpoint using Class 3
        payload = encode_float_be(value_m)
        cmd = FrameBuilder.build_set_command(3, 2, 0x17, payload)

        return await self._send_with_retry(
            cmd, "Set Proportional Pressure Value"
        )

    async def set_autoadapt_radiator(self, value_m: float) -> bool:
        """
        Set AutoAdapt Radiator mode with setpoint.

        AutoAdapt Radiator mode automatically adjusts pump operation for
        radiator heating systems based on system demand.

        Args:
            value_m: Pressure setpoint in meters of water column (e.g., 3.0 for 3 meters)

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_autoadapt_radiator(3.0)  # 3 meters
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting AutoAdapt Radiator to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m for residential pumps)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m). "
                "This may damage the pump or indicate an error."
            )
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
        Set AutoAdapt Underfloor mode with setpoint.

        AutoAdapt Underfloor mode automatically adjusts pump operation for
        underfloor heating systems based on system demand.

        Args:
            value_m: Pressure setpoint in meters of water column (e.g., 2.5 for 2.5 meters)

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_autoadapt_underfloor(2.5)  # 2.5 meters
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting AutoAdapt Underfloor to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m for residential pumps)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m). "
                "This may damage the pump or indicate an error."
            )
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
        Set AutoAdapt Combined mode with setpoint.

        AutoAdapt Combined mode automatically adjusts pump operation for
        combined radiator and underfloor heating systems based on system demand.

        Args:
            value_m: Pressure setpoint in meters of water column (e.g., 2.0 for 2 meters)

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_autoadapt_combined(2.0)  # 2 meters
        """
        self.session.ensure_authenticated()

        logger.info(f"Setting AutoAdapt Combined to {value_m} m...")

        # Validate setpoint against reasonable limits (0.5m to 10m for residential pumps)
        if not (0.5 <= value_m <= 10.0):
            logger.error(
                f"Setpoint {value_m} m is outside valid range (0.5-10.0 m). "
                "This may damage the pump or indicate an error."
            )
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
        self, min_temp: float, max_temp: float
    ) -> bool:
        """
        Set temperature range control mode (Mode 27) with min/max setpoints.

        Args:
            min_temp: Minimum temperature in Celsius
            max_temp: Maximum temperature in Celsius

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_temperature_range_control(35.0, 45.0)
        """
        self.session.ensure_authenticated()

        logger.info(
            f"Setting Temperature Range Control: {min_temp}°C - {max_temp}°C..."
        )

        # 1. Switch to Mode 27
        if not await self.set_mode(ControlMode.TEMPERATURE_RANGE_CONTROL):
            logger.error("Failed to switch to Temperature Range Control mode")
            return False

        # 2. Write temperature range to Object 91, Sub-ID 430
        # Payload format (Type 1012):
        # [DeltaTempEnabled(1)][MinTemp(4)][MaxTemp(4)][TimeLimits(4)]
        # Total size usually 13 bytes including 3-byte header

        # Build 9-byte structure data (without header)
        struct_data = bytearray()
        struct_data.append(0x01)  # DeltaTempEnabled = True
        struct_data.extend(encode_float_be(min_temp))
        struct_data.extend(encode_float_be(max_temp))

        # Add 4 bytes of time limits (typically seen as 05 3C 01 1E in captures)
        struct_data.extend(bytes([0x05, 0x3C, 0x01, 0x1E]))

        # Build APDU: [Class][OpSpec][Obj][SubH][SubL][Reserved][Type(3)][Size(2)][Data...]
        # Using OpSpec 0xB3 (OpSpec 5, Length 19) similar to schedules
        apdu = bytearray(
            [
                0x0A,
                0xB3,
                91,  # Object 91
                0x01,
                0xAE,  # Sub-ID 430 (0x01AE)
                0x00,  # Reserved
                0xF4,
                0x03,
                0x00,  # Type 1012 header (0x03F4 = 1012)
                0x00,
                0x09,  # Size = 9 bytes
            ]
        )
        apdu.extend(struct_data)

        success = await self._send_with_retry(
            self._build_geni_packet(0xF8, 0xE7, bytes(apdu)),
            "Set Temperature Range",
        )

        if success:
            await self._send_configuration_commit()

        return success

    # Helper methods

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

    async def _send_configuration_commit(self) -> None:
        """Send configuration commit packet."""
        # Sub 0x5400, Obj 0xDA01
        conf_apdu = bytearray.fromhex(
            "0A9354000100DA0100000A02050005000100000000"
        )
        cmd = self._build_geni_packet(0xF8, 0xE7, bytes(conf_apdu))
        await self.transport.write(cmd)
        if not getattr(self.session, "fast_mode", False):
            await asyncio.sleep(0.2)
        logger.debug("Configuration commit sent")
