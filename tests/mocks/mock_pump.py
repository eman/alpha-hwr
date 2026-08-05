"""
Mock pump for testing without hardware.

This module provides a simulated Grundfos ALPHA HWR pump that responds to
protocol commands, allowing comprehensive testing without physical hardware.

The mock pump maintains internal state and responds to commands according to
the GENI protocol specification.
"""

import asyncio
import logging
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from alpha_hwr.constants import ControlMode
from alpha_hwr.protocol import FrameParser
from alpha_hwr.protocol.codec import encode_float_be, encode_uint16_be
from alpha_hwr.protocol.matcher import expected_reply
from alpha_hwr.utils import calc_crc16

logger = logging.getLogger(__name__)


@dataclass
class MockPumpState:
    """Internal state of the mock pump."""

    # Connection state
    connected: bool = False
    authenticated: bool = False

    # Control state
    running: bool = False
    control_mode: int = ControlMode.CONSTANT_SPEED
    setpoint: float | None = 0.0

    # Telemetry values
    voltage: float = 230.0
    current: float = 0.5
    power: float = 50.0
    speed_rpm: float = 0.0
    converter_temp: float = 35.0

    flow_m3h: float = 0.0
    head_m: float = 0.0
    inlet_pressure: float = 1.0
    outlet_pressure: float = 1.5

    media_temp: float = 45.0
    pcb_temp: float = 40.0
    box_temp: float = 38.0

    # Device info
    serial_number: str = "MOCK-12345678"
    model: str = "ALPHA HWR 43-60"
    firmware_version: str = "1.2.3"
    hardware_version: str = "H1"

    # Schedule
    schedule_enabled: bool = False
    schedule_entries: dict = field(default_factory=dict)

    # Clock
    last_synced_time: datetime | None = None

    # Cycle time parameters (Mode 25)
    cycle_on_minutes: int = 6
    cycle_off_minutes: int = 14

    # Response callback
    notification_callback: Callable[[bytes], None] | None = None


class MockPump:
    """
    Mock Grundfos ALPHA HWR pump for testing.

    This class simulates a real pump's behavior, responding to protocol
    commands and maintaining internal state. It's designed to be used in
    unit and integration tests without requiring physical hardware.

    Example:
        >>> pump = MockPump()
        >>> await pump.connect()
        >>> await pump.authenticate()
        >>>
        >>> # Send command and get response
        >>> cmd = FrameBuilder.build_read_request(88, 13300)
        >>> response = await pump.send_command(cmd)
        >>> frame = FrameParser.parse_frame(response)
    """

    def __init__(self):
        """Initialize mock pump with default state."""
        self.state = MockPumpState()
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self._command_buffer = bytearray()

    def set_notification_callback(self, callback: Callable[[bytes], None]):
        """Set callback for notifications (telemetry streams)."""
        self.state.notification_callback = callback

    async def connect(self) -> bool:
        """Simulate BLE connection."""
        self.state.connected = True
        return True

    async def disconnect(self) -> bool:
        """Simulate BLE disconnection."""
        self.state.connected = False
        self.state.authenticated = False
        return True

    async def authenticate(self, fast_mode: bool = False) -> bool:
        """Simulate authentication handshake."""
        if not self.state.connected:
            raise ConnectionError("Not connected")

        # In real implementation, would verify auth packets
        # For mock, just set authenticated flag
        self.state.authenticated = True
        return True

    async def send_command(self, command: bytes, timeout: float = 2.0) -> bytes:
        """
        Send command to mock pump and get response.

        Args:
            command: Raw GENI protocol command
            timeout: Response timeout in seconds

        Returns:
            Response bytes from pump

        Raises:
            ConnectionError: If not connected or authenticated
            TimeoutError: If response not received in time
        """
        if not self.state.connected:
            raise ConnectionError("Not connected")

        # Handle fragmentation
        if len(command) > 0 and command[0] == 0x27:
            # Start of a new command
            self._command_buffer = bytearray(command)
        else:
            # Continuation of previous command
            self._command_buffer.extend(command)

        # Check if we have a complete command
        if len(self._command_buffer) < 2:
            return self._build_ack_response()

        expected_len = self._command_buffer[1] + 4
        if len(self._command_buffer) < expected_len:
            # Still waiting for more fragments
            return self._build_ack_response()

        # Command is complete, process it
        full_command = bytes(self._command_buffer)
        self._command_buffer.clear()

        # Parse incoming command
        frame = FrameParser.parse_frame(full_command)

        if not frame.valid:
            # Return error response for invalid frames
            return self._build_error_response()

        # Route to appropriate handler based on class
        if frame.class_byte == 10:
            raw_data = frame.raw_data
            opspec = raw_data[5] if len(raw_data) > 5 else 0
            # Any OpSpec with bit 7 set is a SET operation
            if opspec & 0x80:
                return await self._handle_class10_set(frame)
            return await self._handle_class10(frame)
        elif frame.class_byte == 7:
            return await self._handle_class7(frame)
        elif frame.class_byte == 3:
            return await self._handle_class3(frame)
        elif frame.class_byte == 2:
            return await self._handle_class2(frame)
        else:
            return self._build_error_response()

    async def _handle_class7(self, frame) -> bytes:
        """Handle Class 7 string operations."""
        raw_data = frame.raw_data
        if len(raw_data) < 7:
            return self._build_error_response()

        cmd_id = raw_data[5]
        string_id = raw_data[6]

        if cmd_id == 0x01:  # ReadString
            value = ""
            if string_id == 9:
                value = self.state.serial_number
            elif string_id == 50:
                value = self.state.firmware_version
            elif string_id == 52:
                value = self.state.hardware_version
            elif string_id == 58:
                value = "1.0.0"

            return self._build_class7_response(string_id, value)

        return self._build_error_response()

    async def _handle_class10_set(self, frame) -> bytes:
        """Handle Class 10 SET operations."""
        raw_data = frame.raw_data
        opspec = raw_data[5]

        # Standard GENI Class 10 SET: bit 7 set, bits 0-5 = length
        # Standard ID order for standard length: SubID(2B) then ObjID(2B)
        # BUT for OpSpec 0xB3 (Long SET), the order is ObjID(1B) then SubID(2B)
        # The long-form SETs (schedule 0xB3, temperature range 0x97, DHW
        # config 0x8F) address the object first as a single byte, then a
        # 16-bit sub-id; the ordinary ones put the 16-bit sub-id first.
        if opspec in (0xB3, 0x97, 0x8F):
            obj_id = raw_data[6]
            sub_id = (raw_data[7] << 8) | raw_data[8]
        else:
            sub_id = (raw_data[6] << 8) | raw_data[7]
            obj_id = (raw_data[8] << 8) | raw_data[9]

        # Control operations (Sub 0x5600, Obj 0x0601)
        if sub_id == 0x5600 and obj_id == 0x0601:
            return self._handle_control_command(frame)

        # Mode change only (Sub 0x5600, Obj 0x0A01). The payload carries
        # operation_mode = NoCmd and set_point = NaN, and the pump applies
        # neither - only the control mode changes.
        if sub_id == 0x5600 and obj_id == 0x0A01:
            # [..][0A][90][56 00][0A 01][2F 01 00 00 07][src][opmode][mode]
            if len(raw_data) >= 18:
                self.state.control_mode = raw_data[17]
            return self._build_ack_response()

        # Cycle Time Write (Obj 91 Sub 421, the live configuration).
        # Frame: [0A][8F][5B][01 A5][03 D9][01][00 00 06][flow f32][on][off]
        # so the periods sit at the end of the APDU, which starts at 4.
        if (
            (opspec & 0x80)
            and sub_id == 0x01A5
            and obj_id == 0x5B
            and len(raw_data) >= 21
        ):
            self.state.cycle_on_minutes = raw_data[19]
            self.state.cycle_off_minutes = raw_data[20]
            return self._build_ack_response()

        # Schedule overview enable/disable (Obj 84, Sub 1)
        # Note: ObjID 84=0x0054, SubID 1=0x0001
        if obj_id == 0x0054 and sub_id == 0x0001:
            # APDU structure for 10-byte data: [Type(3)][Size(2)][Data(5)]
            # enabled is Byte 4 of 5-byte data (index 9 of 10-byte block)
            # Plus 10 bytes for GENI/APDU headers = 19
            if len(raw_data) >= 20:
                self.state.schedule_enabled = raw_data[19] != 0
            return self._build_ack_response()

        # Schedule write (Obj 84, Sub 1000-1004)
        if obj_id == 0x0054 and 1000 <= sub_id <= 1004:
            return self._handle_schedule_write(sub_id, raw_data)

        # Clock SET (Sub 0x5E00, Obj 0x6401)
        if sub_id == 0x5E00 and obj_id == 0x6401:
            return self._handle_set_clock(raw_data)

        return self._build_ack_response()

    def _handle_set_clock(self, raw_data: bytes) -> bytes:
        """Handle Class 10 SET clock command.

        The SET frame payload contains a Type 322 header (6 bytes)
        followed by [Year(2BE)][Month][Day][Hour][Min][Sec][pad(3)].
        In the full raw_data, the APDU starts at byte 4:
        [STX][LEN][DST][SRC][Class][OpSpec][SubH][SubL][ObjH][ObjL][Type322...]
        Type 322 data starts at offset 10, datetime at offset 16.
        """
        # Type322 header is 6 bytes starting at offset 10
        # DateTime starts at offset 16: [Year(2)][Mon][Day][Hr][Min][Sec]
        if len(raw_data) >= 23:
            from datetime import datetime

            yr = (raw_data[16] << 8) | raw_data[17]
            mo, da, hr, mi, sc = raw_data[18:23]
            try:
                self.state.last_synced_time = datetime(  # noqa: DTZ001
                    yr, mo, da, hr, mi, sc
                )  # pump wall clock is naive
            except ValueError:
                pass
        return self._build_ack_response()

    def _handle_schedule_write(self, sub_id: int, raw_data: bytes) -> bytes:
        """Handle schedule layer write."""
        # OpSpec 0xB3: SET with long payload
        # Structure: [Header(9)][Reserved(1)][Type(3)][Size(2)][Data(42)]
        # Total offset to data = 15
        if len(raw_data) >= 15 + 42:
            data = raw_data[15 : 15 + 42]
            layer = sub_id - 1000
            if 0 <= layer < 5:
                self.state.schedule_entries[layer] = data
                logger.debug(
                    f"MockPump: Written schedule layer {layer}: {data.hex()[:20]}..."
                )
                return self._build_ack_response()

        logger.warning(f"MockPump: Invalid schedule write: len={len(raw_data)}")
        return self._build_error_response()

    async def _handle_class10(self, frame) -> bytes:
        """Handle Class 10 DataObject operations."""
        # For Class 10 READ requests (OpSpec 0x03), extract identifiers
        # Request format: [Start][Len][SvcH][SvcL][Class][OpSpec][ObjID][SubH][SubL][CRC]

        raw_data = frame.raw_data
        if len(raw_data) >= 10 and raw_data[5] == 0x03:
            obj_id = raw_data[6]
            sub_id = (raw_data[7] << 8) | raw_data[8]
        else:
            # frame.sub_id and frame.obj_id are already correctly parsed by FrameParser
            # which assumes SubID (6-7) and ObjID (8-9).
            sub_id = frame.sub_id
            obj_id = frame.obj_id

        # Control operations (Sub 0x5600, Obj 0x0601)
        if sub_id == 0x5600 and obj_id == 0x0601:
            return self._handle_control_command(frame)

        # Operation status (Obj 86). Sub 6 is the request object and Sub 7
        # the prioritized state; on hardware they differ only in
        # control_source, which Sub 6 reports as 0 (Undefined) whatever the
        # pump is actually doing. Sub 10 is the mode-request object, which
        # reads back the no-op sentinels it is written with.
        if obj_id == 0x0056 and sub_id in (0x0006, 0x0007, 0x000A):
            return self._build_setpoint_info_response(sub_id)

        # Motor state (Obj 87, Sub 69)
        if obj_id == 0x0057 and sub_id == 0x0045:
            return self._build_motor_state_response()

        # Flow/pressure (Obj 93, Sub 290)
        if obj_id == 0x005D and sub_id == 0x0122:
            return self._build_flow_pressure_response()

        # Temperature (Obj 93, Sub 300)
        if obj_id == 0x005D and sub_id == 0x012C:
            return self._build_temperature_response()

        # Statistics (Obj 93, Sub 1)
        if obj_id == 0x005D and sub_id == 0x0001:
            return self._build_statistics_response()

        # Schedule overview (Obj 84, Sub 1)
        if obj_id == 0x0054 and sub_id == 0x0001:
            return self._build_schedule_overview_response()

        # Schedule entries (Obj 84, Sub 1000-1004)
        if obj_id == 0x0054 and 1000 <= sub_id <= 1004:
            return self._build_schedule_entries_response(sub_id)

        # Clock read (Obj 94, Sub 101)
        if obj_id == 0x005E and sub_id == 0x0065:
            return self._build_clock_response()

        # Mode 25 Cycle Time Config (Obj 91, Sub 421)
        if obj_id == 91 and sub_id == 421:
            # dhw_on_off_control_configuration_obj, as measured:
            # [00 00 06][flow setpoint f32, m3/s][on minutes][off minutes]
            payload = bytearray([0x00, 0x00, 0x06])
            payload.extend(bytes([0x38, 0x84, 0x4F, 0x30]))  # 0.227 m3/h
            payload.append(self.state.cycle_on_minutes)
            payload.append(self.state.cycle_off_minutes)
            return self._build_class10_response(sub_id, obj_id, bytes(payload))

        # Main User Settings (Obj 91, Sub 430)
        if obj_id == 91 and sub_id == 430:
            return self._build_user_settings_response()

        # Timestamp map (Obj 88, Sub 13300/13301)
        if obj_id == 88 and sub_id in (13300, 13301):
            return self._build_timestamp_map_response(sub_id)

        # Event log metadata (Obj 88, Sub 10199)
        if obj_id == 88 and sub_id == 10199:
            return self._build_event_log_metadata_response()

        # Event log entries (Obj 88, Sub 10200-10219)
        if obj_id == 88 and 10200 <= sub_id <= 10219:
            return self._build_event_log_entry_response(sub_id)

        # Trend data (Obj 53, Sub 451-454)
        if obj_id == 53 and 451 <= sub_id <= 454:
            return self._build_trend_data_response(sub_id)

        # Default: return empty response
        return self._build_class10_response(sub_id, obj_id, b"")

    async def _handle_class3(self, frame) -> bytes:
        """Handle Class 3 legacy register operations."""
        from alpha_hwr.protocol.codec import decode_float_be

        # For Class 3, frame structure is:
        # [Start][Len][SvcH][SvcL][Class][OpSpec][Register...][Value...][CRC]

        raw_data = frame.raw_data
        if len(raw_data) < 7:
            return self._build_error_response()

        op_length_byte = raw_data[5]
        op_spec = (op_length_byte >> 6) & 0x03
        data_length = op_length_byte & 0x3F

        # Run-state commands: [03][81][id]. These carry no mode and no
        # setpoint, so they change only whether the motor runs. The pump
        # answers [03 00] for a command it executed; it sends no
        # notification afterwards, so the caller has to read the state back.
        if op_length_byte == 0x81 and len(raw_data) >= 7:
            command_id = raw_data[6]
            if command_id == self.CLASS3_START:
                self.state.running = True
                self._apply_running_telemetry()
                return self._build_class3_ack()
            if command_id == self.CLASS3_STOP:
                self.state.running = False
                self._apply_stopped_telemetry()
                return self._build_class3_ack()
            # Anything else is described rather than executed.
            return self._build_class3_ack(accepted=False)

        # Read operations (op_spec = 0 or 1)
        if op_spec in (0x00, 0x01):
            return self._build_class3_response(b"\x00\x00\x00\x00")

        # Write operations (op_spec = 2)
        if op_spec == 0x02:
            payload = frame.payload
            if data_length >= 5 and len(payload) >= 5:
                reg_index = payload[0]
                value_bytes = payload[1:5]

                if reg_index == 0x04:
                    value = decode_float_be(value_bytes)
                    if value is not None:
                        self.state.setpoint = value
                        self.state.control_mode = ControlMode.CONSTANT_SPEED
                elif reg_index == 0x18:
                    value = decode_float_be(value_bytes)
                    if value is not None:
                        self.state.setpoint = value
                        self.state.control_mode = ControlMode.CONSTANT_PRESSURE
                elif reg_index == 0x1C:
                    value = decode_float_be(value_bytes)
                    if value is not None:
                        self.state.setpoint = value
                        self.state.control_mode = ControlMode.CONSTANT_FLOW

            return self._build_ack_response()

        # Command operations (op_spec = 3)
        if op_spec == 0x03:
            return self._build_ack_response()

        return self._build_error_response()

    async def _handle_class2(self, frame) -> bytes:
        """Handle Class 2 info operations."""
        return self._build_class2_response(b"\x00" * 10)

    def _handle_control_command(self, frame) -> bytes:
        """Handle pump control commands (start/stop/mode change)."""
        from alpha_hwr.protocol.codec import decode_float_be

        payload = frame.payload

        if len(payload) < 8:
            return self._build_error_response()

        # Parse control payload: [Header(6 bytes)][Flag][Mode][Setpoint(4)]
        # From ControlService: [0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, Flag, Mode]
        flag = payload[6]  # 0x00 = start, 0x01 = stop
        mode = payload[7]

        if flag == 0x00:
            # Start command
            self.state.running = True
            self.state.control_mode = mode

            # Extract setpoint if available (12-byte payload)
            if len(payload) >= 12:
                self.state.setpoint = decode_float_be(payload, 8)

            self.state.speed_rpm = 1500.0  # Simulate running
            self.state.flow_m3h = 2.5
            self.state.current = 1.5
            self.state.power = 300.0
        elif flag == 0x01:
            # Stop command
            self.state.running = False
            self.state.speed_rpm = 0.0
            self.state.flow_m3h = 0.0
            self.state.current = 0.5
            self.state.power = 50.0

        return self._build_ack_response()

    def _handle_schedule_command(self, frame) -> bytes:
        """Handle schedule read/write operations."""
        # For now, return empty schedule data
        return self._build_class10_response(
            frame.sub_id, frame.obj_id, b"\x00" * 20
        )

    def _build_motor_state_response(self) -> bytes:
        """Build Class 10 motor state telemetry response."""
        # Build payload with motor state data
        payload = bytearray()
        payload.extend(encode_float_be(self.state.voltage))  # 0-3: Voltage
        payload.extend(bytes(4))  # 4-7: Padding
        payload.extend(encode_float_be(self.state.current))  # 8-11: Current
        payload.extend(bytes(4))  # 12-15: Padding
        payload.extend(encode_float_be(self.state.power))  # 16-19: Power
        payload.extend(encode_float_be(self.state.speed_rpm))  # 20-23: Speed
        payload.extend(
            encode_float_be(self.state.converter_temp)
        )  # 24-27: Temp

        return self._build_class10_response(69, 87, bytes(payload))

    def _build_flow_pressure_response(self) -> bytes:
        """Build Class 10 flow/pressure telemetry response."""
        payload = bytearray()
        payload.extend(encode_float_be(self.state.flow_m3h))
        payload.extend(encode_float_be(self.state.head_m))
        payload.extend(encode_float_be(self.state.inlet_pressure))
        payload.extend(encode_float_be(self.state.outlet_pressure))

        return self._build_class10_response(290, 93, bytes(payload))

    def _build_temperature_response(self) -> bytes:
        """Build Class 10 temperature telemetry response."""
        payload = bytearray()
        payload.extend(encode_float_be(self.state.media_temp))
        payload.extend(encode_float_be(self.state.pcb_temp))
        payload.extend(encode_float_be(self.state.box_temp))

        return self._build_class10_response(300, 93, bytes(payload))

    def _build_statistics_response(self) -> bytes:
        """Build Class 10 statistics response (Obj 93, Sub 1)."""
        payload = bytearray()
        payload.extend(bytes([0x00, 0x00, 0x00]))  # Header
        payload.extend(struct.pack(">I", 100))  # Starts
        payload.extend(struct.pack(">H", 5))  # Starts 1h
        payload.extend(struct.pack(">H", 10))  # Starts 24h
        payload.extend(struct.pack(">I", 36000))  # Operating time (10 hours)

        return self._build_class10_response(1, 93, bytes(payload))

    def _build_schedule_overview_response(self) -> bytes:
        """Build Class 10 schedule overview response (Obj 84, Sub 1)."""
        payload = bytearray()
        payload.extend(bytes([0x00, 0x00, 0x00]))  # Header
        payload.extend(bytes([0x05, 0x05, 0x05, 0x05]))  # Capabilities
        payload.append(0x01 if self.state.schedule_enabled else 0x00)  # Enabled
        payload.append(0x02)  # Default action
        payload.extend(encode_float_be(1.5))  # Base setpoint

        return self._build_class10_response(1, 84, bytes(payload))

    def _build_schedule_entries_response(self, sub_id: int) -> bytes:
        """Build Class 10 schedule entries response (Obj 84, Sub 1000-1004)."""
        payload = bytearray()
        payload.extend(bytes([0x00, 0x00, 0x00]))  # Header

        layer = sub_id - 1000
        if layer in self.state.schedule_entries:
            payload.extend(self.state.schedule_entries[layer])
        else:
            # 7 days * 6 bytes = 42 bytes of zeros
            for i in range(7):
                payload.extend(bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))

        return self._build_class10_response(sub_id, 84, bytes(payload))

    def _build_clock_response(self) -> bytes:
        """Build Class 10 clock response (Obj 94, Sub 101)."""
        from datetime import datetime

        # Pump wall clock is naive local time, never UTC.
        dt = self.state.last_synced_time or datetime.now()  # noqa: DTZ005

        payload = bytearray()
        payload.extend(bytes([0x00, 0x00]))  # Status (valid)
        payload.append(0x07)  # Length
        payload.extend(struct.pack(">H", dt.year))
        payload.append(dt.month)
        payload.append(dt.day)
        payload.append(dt.hour)
        payload.append(dt.minute)
        payload.append(dt.second)

        return self._build_class10_response(101, 94, bytes(payload))

    def _build_user_settings_response(self) -> bytes:
        """
        Build Class 10 User Settings response (Obj 91, Sub 430).

        Format: [00 00 0E][01 42 0C][00 00 42 1E DE 4C][OFF][3C 02][ON][01]
        """
        payload = bytearray([0x00, 0x00, 0x0E])  # Header
        payload.extend([0x01, 0x42, 0x0C])  # Magic
        payload.extend([0x00, 0x00, 0x42, 0x1E, 0xDE, 0x4C])  # Magic
        payload.append(self.state.cycle_off_minutes)  # Offset 12
        payload.extend([0x3C, 0x02])  # Magic
        payload.append(self.state.cycle_on_minutes)  # Offset 15
        payload.append(0x01)  # Suffix

        return self._build_class10_response(430, 91, bytes(payload))

    #: Operation mode values, as the pump reports them.
    OPERATION_MODE_AUTO = 0x00
    OPERATION_MODE_STOP = 0x01
    OPERATION_MODE_NO_CMD = 0x06

    def _build_setpoint_info_response(self, sub_id: int = 7) -> bytes:
        """
        Build a Class 10 operation-status response for Object 86.

        Format: ``[00 00 07][control_source][operation_mode][control_mode]
        [setpoint f32 BE]``.

        The three sub-IDs answer differently, as measured on hardware:

        - **Sub 6** (request object) reports ``control_source = 0``
          regardless of what the pump is doing. Reading remote/local state
          from here is why it always looked Undefined.
        - **Sub 7** (prioritized state) reports the real source - ``1`` for
          Local/Panel, ``2`` for Remote/Digital.
        - **Sub 10** (mode request) reads back the no-op sentinels it is
          written with: ``operation_mode = NoCmd`` and ``set_point = NaN``.
        """
        payload = bytearray([0x00, 0x00, 0x07])

        if sub_id == 0x000A:
            payload.append(0x00)  # control_source = Undefined
            payload.append(self.OPERATION_MODE_NO_CMD)
            payload.append(self.state.control_mode)
            payload.extend(b"\x7f\xff\xff\xff")  # set_point = NaN
            return self._build_class10_response(sub_id, 86, bytes(payload))

        payload.append(0x01 if sub_id == 0x0007 else 0x00)  # control_source
        payload.append(
            self.OPERATION_MODE_AUTO
            if self.state.running
            else self.OPERATION_MODE_STOP
        )
        payload.append(self.state.control_mode)
        payload.extend(encode_float_be(self.state.setpoint or 0.0))

        return self._build_class10_response(sub_id, 86, bytes(payload))

    def _build_timestamp_map_response(self, sub_id: int) -> bytes:
        """Build timestamp map response."""
        # Generate 10 mock timestamps
        base_time = 1700000000
        payload = bytearray()
        for i in range(10):
            ts = base_time + (i * 3600)  # 1 hour intervals
            payload.extend(struct.pack(">I", ts))

        return self._build_class10_response(sub_id, 88, bytes(payload))

    def _build_trend_data_response(self, sub_id: int) -> bytes:
        """Build trend data response (Type 946 - TrendData1B, 29 bytes)."""
        # Current value (float, 4 bytes)
        # Last 10 cycle values (10 bytes, 1 byte each)
        # Next counter (1 byte)
        # Next 100-cycle value (float, 4 bytes)
        # Last 10 of 100-cycle values (10 bytes, 1 byte each)

        payload = bytearray()
        payload.extend(bytes([0x00, 0x00, 0x00]))  # Header
        payload.extend(encode_float_be(2.5))  # Current value (451=flow)
        payload.extend(bytes([i for i in range(10)]))  # 10 cycle values
        payload.append(0x05)  # Next counter
        payload.extend(encode_float_be(3.0))  # Next 100-cycle value
        payload.extend(bytes([10 + i for i in range(10)]))  # 100 cycle values

        return self._build_class10_response(sub_id, 53, bytes(payload))

    def _build_event_log_metadata_response(self) -> bytes:
        """Build event log metadata response (Obj 88, Sub 10199)."""
        payload = bytearray()
        payload.extend(bytes([0x00, 0x00, 0x00]))  # Header
        payload.extend(struct.pack(">H", 150))  # Current cycle
        payload.extend(struct.pack(">H", 5))  # Available entries
        payload.extend(struct.pack(">H", 20))  # Max size
        payload.append(0x00)  # Reserved

        return self._build_class10_response(10199, 88, bytes(payload))

    def _build_event_log_entry_response(self, sub_id: int) -> bytes:
        """Build event log entry response (Obj 88, Sub 10200-10219)."""
        payload = bytearray()
        payload.extend(bytes([0x00, 0x00, 0x00]))  # Header

        # 16-byte entry
        entry = bytearray(16)
        entry[4] = 145  # Cycle counter
        entry[6] = 0x48  # Mode
        entry[9] = 0x01  # Event type (start)
        # Timestamp: Jan 31, 2026 12:00:00 UTC
        entry[10:14] = struct.pack(">I", 1769860800)

        payload.extend(entry)
        return self._build_class10_response(sub_id, 88, bytes(payload))

    def _build_class10_response(
        self, sub_id: int, obj_id: int, payload: bytes
    ) -> bytes:
        """
        Build a generic Class 10 response frame.

        The identifier fields carry the type code the real pump answers
        that object with, not an echo of the request. Measured against an
        ALPHA HWR on 2026-08-04; see ``protocol.matcher.RESPONSE_IDENTIFIERS``.
        This mock used to echo the request, which no reply from the real
        device ever does - so any matching logic it exercised was being
        tested against behaviour the pump does not have.
        """
        identifiers = expected_reply(obj_id, sub_id)
        field_a, field_b = identifiers if identifiers else (sub_id, obj_id)

        # Build APDU: [Class][OpSpec][A-H][A-L][B-H][B-L][Payload]
        apdu = bytearray([0x0A, 0x90])
        apdu.extend(encode_uint16_be(field_a))
        apdu.extend(encode_uint16_be(field_b))
        apdu.extend(payload)

        # Build frame: [Start][Length][SvcH][SvcL][APDU][CRC]
        # Length field = bytes from after length byte to before CRC
        # = Service ID (2) + APDU length
        length = len(apdu) + 2  # +2 for service ID bytes only (not CRC)
        frame = bytearray([0x24, length, 0xE7, 0xF8])
        frame.extend(apdu)

        # Add CRC
        crc_data = frame[1:]  # Exclude start byte
        crc = calc_crc16(bytes(crc_data))
        frame.extend(encode_uint16_be(crc))

        return bytes(frame)

    #: Class 3 run-state command IDs.
    CLASS3_STOP = 0x05
    CLASS3_START = 0x06

    def _apply_running_telemetry(self) -> None:
        """Move the simulated readings to what a running pump reports."""
        self.state.speed_rpm = 1500.0
        self.state.flow_m3h = 2.5
        self.state.current = 1.5
        self.state.power = 300.0

    def _apply_stopped_telemetry(self) -> None:
        """Move the simulated readings to what a stopped pump reports."""
        self.state.speed_rpm = 0.0
        self.state.flow_m3h = 0.0
        self.state.current = 0.5
        self.state.power = 50.0

    def _build_class3_ack(self, accepted: bool = True) -> bytes:
        """
        Build the bare acknowledgement a Class 3 command draws.

        ``[03 00]`` means the pump executed it; ``[03 01 xx]`` means it
        only described the data item and did nothing. The frame is far
        shorter than an ordinary response and carries no identifiers, so
        the class byte is all a caller has to match on.
        """
        apdu = (
            bytearray([0x03, 0x00])
            if accepted
            else bytearray([0x03, 0x01, 0xAC])
        )
        frame = bytearray([0x24, len(apdu) + 2, 0xE7, 0xF8])
        frame.extend(apdu)
        frame.extend(encode_uint16_be(calc_crc16(bytes(frame[1:]))))
        return bytes(frame)

    def _build_class3_response(self, payload: bytes) -> bytes:
        """Build Class 3 response frame."""
        apdu = bytearray([0x03, 0x81])  # Class 3, response OpSpec
        apdu.extend(payload)

        # Length = Service ID (2) + APDU length
        length = len(apdu) + 2
        frame = bytearray([0x24, length, 0xE7, 0xF8])
        frame.extend(apdu)

        crc = calc_crc16(bytes(frame[1:]))
        frame.extend(encode_uint16_be(crc))

        return bytes(frame)

    def _build_class7_response(self, string_id: int, value: str) -> bytes:
        """Build Class 7 response frame."""
        val_bytes = value.encode("utf-8") + b"\x00"
        apdu = bytearray([0x07, 0x81, string_id])
        apdu.extend(val_bytes)

        length = len(apdu) + 2
        frame = bytearray([0x24, length, 0xE7, 0xF8])
        frame.extend(apdu)

        crc = calc_crc16(bytes(frame[1:]))
        frame.extend(encode_uint16_be(crc))

        return bytes(frame)

    def _build_class2_response(self, payload: bytes) -> bytes:
        """Build Class 2 response frame."""
        apdu = bytearray([0x02, 0x81])
        apdu.extend(payload)

        length = len(apdu) + 2
        frame = bytearray([0x24, length, 0xE7, 0xF8])
        frame.extend(apdu)

        crc = calc_crc16(bytes(frame[1:]))
        frame.extend(encode_uint16_be(crc))

        return bytes(frame)

    def _build_ack_response(self) -> bytes:
        """Build simple acknowledgment response."""
        # Class 10 ACK: [Start][Len][Svc(2)][Class=0x0A][OpSpec=0x01][CRC(2)]
        # Length = Svc(2) + Class(1) + OpSpec(1) = 4
        frame = bytearray([0x24, 0x04, 0xE7, 0xF8, 0x0A, 0x01])
        crc = calc_crc16(bytes(frame[1:]))
        frame.extend(encode_uint16_be(crc))
        return bytes(frame)

    def _build_error_response(self) -> bytes:
        """Build error response."""
        # Length = Svc(2) + Class(1) + OpSpec(1) + Error(1) = 5
        frame = bytearray([0x24, 0x05, 0xE7, 0xF8, 0xFF, 0xFF, 0x00])
        crc = calc_crc16(bytes(frame[1:]))
        frame.extend(encode_uint16_be(crc))
        return bytes(frame)

    async def start_telemetry_stream(self, interval: float = 1.0):
        """
        Start streaming telemetry notifications.

        Simulates the pump's behavior of continuously sending telemetry
        updates via notifications.

        Args:
            interval: Time between notifications in seconds
        """
        while self.state.connected and self.state.notification_callback:
            # Send motor state notification
            motor_response = self._build_motor_state_response()
            self.state.notification_callback(motor_response)

            await asyncio.sleep(interval)

            # Send flow/pressure notification
            if self.state.running:
                flow_response = self._build_flow_pressure_response()
                self.state.notification_callback(flow_response)

            await asyncio.sleep(interval)
