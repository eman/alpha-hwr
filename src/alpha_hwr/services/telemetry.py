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

Implementation Notes for Other Languages
----------------------------------------
This service demonstrates the separation of concerns:

1. **Transport Layer**: Handles BLE communication and raw packets
2. **Protocol Layer**: Parses frames and decodes telemetry
3. **Service Layer (this)**: Coordinates operations and manages state
4. **Models**: Define data structures (TelemetryData, AdvancedTelemetry)

The service maintains current telemetry state and updates it from:
- Active polling of registers (Class 2/3)
- Passive notifications from telemetry streams (Class 10)

Example in other languages:

TypeScript:
```typescript
class TelemetryService {
    private transport: Transport;
    private telemetry: TelemetryData;
    private advancedTelemetry: AdvancedTelemetry;

    async readOnce(): Promise<TelemetryData> {
        // Poll all registers and return combined data
    }

    async *stream(): AsyncIterable<TelemetryData> {
        // Yield telemetry updates as they arrive
    }

    updateFromNotification(frame: ParsedFrame): void {
        // Update state from Class 10 notification
    }
}
```

Rust:
```rust
pub struct TelemetryService {
    transport: Arc<Transport>,
    telemetry: Arc<RwLock<TelemetryData>>,
    advanced_telemetry: Arc<RwLock<AdvancedTelemetry>>,
}

impl TelemetryService {
    pub async fn read_once(&self) -> Result<TelemetryData, Error> {
        // Poll all registers and return combined data
    }

    pub async fn stream(&self) -> impl Stream<Item = TelemetryData> {
        // Stream telemetry updates
    }

    pub fn update_from_notification(&self, frame: &ParsedFrame) {
        // Update state from Class 10 notification
    }
}
```
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, AsyncIterator

from ..models import TelemetryData, AdvancedTelemetry
from ..protocol.frame_builder import FrameBuilder
from ..protocol import FrameParser, TelemetryDecoder

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

        def is_response_not_notification(packet: bytes) -> bool:
            """
            Filter to accept INFO responses but reject passive notifications and errors.

            INFO responses: Class 0x0A with OpSpec not 0x0E (various data responses)
            Notifications: OpSpec 0x0E (passive stream) - REJECT
            Errors: Class 0x02 (error/status) - REJECT (pump sends data after error)
            """
            if len(packet) < 6:
                return False
            # Reject Class 10 passive notifications (OpSpec 0x0E)
            if packet[4] == 0x0A and packet[5] == 0x0E:
                return False
            # Reject Class 2 error responses (actual data comes after)
            if packet[4] == 0x02:
                return False
            # Accept Class 10 data responses
            return packet[4] == 0x0A

        # 1. Query Motor State (if no active stream)
        if not self._has_motor_state_stream:
            try:
                req = FrameBuilder.build_class10_read(
                    0x570045
                )  # Motor state register
                resp = await self.transport.query(
                    req, timeout=2.0, match_func=is_response_not_notification
                )
                logger.debug(
                    f"MOTOR_STATE response: {resp.hex() if resp else 'None'} (len={len(resp) if resp else 0})"
                )
                if resp:
                    frame = FrameParser.parse_frame(resp)
                    if frame.valid and frame.class_byte == 0x0A:
                        updates = TelemetryDecoder.decode(frame)
                        logger.debug(f"MOTOR_STATE updates: {updates}")
                        if updates:
                            updates["timestamp"] = datetime.now()
                            self._telemetry = self._telemetry.model_copy(
                                update=updates
                            )
            except Exception as e:
                logger.debug(f"Failed to read motor state: {e}")

        await asyncio.sleep(0.05)

        # 2. Query Flow/Pressure (if no active stream)
        if not self._has_flow_stream:
            try:
                req = FrameBuilder.build_class10_read(
                    0x5D0122
                )  # Flow/pressure register
                resp = await self.transport.query(
                    req, timeout=2.0, match_func=is_response_not_notification
                )
                logger.debug(
                    f"FLOW_PRESSURE response: {resp.hex() if resp else 'None'} (len={len(resp) if resp else 0})"
                )
                if resp:
                    frame = FrameParser.parse_frame(resp)
                    if frame.valid and frame.class_byte == 0x0A:
                        updates = TelemetryDecoder.decode(frame)
                        logger.debug(f"FLOW_PRESSURE updates: {updates}")
                        if updates:
                            updates["timestamp"] = datetime.now()
                            self._telemetry = self._telemetry.model_copy(
                                update=updates
                            )
            except Exception as e:
                logger.debug(f"Failed to read flow/pressure: {e}")

        await asyncio.sleep(0.05)

        # 3. Query Temperatures (always poll)
        try:
            req = FrameBuilder.build_class10_read(
                0x5D012C
            )  # Temperature register
            resp = await self.transport.query(
                req, timeout=2.0, match_func=is_response_not_notification
            )
            logger.debug(
                f"TEMPERATURE response: {resp.hex() if resp else 'None'} (len={len(resp) if resp else 0})"
            )
            if resp:
                frame = FrameParser.parse_frame(resp)
                if frame.valid and frame.class_byte == 0x0A:
                    updates = TelemetryDecoder.decode(frame)
                    logger.debug(f"TEMPERATURE updates: {updates}")
                    if updates:
                        updates["timestamp"] = datetime.now()
                        self._telemetry = self._telemetry.model_copy(
                            update=updates
                        )
        except Exception as e:
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

        This method is called by the transport layer when a notification
        arrives. It parses the frame, decodes telemetry, and updates state.

        Args:
            data: Raw notification bytes from BLE

        Example:
            >>> # In transport notification handler
            >>> def on_notification(sender, data):
            ...     telemetry_service.update_from_notification(data)

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
            class_str = (
                f"0x{frame.class_byte:02X}"
                if frame.class_byte is not None
                else "None"
            )
            logger.debug(
                f"Frame parsed: valid={frame.valid}, class={class_str}"
            )

            if not frame.valid or frame.class_byte != 0x0A:
                logger.debug("Not a Class 10 telemetry frame, ignoring")
                return  # Not a Class 10 telemetry frame

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
                basic_updates["timestamp"] = datetime.now()
                self._telemetry = self._telemetry.model_copy(
                    update=basic_updates
                )

            if advanced_updates:
                self._advanced_telemetry = self._advanced_telemetry.model_copy(
                    update=advanced_updates
                )

            # Set stream detection flags based on object type
            if frame.obj_id == 87 and frame.sub_id == 69:  # Motor state
                self._has_motor_state_stream = True
            elif frame.obj_id == 93 and frame.sub_id == 290:  # Flow/pressure
                self._has_flow_stream = True

            logger.debug(
                f"Telemetry updated from notification: {telemetry_data}"
            )

        except Exception as e:
            logger.error(f"Failed to parse telemetry notification: {e}")

    def register_with_transport(self) -> None:
        """
        Register notification callback with transport layer.

        This sets up the telemetry service to receive notifications
        from the transport layer automatically.

        Example:
            >>> service.register_with_transport()
            >>> # Now notifications will automatically update telemetry
        """
        # TODO: This requires the transport layer to support callback registration
        # For now, the client must manually call update_from_notification
        pass
