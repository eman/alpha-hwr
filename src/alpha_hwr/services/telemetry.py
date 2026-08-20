"""
Telemetry service for reading pump sensor data.

This service handles all telemetry operations including:
- Reading current telemetry snapshot
- Streaming continuous telemetry updates
- Parsing Class 10 DataObject notifications
- Managing telemetry state

The service coordinates between the transport layer (BLE communication)
and the protocol layer (frame parsing/telemetry decoding) to provide
a clean API for telemetry access.

This service demonstrates the separation of concerns:

1. **Transport Layer**: Handles BLE communication and raw packets
2. **Protocol Layer**: Parses frames and decodes telemetry
3. **Service Layer (this)**: Coordinates operations and manages state
4. **Models**: Define data structures (TelemetryData, AdvancedTelemetry)

The service maintains current telemetry state and updates it from:
- Active polling of registers (Class 2/3)
- Passive notifications from telemetry streams (Class 10)

"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..exceptions import READ_ERRORS
from ..models import AdvancedTelemetry, TelemetryData
from ..protocol import FrameParser, TelemetryDecoder
from ..protocol.frame_builder import FrameBuilder
from ..protocol.matcher import Command

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport


logger = logging.getLogger(__name__)


class TelemetryService:
    """
    Service for managing pump telemetry operations.

    This service provides high-level APIs for accessing telemetry data:
    - One-time reads (polling)
    - Continuous streaming (notifications)
    - State management

    Attributes:
        _telemetry: Current basic telemetry data
        _advanced_telemetry: Current advanced telemetry data
        _has_motor_state_stream: Flag indicating motor state stream is active
        _has_flow_stream: Flag indicating flow/pressure stream is active

    Example:
        >>> from alpha_hwr.core import Transport, Session
        >>> from alpha_hwr.services import TelemetryService
        >>>
        >>> # Initialize
        >>> transport = Transport(bleak_client)
        >>> session = Session(transport)
        >>> telemetry_service = TelemetryService(transport, session)
        >>>
        >>> # Read once
        >>> data = await telemetry_service.read_once()
        >>> print(f"Flow: {data.flow_m3h} m³/h")
        >>>
        >>> # Stream continuously
        >>> async for data in telemetry_service.stream():
        ...     print(f"Power: {data.power_w} W")
    """

    def __init__(self, transport: Transport, session: Session) -> None:
        """
        Initialize telemetry service.

        Args:
            transport: Transport layer for BLE communication
            session: Session manager for state tracking
        """
        self.transport = transport
        self.session = session

        # Current telemetry state
        self._telemetry = TelemetryData()
        self._advanced_telemetry = AdvancedTelemetry()

        # Stream detection flags
        self._has_motor_state_stream = False
        self._has_flow_stream = False

        # Whether the controller still needs a wake burst before the next read
        self._needs_wake = True

    @property
    def current(self) -> TelemetryData:
        """
        Get current telemetry data.

        Returns the most recently updated telemetry state. This may be from
        active polling or passive notifications.

        Returns:
            Current TelemetryData

        Example:
            >>> telemetry = service.current
            >>> print(f"Voltage: {telemetry.voltage_ac_v}V")
        """
        return self._telemetry

    @property
    def advanced(self) -> AdvancedTelemetry:
        """
        Get current advanced telemetry data.

        Returns advanced telemetry including converter temperature,
        inlet/outlet pressure, alarms/warnings, etc.

        Returns:
            Current AdvancedTelemetry

        Example:
            >>> adv = service.advanced
            >>> print(f"Converter temp: {adv.converter_temperature_c}°C")
        """
        return self._advanced_telemetry

    async def read_once(self) -> TelemetryData:
        """
        Read telemetry snapshot using Class 10 INFO commands.

        Sends INFO requests to query current telemetry data from the pump.
        This is the correct modern approach - NOT Class 3 register polling!

        The pump responds with Class 10 data object frames containing the
        requested telemetry values.

        Returns:
            TelemetryData with current values

        Example:
            >>> data = await service.read_once()
            >>> print(f"Flow: {data.flow_m3h} m³/h")
            >>> print(f"Power: {data.power_w} W")

        Implementation Notes:
            - Uses Class 10 INFO commands (OpSpec 0x00)
            - Filters out passive notifications (OpSpec 0x0E)
            - Parses responses using TelemetryDecoder
            - Updates internal state for subsequent queries
        """
        self.session.ensure_connected()

        # A telemetry register read is answered on the same class as the
        # pump's unsolicited notification stream, and these registers carry
        # no stable type code to match on, so the stream is turned away by
        # its operation specifier (0x0E) and the read takes the rest.
        # Class 2 error frames are turned away by the class check; the pump
        # sends the real data after them.
        read_reply = Command(
            reject_opspecs=frozenset({0x0E}),
            description="telemetry register read",
        )

        async def _query_with_retry(req: bytes, name: str) -> bytes | None:
            for attempt in range(1, 4):  # Up to 3 attempts
                resp = await self.transport.send_command(
                    req, read_reply, timeout=2.0
                )
                logger.debug(
                    f"{name} response: {resp.hex() if resp else 'None'} (len={len(resp) if resp else 0})"
                )
                if resp:
                    return resp
                if not self.transport.is_connected():
                    logger.debug(f"Pump disconnected after {name} query")
                    # The next read happens on a fresh connection, which
                    # starts with a sleeping controller again.
                    self._needs_wake = True
                    return None
                if attempt < 3:
                    logger.debug(
                        f"{name} query failed, sending wake burst and retrying..."
                    )
                    await self.transport.send_wake_burst()
                    self._needs_wake = False
                    await asyncio.sleep(0.2)
            return None

        # Wake the pump before the first read of a session. The controller is
        # often still asleep right after auth, and a read issued while it
        # sleeps goes unanswered (or trips a disconnect). Once it has answered
        # we stop paying the ~0.6s burst on every read: the retry path above
        # re-wakes it if it dozes off again.
        if self._needs_wake:
            try:
                await self.transport.send_wake_burst()
                self._needs_wake = False
            except READ_ERRORS as e:
                # A failed wake burst must not abort the read: fall through
                # and let the per-register retries deal with a controller
                # that is unresponsive. _needs_wake stays set so the next
                # read tries to wake it again.
                logger.debug(f"Pre-read wake burst failed: {e}")

        # 1. Query Motor State (if no active stream)
        if not self._has_motor_state_stream:
            try:
                req = FrameBuilder.build_class10_read(
                    0x570045
                )  # Motor state register
                resp = await _query_with_retry(req, "MOTOR_STATE")
                if resp:
                    frame = FrameParser.parse_frame(resp)
                    if frame.valid and frame.class_byte == 0x0A:
                        updates = TelemetryDecoder.decode(frame)
                        logger.debug(f"MOTOR_STATE updates: {updates}")
                        if updates:
                            updates["timestamp"] = datetime.now(UTC)
                            self._telemetry = self._telemetry.model_copy(
                                update=updates
                            )
            except READ_ERRORS as e:
                logger.debug(f"Failed to read motor state: {e}")

        await asyncio.sleep(0.05)

        # 2. Query Flow/Pressure (if no active stream)
        if not self._has_flow_stream:
            if not self.transport.is_connected():
                logger.debug("Pump disconnected after motor state query")
                return self._telemetry
            try:
                req = FrameBuilder.build_class10_read(
                    0x5D0122
                )  # Flow/pressure register
                resp = await _query_with_retry(req, "FLOW_PRESSURE")
                if resp:
                    frame = FrameParser.parse_frame(resp)
                    if frame.valid and frame.class_byte == 0x0A:
                        updates = TelemetryDecoder.decode(frame)
                        logger.debug(f"FLOW_PRESSURE updates: {updates}")
                        if updates:
                            updates["timestamp"] = datetime.now(UTC)
                            self._telemetry = self._telemetry.model_copy(
                                update=updates
                            )
            except READ_ERRORS as e:
                logger.debug(f"Failed to read flow/pressure: {e}")

        await asyncio.sleep(0.05)

        # 3. Query Temperatures (always poll)
        if not self.transport.is_connected():
            logger.debug("Pump disconnected before temperature query")
            return self._telemetry
        try:
            req = FrameBuilder.build_class10_read(
                0x5D012C
            )  # Temperature register
            resp = await _query_with_retry(req, "TEMPERATURE")
            if resp:
                frame = FrameParser.parse_frame(resp)
                if frame.valid and frame.class_byte == 0x0A:
                    updates = TelemetryDecoder.decode(frame)
                    logger.debug(f"TEMPERATURE updates: {updates}")
                    if updates:
                        updates["timestamp"] = datetime.now(UTC)
                        self._telemetry = self._telemetry.model_copy(
                            update=updates
                        )
        except READ_ERRORS as e:
            logger.debug(f"Failed to read temperatures: {e}")

        await asyncio.sleep(0.05)

        return self._telemetry

    async def stream(
        self, interval: float = 0.1, poll_if_no_stream: bool = True
    ) -> AsyncIterator[TelemetryData]:
        """
        Stream continuous telemetry updates.

        This method yields telemetry data as it's updated, either from:
        - Passive Class 10 notifications (if pump sends them)
        - Active polling (if no notifications)

        Args:
            interval: Polling interval in seconds (default 0.1 = 10Hz)
            poll_if_no_stream: If True, falls back to polling if no stream detected

        Yields:
            TelemetryData as it's updated

        Example:
            >>> async for data in service.stream(interval=0.2):
            ...     print(f"Flow: {data.flow_m3h} m³/h, Power: {data.power_w} W")
            ...     if data.power_w > 100:
            ...         break  # Stop streaming

        Implementation Notes:
            - Non-blocking: uses async iteration
            - Can be cancelled by breaking from loop
            - Automatically detects if pump sends notifications
            - Falls back to polling if notifications stop
        """
        self.session.ensure_connected()

        # Register notification callback
        previous_telemetry = self._telemetry.model_copy()

        try:
            while True:
                # Check if we have active notification stream
                # If not, poll actively
                if poll_if_no_stream and not (
                    self._has_motor_state_stream or self._has_flow_stream
                ):
                    await self.read_once()

                # Yield if data changed
                if self._telemetry != previous_telemetry:
                    yield self._telemetry
                    previous_telemetry = self._telemetry.model_copy()

                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.debug("Telemetry stream cancelled")
            raise

    def update_from_notification(self, data: bytes) -> None:
        """
        Update telemetry state from BLE notification.

        This method is called by the Client's notification handler when a
        notification arrives. It parses the frame, decodes telemetry, and
        updates state.

        Args:
            data: Raw notification bytes from BLE

        Note:
            Registration of this handler is managed by the Client layer during
            connection setup. Services should not directly interact with the
            transport layer per the architecture guidelines.

        Example:
            >>> # Handler registration happens in Client.connect()
            >>> # The client automatically forwards notifications to this method

        Implementation Notes:
            - Automatically detects Class 10 telemetry frames
            - Routes to appropriate decoder based on Sub-ID/Object ID
            - Updates both basic and advanced telemetry
            - Sets stream detection flags
            - Thread-safe (can be called from notification callback)
        """
        try:
            logger.debug(
                f"update_from_notification called with {len(data)} bytes"
            )

            # Parse frame
            frame = FrameParser.parse_frame(data)

            # Check if this is even a Class 10 frame before proceeding
            if not frame.valid or frame.class_byte != 0x0A:
                logger.debug("Not a Class 10 frame, ignoring")
                return

            # A frame with no type fields is an acknowledgement, a refusal
            # or a runt - never telemetry.
            if frame.type_high is None or frame.type_low_ver is None:
                logger.debug(
                    "Class 10 frame carries no object type "
                    "(an ack, a refusal or a partial), ignoring"
                )
                return

            # Decode telemetry
            telemetry_data = TelemetryDecoder.decode(frame)
            logger.debug(f"Telemetry decoded: {telemetry_data}")

            if not telemetry_data:
                logger.debug("Empty telemetry data")
                return  # Unknown or empty telemetry

            # Separate basic and advanced telemetry fields
            adv_keys = {
                "converter_temperature_c",
                "inlet_pressure_bar",
                "outlet_pressure_bar",
                "active_alarms",
                "active_warnings",
            }
            shared_keys = {
                "pcb_temperature_c",
                "control_box_temperature_c",
            }

            basic_updates = {
                k: v
                for k, v in telemetry_data.items()
                if k not in adv_keys and k not in shared_keys
            }
            advanced_updates = {
                k: v
                for k, v in telemetry_data.items()
                if k in adv_keys or k in shared_keys
            }

            # Update telemetry state
            if basic_updates:
                basic_updates["timestamp"] = datetime.now(UTC)
                self._telemetry = self._telemetry.model_copy(
                    update=basic_updates
                )

            if advanced_updates:
                self._advanced_telemetry = self._advanced_telemetry.model_copy(
                    update=advanced_updates
                )

            # Set stream detection flags from the object type the pump
            # answered with. This used to compare against Object 87 /
            # Sub-ID 69 and Object 93 / Sub-ID 290 - the addresses that
            # were *requested*. A reply carries neither, so neither flag
            # could ever be set by a real notification, and the polling
            # path this exists to suppress ran regardless of whether the
            # pump was already streaming.
            if (frame.type_low_ver, frame.type_high) == (0x0003, 0x0001):
                self._has_motor_state_stream = True
            elif (frame.type_low_ver, frame.type_high) == (0x3502, 0x0002):
                self._has_flow_stream = True

            logger.debug(
                f"Telemetry updated from notification: {telemetry_data}"
            )

        except READ_ERRORS as e:
            logger.error(f"Failed to parse telemetry notification: {e}")
