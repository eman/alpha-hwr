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
import math
from typing import TYPE_CHECKING, ClassVar

from ..constants import ControlMode
from ..exceptions import READ_ERRORS, ConnectionError
from ..models import SetpointInfo, WriteCommand, WriteResult
from ..protocol import FrameBuilder
from ..protocol.codec import (
    decode_float_be,
    encode_float_be,
    encode_uint16_be,
)
from ..protocol.matcher import Command
from .base import BaseService

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport
    from alpha_hwr.services.schedule import ScheduleService
    from alpha_hwr.services.write_operation import WriteOperationService


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
        >>> from alpha_hwr.core import Transport, Session  # doctest: +SKIP
        >>> from alpha_hwr.services import ControlService  # doctest: +SKIP
        >>> from alpha_hwr.constants import ControlMode  # doctest: +SKIP
        >>>
        >>> # Initialize
        >>> control = ControlService(transport, session)  # doctest: +SKIP
        >>>
        >>> # Start pump
        >>> await control.start()  # doctest: +SKIP
        >>>
        >>> # Set constant pressure mode
        >>> await control.set_constant_pressure(1.5)  # 1.5 meters  # doctest: +SKIP
        >>>
        >>> # Stop pump
        >>> await control.stop()  # doctest: +SKIP
    """

    # Control Object Identifiers (from trace)
    # These seem to be shifted or non-standard, but they work on ALPHA HWR
    SUB_CONTROL = 0x5600

    #: Object 86 sub-id 6, ``overall_operation_local_request``. One fused
    #: write carrying run state, control mode *and* setpoint together, so
    #: anything sent through it necessarily asserts all three.
    OBJ_CONTROL = 0x0601

    #: Object 86 sub-id 10, ``overall_control_mode_local_request``. Changes
    #: only the control mode: its payload carries ``operation_mode = NoCmd``
    #: and ``set_point = NaN``, so the run state and every mode's stored
    #: setpoint are left alone. Reading this object back from the pump
    #: returns exactly those sentinels, which is how it was confirmed.
    OBJ_MODE_REQUEST = 0x0A01

    #: ``set_point`` value meaning "keep whatever is stored". Big-endian
    #: IEEE-754 NaN. The alternative - the per-mode default suffix below -
    #: encodes 3671.0 for every scalar mode, which the pump stores durably.
    SETPOINT_KEEP = bytes([0x7F, 0xFF, 0xFF, 0xFF])

    #: ``operation_mode`` value meaning "leave the run state alone".
    OPERATION_MODE_NO_CMD = 0x06

    #: Bounds accepted for a temperature-range setpoint, in degrees C.
    #:
    #: These are a client-side guard, and measurement says they are the
    #: *only* guard: the pump validates this object not at all. Offered
    #: -10 C and 120 C it stored both, unchanged - no clamping, no
    #: rejection, nothing. That is the opposite of the setpoint objects,
    #: which clamp silently.
    #:
    #: So the range here is a judgement about what a hot-water system can
    #: mean, not a mirror of firmware behaviour. The two entry points used
    #: to disagree about it (20-60 here, 20-70 in the write layer), which
    #: made the same request valid or invalid depending on which one the
    #: caller happened to reach for.
    TEMP_RANGE_MIN_C = 20.0
    TEMP_RANGE_MAX_C = 70.0

    #: Flow setpoints are stored in SI m3/s while the API speaks m3/h.
    #: Writing m3/h straight through put a commanded 2.5 on the wire as
    #: 2.5 m3/s - 9000 m3/h - which the pump rejected as out of range,
    #: keeping its old value and making the register look frozen. Note
    #: this applies to *setpoints* only: telemetry flow is already m3/h.
    SECONDS_PER_HOUR = 3600.0

    #: Modes whose setpoint is a single scalar the fused control object
    #: would overwrite. For these, an absent setpoint must be sent as
    #: SETPOINT_KEEP rather than falling back to the default suffix.
    _SCALAR_SETPOINT_MODES: ClassVar[frozenset[int]] = frozenset(
        {0x00, 0x01, 0x02, 0x08}
    )

    # ALPHA HWR Specific SubIDs for individual setpoints (optional backup)
    SUB_SPEED_SETPOINT = 13
    SUB_PRESSURE_SETPOINT = 15
    SUB_FLOW_SETPOINT = 39
    PUMP_OBJ = 86

    #: Where the pump publishes each scalar mode's setpoint range.
    #:
    #: These are the type 301 version 1 "factory config" objects - the same
    #: ones the Grundfos GO app's setpoint slider binds to. Each carries a
    #: 28-byte struct of seven floats, of which the first three are
    #: default, minimum and maximum.
    #:
    #: All four answer with the *same* type code, so a reply cannot say
    #: which sub-id it came from. See :meth:`read_setpoint_ranges` for what
    #: that forces.
    _RANGE_SUB_IDS: ClassVar[dict[int, int]] = {
        ControlMode.CONSTANT_SPEED: 13,
        ControlMode.CONSTANT_PRESSURE: 15,
        ControlMode.PROPORTIONAL_PRESSURE: 17,
        ControlMode.CONSTANT_FLOW: 39,
    }

    #: What to divide or multiply the pump's native units by to reach the
    #: units this client speaks, per mode.
    #:
    #: Pressure is stored in Pascals and reported in metres of head; flow
    #: is stored in SI m3/s and reported in m3/h. Speed is native RPM.
    _RANGE_SCALE: ClassVar[dict[int, float]] = {
        ControlMode.CONSTANT_SPEED: 1.0,
        ControlMode.CONSTANT_PRESSURE: 1.0 / 9806.65,
        ControlMode.PROPORTIONAL_PRESSURE: 1.0 / 9806.65,
        ControlMode.CONSTANT_FLOW: 3600.0,
    }

    # Control Mode Mapping for ALPHA HWR
    # Value -> Mode Byte used in control payload
    # Generic AutoAdapt (mode 5) is deliberately absent: the pump has no
    # wire byte for it. It used to fall through to the default, which was
    # Constant Speed - so asking for AutoAdapt put the pump into a
    # different mode and reported success.
    _MODE_BYTE_MAP: ClassVar[dict[int, int]] = {
        0: 0x00,  # CONSTANT_PRESSURE
        1: 0x01,  # PROPORTIONAL_PRESSURE
        2: 0x02,  # CONSTANT_SPEED
        8: 0x08,  # CONSTANT_FLOW
        13: 0x0D,  # AUTO_ADAPT_RADIATOR
        14: 0x0E,  # AUTO_ADAPT_UNDERFLOOR
        15: 0x0F,  # AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR
        25: 0x19,  # DHW_ON_OFF_CONTROL
        27: 0x1B,  # TEMPERATURE_RANGE_CONTROL
    }

    # Default suffix bytes per mode, from the Grundfos GO app captures.
    #
    # Only the two non-scalar modes use these. The four scalar modes are
    # deliberately absent: their entry here was bytes([0x45, 0x65, 0x70,
    # 0x00]), which decodes to exactly 3671.0, and sending it wrote that
    # value over whatever setpoint the mode actually had. It is not an
    # inert placeholder - 3671.0 appears verbatim in the pump's own speed
    # limits block - so those modes send SETPOINT_KEEP instead.
    _MODE_SUFFIX_MAP: ClassVar[dict[int, bytes]] = {
        0x19: bytes([0x38, 0xC6, 0x76, 0xEF]),  # DHW
        0x1B: bytes([0x39, 0x67, 0x70, 0x00]),  # Temp Range
    }

    def __init__(
        self,
        transport: Transport,
        session: Session,
        schedule_service: ScheduleService | None = None,
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
        self._writes: WriteOperationService | None = None

        # What the pump holds, read by sync_cache(). Setpoints are keyed by
        # mode: one shared slot leaks a value from one mode into another
        # under different units.
        self._cache_valid = False
        self._cached_mode: ControlMode | int | None = None
        self._cached_enabled: bool | None = None
        self._cached_temp_range: tuple[float, float, bool] | None = None
        self._cached_cycle: tuple[int, int] | None = None
        self._cached_setpoints: dict[int, float] = {}

        # Per-mode setpoint bounds as the pump publishes them, filled in by
        # read_setpoint_ranges(). Empty until then, and callers fall back
        # to the wider inherited constants rather than refusing a value the
        # pump might well accept.
        self._setpoint_ranges: dict[int, tuple[float, float]] = {}

    #: Class 3 command IDs. START/STOP change the run state and nothing
    #: else - no mode, no setpoint - which is why they replaced the fused
    #: control object for on/off.
    CLASS3_STOP = 0x05
    CLASS3_START = 0x06

    async def _send_run_command(self, start: bool) -> bool:
        """
        Start or stop the pump via the Class 3 run-state command.

        Carries no mode and no setpoint, so it cannot disturb either. The
        pump answers with a bare acknowledgement: ``[03 00]`` means it
        executed the command, ``[03 01 xx]`` means it only described the
        data item and did nothing.

        It also sends no notification afterwards, so a caller that needs to
        know the resulting run state has to read it back.
        """
        apdu = bytes(
            [0x03, 0x81, self.CLASS3_START if start else self.CLASS3_STOP]
        )
        req = self._build_geni_packet(0xF8, 0xE7, apdu)
        return await self._send_with_retry(
            req, "Start pump" if start else "Stop pump"
        )

    async def start(self, mode: int | None = None) -> bool:
        """
        Start the pump.

        Uses the Class 3 START command, which changes only the run state.
        The pump keeps its current mode and that mode's stored setpoint.

        Args:
            mode: Optional control mode to switch to first. Sent as a
                separate, unfused mode change rather than folded into the
                start command.

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()
        logger.info("Starting pump...")

        if mode is not None and not await self.set_mode(mode):
            logger.error("Aborting start: mode change failed")
            return False

        return await self._send_run_command(start=True)

    async def stop(self, mode: int | None = None) -> bool:
        """
        Stop the pump.

        Uses the Class 3 STOP command, which changes only the run state.

        Args:
            mode: Optional control mode to switch to first. Sent as a
                separate, unfused mode change.

        Returns:
            True if successful, False otherwise
        """
        self.session.ensure_authenticated()
        logger.info("Stopping pump...")

        if mode is not None and not await self.set_mode(mode):
            logger.error("Aborting stop: mode change failed")
            return False

        return await self._send_run_command(start=False)

    def _mode_byte(self, mode_val: int) -> int:
        """
        Map a control mode to its wire byte.

        Raises rather than substituting a default. The previous fallback
        was Constant Speed, so asking for a mode the map does not cover -
        any AutoAdapt variant, for instance - silently put the pump into a
        different mode from the one requested.
        """
        try:
            return self._MODE_BYTE_MAP[mode_val]
        except KeyError:
            supported = ", ".join(str(m) for m in sorted(self._MODE_BYTE_MAP))
            raise ValueError(
                f"Control mode {mode_val} is not supported over this "
                f"protocol; supported modes are {supported}"
            ) from None

    async def _send_set_mode_request(self, mode_val: int) -> bool:
        """
        Change the control mode without touching anything else.

        Writes Object 86 sub-id 10 (``overall_control_mode_local_request``,
        wire Obj 0x0A01), whose payload carries ``operation_mode = NoCmd``
        and ``set_point = NaN`` so only the control mode is applied. This
        is how the Grundfos GO app switches modes.

        The fused control object (Obj 0x0601) cannot do this: it writes the
        run state and the setpoint in the same frame, so a mode change
        through it either forces the pump on or overwrites the target
        mode's stored setpoint, depending on what the caller supplies.

        Deliberately sends no configuration commit - the mode change
        persists on its own, and the commit writes the schedule, which has
        nothing to do with the control mode.

        Returns:
            True if the command was acknowledged.
        """
        mode_byte = self._mode_byte(mode_val)

        payload = bytearray([0x2F, 0x01, 0x00, 0x00, 0x07])
        payload.append(0x00)  # control_source = Undefined (ignored)
        payload.append(self.OPERATION_MODE_NO_CMD)  # leave run state alone
        payload.append(mode_byte)  # the only field applied
        payload.extend(self.SETPOINT_KEEP)

        apdu = bytearray([0x0A, 0x90])
        apdu.extend(encode_uint16_be(self.SUB_CONTROL))
        apdu.extend(encode_uint16_be(self.OBJ_MODE_REQUEST))
        apdu.extend(payload)

        req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))
        return await self._send_with_retry(
            req, f"Set Mode Request (mode={mode_val})"
        )

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
        mode_byte = self._mode_byte(mode_val)

        # Build payload
        payload = bytearray([0x2F, 0x01, 0x00, 0x00, 0x07, 0x00])
        payload.append(0x00 if start else 0x01)  # 0=Start, 1=Stop
        payload.append(mode_byte)

        if setpoint is not None:
            payload.extend(encode_float_be(setpoint))
        elif mode_byte in self._SCALAR_SETPOINT_MODES:
            # No value to assert, so tell the pump to keep the one it has.
            payload.extend(self.SETPOINT_KEEP)
        else:
            payload.extend(self._MODE_SUFFIX_MAP[mode_byte])

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

    async def set_mode(self, mode: ControlMode | int) -> bool:
        """
        Set the control mode, and nothing else.

        Neither the run state nor any mode's stored setpoint is touched:
        the mode change goes through the pump's dedicated mode-request
        object rather than the fused control object, which used to force
        the pump on and overwrite the target mode's setpoint with a
        default.

        Args:
            mode: Control mode to set

        Returns:
            True if mode set successfully, False otherwise
        """
        self.session.ensure_authenticated()

        mode_val = mode.value if isinstance(mode, ControlMode) else mode
        logger.info(f"Setting control mode to {mode_val}...")

        if await self._send_set_mode_request(mode_val):
            self._current_mode = (
                mode if isinstance(mode, ControlMode) else mode_val
            )
            return True

        return False

    async def get_mode(self, retries: int = 3) -> SetpointInfo | None:
        """
        Get the current control mode and setpoint information.

        Reads Class 10 Object 86, Sub-ID 7
        (``overall_operation_prioritized_request_obj``) - the pump's own
        view of its state after it has weighed remote, local and alarm
        influence against each other. For Temperature Range Control
        (mode 27) it additionally reads Object 91, Sub-ID 430.

        Sub-ID 6, which this used to read, is the *request* object: it
        echoes what was last written and reports ``control_source = 0``
        indefinitely. Measured side by side on hardware, Sub 6 returned
        ``control_source = 0`` while Sub 7 returned ``1`` (Local/Panel),
        which is why ``is_remote`` was never meaningful before.

        Returns:
            SetpointInfo with current control mode, operation mode, and setpoint value,
            or None if read failed

        Raises:
            ConnectionError: If the BLE connection to the pump drops while
                waiting for the response.

        Example:
            >>> info = await control.get_mode()  # doctest: +SKIP
            >>> if info and info.control_mode == ControlMode.CONSTANT_PRESSURE:  # doctest: +SKIP
            ...     value, unit = info.get_display_value()
            ...     print(f"Running in constant pressure mode: {value} {unit}")

        Implementation Notes:
            - Standard modes: Object 86, Sub-ID 7, Type 303 (OperationStatusRequest)
            - Temperature Range: Object 91, Sub-ID 430, Type 1012
            - Response format: `[00 00 XX][control_source][operation_mode][control_mode][setpoint(4 bytes float)]`
            - Setpoint is big-endian float at offset 3 (after 3-byte header)
        """
        self.session.ensure_authenticated()

        try:
            import struct

            from ..constants import ControlMode

            # Read Class 10: Object 86, Sub-ID 7
            # (overall_operation_prioritized_request_obj) - the prioritized
            # state, not the request object; see the docstring.
            # Retry: this is often the first read issued right after the
            # authentication handshake, and the pump can briefly be
            # unresponsive while it finishes settling into the new session.
            data = await self._read_class10_object(86, 7, retries=retries)

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

                    # Flow setpoints are stored in SI m3/s. Reading one
                    # without this factor is where the ~1000x discrepancy
                    # came from - 2.5 m3/h reads back as 0.000694.
                    elif control_mode == ControlMode.CONSTANT_FLOW:
                        setpoint = setpoint * self.SECONDS_PER_HOUR

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

        except READ_ERRORS as e:
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

        if not self._check_setpoint(
            ControlMode.CONSTANT_PRESSURE, value_m, "m", (0.5, 10.0)
        ):
            return False

        # Convert meters to Pascals
        value_pa = value_m * 9806.65

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.CONSTANT_PRESSURE, setpoint=value_pa
        ):
            return False

        # The pump takes the setpoint from the fused control request
        # above. There is no second write; see the note on
        # _set_class10_setpoint's removal below.
        return await self._commit_setpoint()

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

        if not self._check_setpoint(
            ControlMode.CONSTANT_SPEED, value_rpm, "RPM", (500.0, 4500.0)
        ):
            return False

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.CONSTANT_SPEED, setpoint=value_rpm
        ):
            return False

        # The pump takes the setpoint from the fused control request
        # above. There is no second write; see the note on
        # _set_class10_setpoint's removal below.
        return await self._commit_setpoint()

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
        if not self._check_setpoint(
            ControlMode.CONSTANT_FLOW, value_m3h, "m³/h", (0.1, 10.0)
        ):
            return False

        # The pump stores this setpoint in SI m3/s, so convert before it
        # goes anywhere near the wire.
        value_m3s = value_m3h / self.SECONDS_PER_HOUR

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.CONSTANT_FLOW, setpoint=value_m3s
        ):
            return False

        # The pump takes the setpoint from the fused control request
        # above. There is no second write; see the note on
        # _set_class10_setpoint's removal below.
        return await self._commit_setpoint()

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

        # Proportional pressure has its own range, and it is not constant
        # pressure's: the pump reports 2.599-4.569 m here against
        # 1.000-2.450 m there. The two do not overlap, so borrowing one for
        # the other refuses every setpoint the mode actually accepts.
        if not self._check_setpoint(
            ControlMode.PROPORTIONAL_PRESSURE, value_m, "m", (0.5, 10.0)
        ):
            return False

        # Convert meters to Pascals
        value_pa = value_m * 9806.65

        # 1. Update overall operation request (Sub 6)
        if not await self._send_control_request(
            ControlMode.PROPORTIONAL_PRESSURE, setpoint=value_pa
        ):
            return False

        # The pump takes the setpoint from the fused control request
        # above. There is no second write; see the note on
        # _set_class10_setpoint's removal below.
        return await self._commit_setpoint()

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
            >>> await control.set_temperature_control(35.0, 39.0)  # Radiator system  # doctest: +SKIP
            >>> await control.set_temperature_control(35.0, 39.0, "underfloor")  # doctest: +SKIP

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
        lo, hi = self.TEMP_RANGE_MIN_C, self.TEMP_RANGE_MAX_C
        if not (lo <= on_temp_c <= hi):
            logger.error(
                f"On temperature {on_temp_c}°C is outside valid range "
                f"({lo:g}-{hi:g}°C)"
            )
            return False

        if not (lo <= off_temp_c <= hi):
            logger.error(
                f"Off temperature {off_temp_c}°C is outside valid range "
                f"({lo:g}-{hi:g}°C)"
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

        mode, _register_id = heating_map[heating_type]

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
            >>> await control.set_autoadapt(1.5)  # 1.5 meters  # doctest: +SKIP
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

    #: Length of the temperature-range struct's trailing limits field.
    TEMP_RANGE_LIMITS_LEN = 5

    async def _read_temp_range_limits_tail(self) -> bytes | None:
        """
        Read the pump's stored on/off-time limits from Object 91 Sub 430.

        The struct is ``[autoadapt][min f32][max f32][limits(5)]``; only
        the limits are returned. Returns None if the object cannot be read,
        so the caller can decline to write rather than invent them.
        """
        data = await self._read_class10_object(91, 430)
        if not data:
            return None

        # Skip the 3-byte header, then autoadapt + two floats.
        offset = (
            3 if len(data) >= 3 and data[0] == 0x00 and data[1] == 0x00 else 0
        )
        tail_start = offset + 9
        tail = data[tail_start : tail_start + self.TEMP_RANGE_LIMITS_LEN]
        if len(tail) != self.TEMP_RANGE_LIMITS_LEN:
            logger.warning(
                f"Temperature range payload too short for its limits field: "
                f"{len(data)} bytes"
            )
            return None

        logger.debug(f"Pump temperature-range limits: {tail.hex()}")
        return bytes(tail)

    async def get_temperature_range(self) -> tuple[float, float, bool] | None:
        """
        Read the stored temperature range and AutoAdapt flag.

        Returns:
            ``(min_c, max_c, autoadapt)``, or None if the read failed.
        """
        import struct

        data = await self._read_class10_object(91, 430)
        if not data or len(data) < 12:
            return None

        offset = 3 if data[0] == 0x00 and data[1] == 0x00 else 0
        if len(data) < offset + 9:
            return None

        autoadapt = bool(data[offset])
        min_temp = struct.unpack(">f", data[offset + 1 : offset + 5])[0]
        max_temp = struct.unpack(">f", data[offset + 5 : offset + 9])[0]
        return min_temp, max_temp, autoadapt

    async def set_temperature_range_control(
        self,
        min_temp: float,
        max_temp: float,
        autoadapt: bool | None = None,
    ) -> bool:
        """
        Set temperature range control mode (Mode 27) with min/max setpoints.

        Args:
            min_temp: Minimum temperature in Celsius
            max_temp: Maximum temperature in Celsius
            autoadapt: If True, enables automatic flow adjustment (1-4 gpm).
                If False, uses fixed flow limits. If omitted (the default),
                the pump's current setting is preserved - the three fields
                share one write, so passing a default here silently turned
                AutoAdapt back on every time a bound was adjusted.

        Returns:
            True if successful, False otherwise

        Example:
            >>> await control.set_temperature_range_control(35.0, 45.0, autoadapt=True)  # doctest: +SKIP
        """
        self.session.ensure_authenticated()

        if autoadapt is None:
            current = await self.get_temperature_range()
            if current is None:
                logger.error(
                    "Could not read the pump's AutoAdapt setting; aborting "
                    "rather than guessing it"
                )
                return False
            autoadapt = current[2]

        logger.info(
            f"Setting Temperature Range Control: {min_temp}°C - {max_temp}°C (autoadapt={autoadapt})..."
        )

        # 1. Switch mode. Unfused, so this asserts the mode and nothing
        # else - the min temperature is not a Class 10 setpoint and does
        # not belong in the control frame.
        if not await self._send_set_mode_request(
            ControlMode.TEMPERATURE_RANGE_CONTROL
        ):
            logger.error("Failed to switch to Temperature Range Control mode")
            return False

        # The struct's trailing bytes are the pump's own on/off-time
        # limits, not padding. Read them so they can be written back
        # unchanged; sending constants overwrites the pump's limits with
        # whatever those constants happen to be. Measured on hardware, the
        # real tail is 0f 3c 02 05 01 - the constants below it were never
        # anything the pump had.
        limits_tail = await self._read_temp_range_limits_tail()
        if limits_tail is None:
            logger.error(
                "Could not read the pump's temperature-range limits; "
                "aborting rather than overwriting them with defaults"
            )
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

        # The pump's own on/off-time limits, echoed back verbatim.
        apdu.extend(limits_tail)

        req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))
        if await self._send_with_retry(req, "Set Temperature Range (Obj 91)"):
            await self._send_configuration_commit()
            return True
        return False

    #: The pump's flow limiters, as ``limiter_user_config`` (type 895),
    #: ``limiter_factory_config`` (897) and ``limiter_status`` (896).
    #:
    #: Only two exist. Object 86 sub-ids 600-619, 620-639 and 640-659 are
    #: declared as twenty instances each in the GENI profile, but every
    #: sub-id past the second answers ``OPERATION_FAILED`` - measured
    #: 2026-08-20 by reading all sixty. The name enum in
    #: ``geni_profile_52_7.xml`` gives MaxFlow = 1, MinFlow = 2, so the
    #: instances are per limiter rather than per mode.
    LIMITER_NAMES: ClassVar[dict[int, str]] = {1: "MaxFlow", 2: "MinFlow"}
    SUB_LIMITER_USER_CONFIG = 600
    SUB_LIMITER_FACTORY_CONFIG = 620
    SUB_LIMITER_STATUS = 640

    async def read_limiters(self) -> dict[str, dict[str, float | bool]]:
        """
        Read the pump's flow limiters and whether either is limiting.

        A limiter that is enabled caps delivered flow regardless of the
        setpoint, and nothing in the setpoint range says so: the type 301
        range is the *factory* range. So a setpoint can be accepted, read
        back correct, and still not be delivered. This is the only way to
        see that.

        Returns:
            ``{"MaxFlow": {...}, "MinFlow": {...}}`` with ``enabled``,
            ``limit_m3h``, ``factory_min_m3h``, ``factory_max_m3h`` and
            ``limiting`` for each limiter that answered.

        Examples:
            >>> limiters = await client.control.read_limiters()  # doctest: +SKIP
            >>> limiters["MaxFlow"]["enabled"]  # doctest: +SKIP
            False
        """
        out: dict[str, dict[str, float | bool]] = {}

        for index, name in self.LIMITER_NAMES.items():
            offset = index - 1
            entry: dict[str, float | bool] = {}

            user = await self._read_limiter_struct(
                self.SUB_LIMITER_USER_CONFIG + offset, minimum=6
            )
            if user is not None:
                entry["enabled"] = bool(user[1])
                limit = decode_float_be(user, 2)
                if limit is not None:
                    entry["limit_m3h"] = limit * 3600.0

            factory = await self._read_limiter_struct(
                self.SUB_LIMITER_FACTORY_CONFIG + offset, minimum=9
            )
            if factory is not None:
                low = decode_float_be(factory, 1)
                high = decode_float_be(factory, 5)
                if low is not None and high is not None:
                    entry["factory_min_m3h"] = low * 3600.0
                    entry["factory_max_m3h"] = high * 3600.0

            status = await self._read_limiter_struct(
                self.SUB_LIMITER_STATUS + offset, minimum=6
            )
            if status is not None:
                entry["limiting"] = bool(status[1])

            if entry:
                out[name] = entry

        return out

    async def _read_limiter_struct(
        self, sub_id: int, minimum: int
    ) -> bytes | None:
        """Read one limiter object, past its three-byte size header."""
        data = await self._read_class10_object(self.PUMP_OBJ, sub_id)
        if not data:
            return None
        body = data
        if len(body) >= 3 and body[0] == 0 and body[1] == 0:
            body = body[3:]
        return body if len(body) >= minimum else None

    #: Object 91 Sub 421, ``dhw_on_off_control_configuration_obj``. Holds
    #: the live cycle configuration: ``[flow setpoint f32 (m3/s)][on][off]``.
    #:
    #: Not Sub 430, which this used to read and write. Sub 430 is
    #: ``TemperatureRangeControlUserSettings`` - its trailing bytes are the
    #: on/off-time *limits*, invariant to the configuration - so cycle times
    #: read from it never changed and writes to it never took.
    SUB_DHW_CONFIG = 0x01A5
    OBJ_USER_SETTINGS = 91

    async def _read_dhw_config(self) -> tuple[bytes, int, int] | None:
        """
        Read the stored cycle configuration.

        Returns ``(flow_setpoint_raw, on_minutes, off_minutes)``, with the
        flow kept as raw wire bytes so a later write can echo it back
        without a float round trip. None if the object cannot be read or a
        period is outside the 1-60 the pump accepts.
        """
        data = await self._read_class10_object(
            self.OBJ_USER_SETTINGS, self.SUB_DHW_CONFIG
        )
        if not data:
            return None

        offset = (
            3 if len(data) >= 3 and data[0] == 0x00 and data[1] == 0x00 else 0
        )
        if len(data) < offset + 6:
            logger.warning(f"DHW config payload too short: {len(data)} bytes")
            return None

        flow_raw = bytes(data[offset : offset + 4])
        on_minutes = data[offset + 4]
        off_minutes = data[offset + 5]

        if not (1 <= on_minutes <= 60 and 1 <= off_minutes <= 60):
            logger.warning(
                f"DHW config reports out-of-range periods "
                f"(on={on_minutes}, off={off_minutes}); treating as unknown"
            )
            return None

        return flow_raw, on_minutes, off_minutes

    async def set_cycle_time_control(
        self, on_minutes: int, off_minutes: int
    ) -> bool:
        """
        Set cycle time control mode (Mode 25 / DHW_ON_OFF_CONTROL).

        Writes Object 91 Sub 421 as a read-modify-write: the object also
        carries the flow the pump targets during ON periods, which is
        echoed back byte for byte rather than recomputed, so setting the
        periods cannot disturb it.

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

        stored = await self._read_dhw_config()
        if stored is None:
            logger.error(
                "Could not read the stored cycle configuration; aborting "
                "rather than writing a fabricated flow setpoint"
            )
            return False
        flow_raw, _, _ = stored

        # 1. Switch mode, unfused.
        if not await self._send_set_mode_request(
            ControlMode.DHW_ON_OFF_CONTROL
        ):
            return False

        # 2. Write the configuration, in the Grundfos GO app's frame shape:
        #    [0A][8F][5B][01 A5][03 D9][01][00 00 06][flow f32][on][off]
        try:
            apdu = bytearray(
                [
                    0x0A,  # Class 10
                    0x8F,  # OpSpec: SET + 15 bytes
                    0x5B,  # Obj-ID (91)
                    0x01,
                    0xA5,  # Sub-ID (421)
                    0x03,
                    0xD9,  # Type 985 (DHWOnOffControlConfiguration)
                    0x01,  # Object version
                    0x00,
                    0x00,
                    0x06,  # Size (6 bytes)
                ]
            )
            apdu.extend(flow_raw)
            apdu.append(on_minutes)
            apdu.append(off_minutes)

            req = self._build_geni_packet(0xF8, 0xE7, bytes(apdu))
            if not await self._send_with_retry(req, "Set Cycle Time"):
                logger.error("Failed to write cycle time configuration")
                return False

            logger.info(
                f"Successfully set cycle times: {on_minutes} min ON, {off_minutes} min OFF"
            )

            # Deliberately no configuration commit: the commit writes the
            # schedule overview, which has nothing to do with this object,
            # and captures of the app show it sending none here.
            return True

        except READ_ERRORS as e:
            logger.error(f"Failed to write cycle time configuration: {e}")
            return False

    async def get_cycle_time_config(self) -> tuple[int, int] | None:
        """
        Get current cycle time configuration for Mode 25 (DHW_ON_OFF_CONTROL).

        Returns:
            Tuple of (on_time_minutes, off_time_minutes) if successful, None otherwise
        """
        self.session.ensure_authenticated()

        try:
            stored = await self._read_dhw_config()
            if stored is None:
                logger.error("Could not read cycle time configuration")
                return None

            _, on_time, off_time = stored
            logger.info(
                f"Read cycle times: {on_time} min ON, {off_time} min OFF"
            )
            return (on_time, off_time)

        except READ_ERRORS as e:
            logger.error(f"Failed to read cycle time configuration: {e}")
            return None

    async def get_cycle_flow(self) -> float | None:
        """
        Flow the pump targets during cycle-mode ON periods, in m3/h.

        Stored in SI m3/s, like every other flow setpoint.
        """
        import struct

        stored = await self._read_dhw_config()
        if stored is None:
            return None
        return struct.unpack(">f", stored[0])[0] * self.SECONDS_PER_HOUR

    # Helper methods

    def _check_setpoint(
        self, mode: int, value: float, unit: str, fallback: tuple[float, float]
    ) -> bool:
        """
        Is this a setpoint the pump could store at all?

        Only rejects what is not a number. An out-of-range value is *not*
        rejected: this pump does not refuse a setpoint it dislikes, it
        takes it and clamps it, and reports what it stored. Letting it
        answer tells the caller more than a refusal does, and the answer is
        the pump's to give.

        It also has to be. The range the pump publishes is the *factory*
        range, and with a flow limiter enabled the pump manages actual
        speed to hold the flow bound - where it settles is a property of
        the installation's hydraulics rather than of the pump. On one
        reported loop a 3000 RPM request delivered 1885. There is no number
        that is the maximum speed there, so there is no bound to check
        against, and a check that looked authoritative would be worse than
        none. See esphome-alpha-hwr #276.

        The published range is still worth having: it goes in the settle
        detail when the pump does clamp, so the caller learns why.
        """
        if not math.isfinite(value):
            # The all-ones float is the SETPOINT_KEEP sentinel, so a NaN on
            # the wire reads as "leave the setpoint alone" - a write that
            # silently does nothing rather than one that fails.
            logger.error(f"{value} is not a setpoint the pump can store")
            return False

        published = self.get_setpoint_range(mode)
        low, high = published or fallback
        if not low <= value <= high:
            logger.info(
                f"Setpoint {value} {unit} is outside the "
                f"{low:.4g}-{high:.4g} {unit} "
                + ("range the pump reports" if published else "assumed range")
                + "; sending it anyway - the pump clamps rather than refusing"
            )
        return True

    async def _commit_setpoint(self) -> bool:
        """
        Persist a setpoint the fused control request has just carried.

        The GO app follows every Object 86 Sub 6 control request with an
        Object 84 Sub 1 overview commit, 25 times over in the capture
        corpus, and that is what makes the value stick.
        """
        await self._send_configuration_commit()
        return True

    async def read_setpoint_ranges(self) -> dict[int, tuple[float, float]]:
        """
        Read each scalar mode's setpoint range from the pump.

        The pump publishes these in the type 301 factory-config objects at
        Object 86 sub-ids 13, 15, 17 and 39 - the same objects the Grundfos
        GO app's setpoint slider binds to. Each holds a 28-byte struct whose
        first three floats are default, minimum and maximum, in the pump's
        native units.

        Returns:
            ``{ControlMode: (minimum, maximum)}`` in this client's units,
            for as many modes as could be read.

        Note:
            The chain is deliberately **sequential and stops at the first
            failure**. All four objects answer with the same type code
            (``00 01 2d 01``), so the transport cannot tell their replies
            apart. Carrying on past a failure hands read N's late reply to
            read N+1 and shifts every remaining range by one slot - which
            would bound constant pressure by constant speed's 1650-3671
            read as Pascals, 0.168-0.374 m, and refuse an ordinary 1.5 m
            setpoint for the rest of the connection.

        Examples:
            >>> ranges = await client.control.read_setpoint_ranges()  # doctest: +SKIP
            >>> ranges[ControlMode.CONSTANT_SPEED]  # doctest: +SKIP
            (1650.0, 3671.0)
        """
        ranges: dict[int, tuple[float, float]] = {}

        for mode, sub_id in self._RANGE_SUB_IDS.items():
            data = await self._read_class10_object(self.PUMP_OBJ, sub_id)
            if not data:
                logger.debug(
                    f"Setpoint range for mode {mode} (Sub {sub_id}) could "
                    f"not be read; stopping the chain rather than "
                    f"misattributing the replies that follow"
                )
                break

            body = data
            if len(body) >= 3 and body[0] == 0 and body[1] == 0:
                body = body[3:]

            if len(body) < 12:
                logger.debug(
                    f"Setpoint range for mode {mode} is {len(body)} bytes, "
                    f"too short for three floats"
                )
                break

            minimum = decode_float_be(body, 4)
            maximum = decode_float_be(body, 8)
            if minimum is None or maximum is None:
                break

            scale = self._RANGE_SCALE[mode]
            ranges[mode] = (minimum * scale, maximum * scale)

        if ranges:
            self._setpoint_ranges.update(ranges)
        return ranges

    def get_setpoint_range(self, mode: int) -> tuple[float, float] | None:
        """
        The pump's own range for a mode, if it has been read.

        Returns None when it has not. Callers should fall back to the
        *wider* inherited constants rather than refusing: letting the pump
        clamp a value it dislikes is better than refusing one it would have
        taken.
        """
        return self._setpoint_ranges.get(mode)

    # _set_class10_setpoint() was here, and is deliberately gone.
    #
    # It built [0A][84][SubH][SubL][ObjH][ObjL][f32] - sub-id first, where
    # every Class 10 SET this pump accepts is object first. So the frame
    # named object 0x00, and the pump refused it. Confirmed on hardware
    # 2026-08-20 by sending the exact frame the method produced:
    #
    #     -> 27 0C E7 F8 0A 84 00 27 00 56 38 84 4F 4B EA CC
    #     <- 24 07 F8 E7 0A 81 00 4F 40 4E 81
    #
    # 0x81 is Unknown Data Item with one payload byte, and that byte is
    # 0x00: the object it could not find. Every setpoint write this client
    # has made since the method existed was refused, invisibly, because the
    # send was fire-and-forget and _send_with_retry() reports success even
    # on a timeout.
    #
    # Correcting the address would not have been enough. Sub-ids 13, 15, 17
    # and 39 are type 301, a 28-byte struct of seven floats; a SET to a
    # typed object has to carry [TypeH][TypeL][Ver][size] ahead of the body,
    # and a bare float would be read as the top half of the type word.
    #
    # It is also not needed. The fused Object 86 Sub 6 control request
    # already carries the setpoint - which is how the GO app sets one,
    # 25 times over in the capture corpus, each followed by an Object 84
    # Sub 1 overview commit. That is what _commit_setpoint() does.

    async def _send_with_retry(
        self, packet: bytes, description: str, retries: int = 3
    ) -> bool:
        """
        Send packet with retry logic and optional response verification.

        For control commands, we attempt to verify success by waiting for a response.
        If no response is received, we still consider it successful (fire-and-forget).
        """
        # A reply only counts if it comes back on the class the command
        # was sent on. This matters most for the Class 3 run commands:
        # their acknowledgement is a bare two-byte frame with nothing to
        # match on but the class, so without this gate a Class 10 telemetry
        # notification arriving first would be read as the answer.
        #
        # Class 10 SETs *are* acknowledged, in 90-120 ms measured through
        # this client against an ALPHA HWR, with the canonical nine-byte
        # 24 05 F8 E7 0A 01 00 AE A2. An earlier revision here skipped the
        # wait on the strength of a probe that never saw one - because the
        # probe wrote frames whole, and this pump ignores a GENI frame that
        # is not split into 20-byte GATT writes whatever the negotiated
        # MTU says. The frames never arrived, so of course nothing answered
        # them.
        command = Command.for_request(
            packet,
            expect_short_ack=True,
            description=description,
        )

        for attempt in range(retries):
            try:
                response = await self.transport.send_command(
                    packet,
                    command,
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

            except READ_ERRORS as e:
                logger.warning(
                    f"{description} attempt {attempt + 1} failed: {e}"
                )
                if attempt < retries - 1:
                    await asyncio.sleep(0.2)

        return False

    # ------------------------------------------------------------------
    # Verified writes
    #
    # These return a WriteResult describing what the pump actually stored,
    # decided by reading it back. The bool-returning setters above are the
    # wire primitives they are built from; prefer these, because the pump
    # clamps values it dislikes rather than refusing them, and a bare True
    # cannot tell you that happened.
    # ------------------------------------------------------------------

    def attach_write_service(self, writes: WriteOperationService) -> None:
        """Give this service the write layer its verified methods submit to."""
        self._writes = writes

    def _require_writes(self) -> WriteOperationService:
        writes = self._writes
        if writes is None:
            raise RuntimeError(
                "No write service attached; construct this service through "
                "AlphaHWRClient, which wires one in"
            )
        return writes

    async def set_enabled(self, enabled: bool) -> WriteResult:
        """
        Start or stop the pump, and confirm the resulting run state.

        The pump sends nothing after a Class 3 run command, so the result
        comes from reading the state back.
        """
        return await self._require_writes().submit(
            WriteCommand.SET_ENABLED, "enabled", enabled=enabled
        )

    async def set_mode_verified(self, mode: ControlMode | int) -> WriteResult:
        """Change the control mode and confirm the pump applied it."""
        return await self._require_writes().submit(
            WriteCommand.SET_MODE, "mode", mode=mode
        )

    async def set_setpoint(
        self, mode: ControlMode | int, value: float
    ) -> WriteResult:
        """
        Set a mode's setpoint and report what the pump stored.

        Switches the pump into ``mode`` as well - the two share one write,
        so this cannot merely edit a stored value in the background.

        A ``clamped`` result is normal and not an error: this pump stores
        1650 for a request of 600 RPM and 3671 for 4400, the ends of its
        own limits.
        """
        return await self._require_writes().submit(
            WriteCommand.SET_SETPOINT,
            f"setpoint:{int(mode)}",
            mode=mode,
            value=value,
        )

    async def set_temperature_range(
        self,
        min_temp: float,
        max_temp: float,
        autoadapt: bool | None = None,
    ) -> WriteResult:
        """
        Set the temperature range and confirm it, preserving the rest.

        ``autoadapt=None`` keeps the pump's current setting; the three
        fields share one write, so a default here would silently change it.
        """
        return await self._require_writes().submit(
            WriteCommand.SET_TEMPERATURE_RANGE,
            "temp_range",
            temp_min=min_temp,
            temp_max=max_temp,
            autoadapt=autoadapt,
        )

    async def set_cycle_times(
        self, on_minutes: int, off_minutes: int
    ) -> WriteResult:
        """Set the cycle periods and confirm them, preserving the flow."""
        return await self._require_writes().submit(
            WriteCommand.SET_CYCLE_TIMES,
            "cycle_times",
            on_minutes=on_minutes,
            off_minutes=off_minutes,
        )

    # ------------------------------------------------------------------
    # Cache synchronisation and readiness
    # ------------------------------------------------------------------

    async def sync_cache(self) -> bool:
        """
        Read the pump's stored configuration into this service.

        Several writes carry more fields than the caller sets - the
        temperature range writes min, max and AutoAdapt together, the cycle
        config writes both periods and a flow - so they have to know what
        the pump currently holds. Reading it once here, after
        authentication, is what lets those writes preserve the fields they
        were not asked to change instead of inventing them.

        Returns:
            True if everything needed was read.
        """
        self._cache_valid = False

        # One attempt per read. The caller decides whether to try again -
        # blocking a connection for the full retry budget when the pump is
        # simply not answering yet helps nobody.
        info = await self.get_mode(retries=1)
        if info is None:
            logger.warning(
                "Cache sync failed: could not read the control state"
            )
            return False
        self._cached_mode = info.control_mode
        self._cached_enabled = info.is_running
        self._cache_setpoint(info.control_mode, info.setpoint)

        temp_range = await self.get_temperature_range()
        if temp_range is None:
            logger.warning(
                "Cache sync failed: could not read the temperature range"
            )
            return False
        self._cached_temp_range = temp_range

        # The setpoint ranges, likewise, are not required. A pump that
        # will not answer them leaves the write layer on its fallback
        # constants, which is worse than the truth but better than being
        # unable to write at all. Read once per connection: they are
        # factory values and do not move.
        await self.read_setpoint_ranges()

        # The cycle configuration is deliberately not required. It is not
        # needed to display anything, and a pump that returns a short or
        # unusual Object 91 payload would otherwise leave this service
        # permanently not-ready, blocking every write.
        self._cached_cycle = await self.get_cycle_time_config()

        self._cache_valid = True
        logger.info(
            f"Cache synchronised: mode={self._cached_mode!r} "
            f"range={temp_range[0]:g}-{temp_range[1]:g}C "
            f"cycle={self._cached_cycle}"
        )
        return True

    def _cache_setpoint(
        self, mode: ControlMode | int, value: float | None
    ) -> None:
        """
        Store a setpoint against its own mode.

        Per-mode rather than one shared slot: a single field leaks a value
        from one mode into another under different units, so a 4.0 m
        pressure setpoint comes back as a 4.0 RPM speed request.
        """
        if value is not None:
            self._cached_setpoints[int(mode)] = value

    def cached_setpoint(self, mode: ControlMode | int) -> float | None:
        """The last setpoint seen for ``mode``, or None if never read."""
        return self._cached_setpoints.get(int(mode))

    @property
    def is_cache_valid(self) -> bool:
        """
        Whether this service knows enough about the pump to write safely.

        False until :meth:`sync_cache` has succeeded, and again after a
        disconnect - a write built from a cache filled on a previous
        connection can carry values the pump no longer holds.
        """
        return self._cache_valid

    def invalidate_cache(self) -> None:
        """
        Forget everything read from the pump.

        Called on disconnect. The mode is dropped along with the rest: a
        command issued on one connection must not be treated as confirmed
        by a reading taken on the next.
        """
        self._cache_valid = False
        self._cached_mode = None
        self._cached_enabled = None
        self._cached_temp_range = None
        self._cached_cycle = None
        self._cached_setpoints.clear()
        logger.debug("Control cache invalidated")
