"""
GENI telemetry decoder.

This module decodes Class 10 DataObject telemetry notifications from the pump.
It extracts and validates sensor data from raw payload bytes.

Telemetry Objects
-----------------
The Alpha HWR pump sends telemetry using Class 10 DataObjects:

1. **Motor State** (Obj 87, Sub 69) - Type 256
   - Grid voltage, current, power, speed, converter temperature

2. **Flow/Pressure** (Obj 93, Sub 290) - Type 565
   - Flow rate, head, inlet pressure, outlet pressure

3. **Temperature** (Obj 93, Sub 300) - Type 534
   - Media temperature, PCB temperature, control box temperature

4. **Alarms/Warnings** (Obj 88, Sub 0/11) - Type 570
   - Active alarm codes and warning codes

Payload Format
--------------
All telemetry payloads use big-endian encoding:
- Floats: IEEE 754 single-precision (4 bytes)
- Integers: Big-endian uint16 (2 bytes)

Values are validated against reasonable ranges to detect corruption.

For complete protocol reference, see:
- docs/protocol/telemetry_streams.md
- docs/protocol/wire_format.md

Implementation Notes for Other Languages
----------------------------------------
This decoder is designed to be easily portable to other languages:

1. **Stateless Decoding**: Each payload decoded independently
2. **Range Validation**: Always validate against physical limits
3. **Graceful Degradation**: Return partial data if some fields are corrupted
4. **Type Safety**: Use dictionaries/structs to ensure type correctness

Example in C:
```c
typedef struct {
    bool has_voltage;
    float voltage_ac_v;
    bool has_current;
    float current_a;
    bool has_power;
    float power_w;
    bool has_speed;
    float speed_rpm;
    bool has_converter_temp;
    float converter_temperature_c;
} MotorState;

MotorState decode_motor_state(const uint8_t* payload, size_t len) {
    MotorState state = {0};

    // Grid voltage (offset 0)
    if (len >= 4) {
        float voltage = decode_float_be(payload, 0);
        if (voltage >= 0 && voltage <= 300) {
            state.has_voltage = true;
            state.voltage_ac_v = voltage;
        }
    }

    // Current (offset 8)
    if (len >= 12) {
        float current = decode_float_be(payload, 8);
        if (current >= 0 && current <= 10) {
            state.has_current = true;
            state.current_a = current;
        }
    }

    // Continue for other fields...

    return state;
}
```

Example in JavaScript:
```javascript
class MotorState {
    constructor() {
        this.voltageAcV = null;
        this.currentA = null;
        this.powerW = null;
        this.speedRpm = null;
        this.converterTemperatureC = null;
    }
}

function decodeMotorState(payload) {
    const state = new MotorState();

    // Grid voltage (offset 0)
    if (payload.length >= 4) {
        const voltage = decodeFloatBE(payload, 0);
        if (voltage >= 0 && voltage <= 300) {
            state.voltageAcV = voltage;
        }
    }

    // Current (offset 8)
    if (payload.length >= 12) {
        const current = decodeFloatBE(payload, 8);
        if (current >= 0 && current <= 10) {
            state.currentA = current;
        }
    }

    // Continue for other fields...

    return state;
}
```
"""

import logging
import struct
from typing import Any

from .codec import decode_float_be, decode_uint16_be
from .frame_parser import ParsedFrame

logger = logging.getLogger(__name__)


class TelemetryDecoder:
    """
    Decodes telemetry from Class 10 DataObject notifications.

    All methods are static for easy porting to other languages.
    """

    @staticmethod
    def decode_motor_state(payload: bytes) -> dict[str, float]:
        """
        Decode motor state telemetry (Obj 87, Sub 69).

        This object contains electrical and mechanical motor data:
        - Grid voltage (AC input)
        - Current draw
        - DC power consumption
        - Motor speed (RPM)
        - Converter temperature

        Payload Offsets:
        - 0-3: Grid voltage (float, volts, 0-300V)
        - 8-11: Current (float, amps, 0-10A)
        - 16-19: DC power consumption (float, watts, 0-1000W)
        - 20-23: Absolute speed (float, RPM, 0-6000 RPM)
        - 24-27: Converter temperature (float, °C, -20 to 120°C)

        Args:
            payload: Raw payload bytes from Class 10 frame

        Returns:
            Dictionary with decoded values (only includes valid fields)

        Examples:
            >>> # Parse frame first
            >>> frame = FrameParser.parse_frame(notification_data)
            >>> if frame.obj_id == 87 and frame.sub_id == 69:
            ...     motor_data = TelemetryDecoder.decode_motor_state(frame.payload)
            ...     print(f"Voltage: {motor_data.get('voltage_ac_v')}V")
            ...     print(f"Current: {motor_data.get('current_a')}A")
            ...     print(f"Power: {motor_data.get('power_w')}W")
            ...     print(f"Speed: {motor_data.get('speed_rpm')} RPM")

        Implementation Notes:
            - All floats are big-endian IEEE 754
            - Values outside physical limits are discarded
            - Missing fields are not included in result
            - Offsets 4-7, 12-15 are reserved (not documented)
        """
        data: dict[str, float] = {}

        # Grid voltage (offset 0)
        if len(payload) >= 4:
            voltage = decode_float_be(payload, 0)
            if voltage is not None and 0 <= voltage <= 300:
                data["voltage_ac_v"] = voltage

        # Current (offset 8)
        if len(payload) >= 12:
            current = decode_float_be(payload, 8)
            if current is not None and 0 <= current <= 10:
                data["current_a"] = current

        # DC power consumption (offset 16)
        if len(payload) >= 20:
            power = decode_float_be(payload, 16)
            if power is not None and 0 <= power <= 1000:
                data["power_w"] = power

        # Absolute speed (offset 20)
        if len(payload) >= 24:
            speed = decode_float_be(payload, 20)
            if speed is not None and 0 <= speed <= 6000:
                data["speed_rpm"] = speed

        # Converter temperature (offset 24)
        if len(payload) >= 28:
            temp = decode_float_be(payload, 24)
            if temp is not None and -20 <= temp <= 120:
                data["converter_temperature_c"] = temp

        return data

    @staticmethod
    def decode_flow_pressure(payload: bytes) -> dict[str, float]:
        """
        Decode flow and pressure telemetry (Obj 93, Sub 290).

        This object contains hydraulic performance data:
        - Flow rate
        - Head (pressure height)
        - Inlet pressure
        - Outlet pressure

        Payload Offsets:
        - 0-3: Flow rate (float, m³/h, 0-10 m³/h)
        - 4-7: Head (float, meters, 0-20m)
        - 8-11: Inlet pressure (float, bar, 0-20 bar)
        - 12-15: Outlet pressure (float, bar, 0-20 bar)

        Args:
            payload: Raw payload bytes from Class 10 frame

        Returns:
            Dictionary with decoded values (only includes valid fields)

        Examples:
            >>> frame = FrameParser.parse_frame(notification_data)
            >>> if frame.obj_id == 93 and frame.sub_id == 290:
            ...     flow_data = TelemetryDecoder.decode_flow_pressure(frame.payload)
            ...     print(f"Flow: {flow_data.get('flow_m3h')} m³/h")
            ...     print(f"Head: {flow_data.get('head_m')} m")
            ...     print(f"Inlet: {flow_data.get('inlet_pressure_bar')} bar")
            ...     print(f"Outlet: {flow_data.get('outlet_pressure_bar')} bar")

        Implementation Notes:
            - All floats are big-endian IEEE 754
            - Values outside physical limits are discarded
            - Flow rate is volumetric (cubic meters per hour)
            - Head is equivalent pressure height in meters
        """
        data: dict[str, float] = {}

        # Flow rate (offset 0)
        if len(payload) >= 4:
            flow = decode_float_be(payload, 0)
            if flow is not None and 0 <= flow <= 10:
                data["flow_m3h"] = flow

        # Head (offset 4)
        if len(payload) >= 8:
            head = decode_float_be(payload, 4)
            if head is not None and 0 <= head <= 20:
                data["head_m"] = head

        # Inlet pressure (offset 8)
        if len(payload) >= 12:
            p_in = decode_float_be(payload, 8)
            if p_in is not None and 0 <= p_in <= 20:
                data["inlet_pressure_bar"] = p_in

        # Outlet pressure (offset 12)
        if len(payload) >= 16:
            p_out = decode_float_be(payload, 12)
            if p_out is not None and 0 <= p_out <= 20:
                data["outlet_pressure_bar"] = p_out

        return data

    @staticmethod
    def decode_temperature(payload: bytes) -> dict[str, float]:
        """
        Decode temperature telemetry (Obj 93, Sub 300).

        This object contains temperature readings from various sensors:
        - Media temperature (water/fluid being pumped)
        - PCB temperature (circuit board)
        - Control box temperature (enclosure)

        Payload Offsets:
        - 0-3: Media temperature (float, °C, -20 to 100°C)
        - 4-7: PCB temperature (float, °C, -20 to 150°C)
        - 8-11: Control box temperature (float, °C, -20 to 150°C)

        Args:
            payload: Raw payload bytes from Class 10 frame

        Returns:
            Dictionary with decoded values (only includes valid fields)

        Examples:
            >>> frame = FrameParser.parse_frame(notification_data)
            >>> if frame.obj_id == 93 and frame.sub_id == 300:
            ...     temp_data = TelemetryDecoder.decode_temperature(frame.payload)
            ...     print(f"Media: {temp_data.get('media_temperature_c')}°C")
            ...     print(f"PCB: {temp_data.get('pcb_temperature_c')}°C")
            ...     print(f"Box: {temp_data.get('control_box_temperature_c')}°C")

        Implementation Notes:
            - All floats are big-endian IEEE 754
            - Values outside physical limits are discarded
            - PCB and control box limits are higher due to electronics
            - Media temperature is water temperature (typical HVAC range)
        """
        data: dict[str, float] = {}

        # Media temperature (offset 0)
        if len(payload) >= 4:
            temp = decode_float_be(payload, 0)
            if temp is not None and -20 <= temp <= 100:
                data["media_temperature_c"] = temp

        # PCB temperature (offset 4)
        if len(payload) >= 8:
            temp = decode_float_be(payload, 4)
            if temp is not None and -20 <= temp <= 150:
                data["pcb_temperature_c"] = temp

        # Control box temperature (offset 8)
        if len(payload) >= 12:
            temp = decode_float_be(payload, 8)
            if temp is not None and -20 <= temp <= 150:
                data["control_box_temperature_c"] = temp

        return data

    @staticmethod
    def decode_alarms_warnings(
        payload: bytes, is_alarms: bool = True
    ) -> list[int]:
        """
        Decode alarm/warning codes (Obj 88, Sub 0 or 11).

        This object contains active alarm or warning codes as a list of uint16 values.
        Non-zero codes indicate active conditions.

        Payload Format:
        - Array of uint16 values (big-endian)
        - Each 2-byte pair is one code
        - Code 0 means "no alarm/warning" (filtered out)

        Args:
            payload: Raw payload bytes from Class 10 frame
            is_alarms: True for alarms (Sub 0), False for warnings (Sub 11)

        Returns:
            List of active alarm/warning codes (non-zero values only)

        Examples:
            >>> frame = FrameParser.parse_frame(notification_data)
            >>> if frame.obj_id == 88:
            ...     if frame.sub_id == 0:  # Alarms
            ...         codes = TelemetryDecoder.decode_alarms_warnings(frame.payload)
            ...         if codes:
            ...             print(f"Active alarms: {codes}")
            ...     elif frame.sub_id == 11:  # Warnings
            ...         codes = TelemetryDecoder.decode_alarms_warnings(frame.payload, False)
            ...         if codes:
            ...             print(f"Active warnings: {codes}")

        Implementation Notes:
            - Payload is an array of uint16 (2 bytes each)
            - Big-endian byte order
            - Zero codes are filtered out (indicate "no condition")
            - Same format for both alarms and warnings
        """
        codes: list[int] = []

        # Parse uint16 array
        for i in range(0, len(payload), 2):
            if i + 2 <= len(payload):
                code = decode_uint16_be(payload, i)
                if code is not None and code != 0:
                    codes.append(code)

        return codes

    @staticmethod
    def decode_legacy_packet(packet: bytes) -> dict[str, Any]:
        """
        Decode telemetry using legacy pattern matching.

        Some pumps send telemetry in custom object formats that don't match
        the standard GENI profile objects. This method searches for known
        magic byte patterns in the packet to extract telemetry.

        Legacy patterns:
        - \\x2f\\x01: Setpoint/Reference speed (Object 0x012F)
        - \\x2e\\x01: Flow/Head data (Object 0x012E)
        - \\x03\\x00\\x01: Custom electrical object (3, 1)
        - \\x2d\\x01: Custom speed object (0x2D01, 1)
        - \\x16\\x02: Custom temperature object (0x1602, 2)

        Args:
            packet: Full GENI packet bytes

        Returns:
            Dictionary with decoded telemetry data
        """
        data: dict[str, Any] = {}

        # Legacy: Look for Obj 2F01 (Setpoint/Reference)
        idx = packet.find(b"\x2f\x01")
        if idx != -1 and idx + 10 <= len(packet):
            try:
                # 2F01 payload is often Reference Speed (Setpoint)
                rpm_raw = struct.unpack(">H", packet[idx + 8 : idx + 10])[0]
                # Map to setpoint_rpm instead of speed_rpm
                data["setpoint_rpm"] = rpm_raw / 10.0
            except struct.error:
                pass

        # Legacy: Look for Obj 2E01 (Flow/Head)
        idx = packet.find(b"\x2e\x01")
        if idx != -1 and idx + 10 <= len(packet) and "flow_m3h" not in data:
            try:
                for offset in [2, 4, 6, 8]:
                    if idx + offset + 8 <= len(packet):
                        f1 = struct.unpack(
                            ">f", packet[idx + offset : idx + offset + 4]
                        )[0]
                        f2 = struct.unpack(
                            ">f", packet[idx + offset + 4 : idx + offset + 8]
                        )[0]
                        if 0 <= f1 <= 10 and 0 <= f2 <= 10:
                            data["flow_m3h"] = f1
                            data["head_m"] = f2
                            break
            except struct.error:
                pass

        # Legacy: Custom Object 1-3 (Electrical)
        # Pattern: [00 01] [03 00 01] [data...]
        idx = packet.find(b"\x03\x00\x01")
        if idx != -1 and idx >= 2:
            try:
                # Check if preceded by SubID [00 01]
                if packet[idx - 2 : idx] == b"\x00\x01":
                    payload = packet[idx + 3 :]
                    if len(payload) >= 6:
                        data["voltage_ac_v"] = struct.unpack(
                            ">f", payload[2:6]
                        )[0]
                    if len(payload) >= 10:
                        data["voltage_dc_v"] = struct.unpack(
                            ">f", payload[6:10]
                        )[0]
                    if len(payload) >= 14:
                        data["power_w"] = struct.unpack(">f", payload[10:14])[0]
            except struct.error:
                pass

        # Legacy: Custom Object 1-11521 (Possible Actual Speed)
        # ObjID 0x2D01 = 11521
        idx = packet.find(b"\x2d\x01")
        if idx != -1:
            try:
                # Pattern: [SubID H][SubID L][0x2d][0x01][payload...]
                if idx >= 2:
                    payload = packet[idx + 2 :]
                    if len(payload) >= 14:
                        speed = struct.unpack(">f", payload[10:14])[0]
                        if 0 <= speed <= 5000:
                            data["speed_rpm"] = speed
                    if len(payload) >= 10:
                        pwr = struct.unpack(">f", payload[6:10])[0]
                        if 0 <= pwr <= 500:
                            data["power_w"] = pwr
            except struct.error:
                pass

        # Legacy: Custom Object 2-1602 (Temperature)
        # ObjID 0x1602 = 5634
        # Pattern: [SubID=0x0002][ObjID=0x1602][payload...]
        idx = packet.find(b"\x16\x02")
        if idx != -1 and idx >= 2:
            try:
                # Check if preceded by SubID [00 02]
                if packet[idx - 2 : idx] == b"\x00\x02":
                    payload = packet[idx + 2 :]
                    if len(payload) >= 7:
                        data["media_temperature_c"] = struct.unpack(
                            ">f", payload[3:7]
                        )[0]
                    if len(payload) >= 11:
                        data["pcb_temperature_c"] = struct.unpack(
                            ">f", payload[7:11]
                        )[0]
                    if len(payload) >= 15:
                        data["control_box_temperature_c"] = struct.unpack(
                            ">f", payload[11:15]
                        )[0]
            except struct.error:
                pass

        return data

    @staticmethod
    def decode_register_read_response(packet: bytes) -> dict[str, Any]:
        """
        Decode register-read query responses (OpSpec 0x30, 0x2b, etc).

        When querying telemetry using Class 10 READ operations (OpSpec 0x03),
        the pump responds with packets that have different OpSpec values
        (0x30 for motor state, 0x2b for flow, 0x14 for temperature, etc).

        These responses have a simpler format than standard notifications:
        - Bytes 0-11: Packet header (start, len, dest, src, class, opspec, counters)
        - Bytes 12+: Reserved/padding (1 byte)
        - Bytes 13+: Packed array of IEEE 754 floats (big-endian)

        The data starts at offset 13 and contains sequential float values.
        The meaning of each float depends on the OpSpec value.

        Args:
            packet: Full GENI response packet bytes

        Returns:
            Dictionary with decoded telemetry data based on OpSpec

        Examples:
            >>> # Motor state response (OpSpec 0x30)
            >>> data = TelemetryDecoder.decode_register_read_response(motor_packet)
            >>> print(data['power_w'], data['speed_rpm'])

            >>> # Flow response (OpSpec 0x2b)
            >>> data = TelemetryDecoder.decode_register_read_response(flow_packet)
            >>> print(data['flow_m3h'], data['head_m'])
        """
        data: dict[str, Any] = {}

        if len(packet) < 13:
            return data

        opspec = packet[5] if len(packet) > 5 else 0

        # Extract floats starting at offset 13
        floats: list[float | None] = []
        offset = 13
        while offset + 4 <= len(packet) - 2:  # Leave room for CRC
            try:
                val = struct.unpack(">f", packet[offset : offset + 4])[0]
                # Check for NaN/invalid markers
                if val != val or abs(val) > 1e15:  # NaN or unreasonably large
                    floats.append(None)
                else:
                    floats.append(val)
                offset += 4
            except struct.error:
                break

        # Decode based on OpSpec value
        if opspec == 0x30:  # Motor state response
            # Float array layout for motor state:
            # [0] = Voltage AC (V)
            # [1] = Voltage DC (V)
            # [2] = Current (A)
            # [3] = Power (W)
            # [4] = Unknown (possibly redundant power measurement)
            # [5] = Speed (RPM)
            # [6+] = Reserved/NaN

            if len(floats) > 0 and floats[0] is not None:
                if 0 <= floats[0] <= 500:  # Reasonable AC voltage range
                    data["voltage_ac_v"] = floats[0]

            if len(floats) > 1 and floats[1] is not None:
                if 0 <= floats[1] <= 500:  # Reasonable DC voltage range
                    data["voltage_dc_v"] = floats[1]

            if len(floats) > 2 and floats[2] is not None:
                if 0 <= floats[2] <= 50:  # Reasonable current range
                    data["current_a"] = floats[2]

            if len(floats) > 3 and floats[3] is not None:
                if 0 <= floats[3] <= 1000:  # Reasonable power range
                    data["power_w"] = floats[3]

            if len(floats) > 5 and floats[5] is not None:
                if 0 <= floats[5] <= 10000:  # Reasonable RPM range
                    data["speed_rpm"] = floats[5]

        elif opspec == 0x2B:  # Flow/pressure response
            # Float array layout for flow/pressure:
            # [0-5] = Reserved/Unknown
            # [6] = Flow rate (m³/h)
            # [7] = Head pressure (m)
            # [8] = Inlet pressure (bar) - often NaN
            # [9] = Outlet pressure (bar) - often NaN

            if len(floats) > 6 and floats[6] is not None:
                if 0 <= floats[6] <= 100:  # Reasonable flow range
                    data["flow_m3h"] = floats[6]

            if len(floats) > 7 and floats[7] is not None:
                if 0 <= floats[7] <= 50:  # Reasonable head range
                    data["head_m"] = floats[7]

            if len(floats) > 8 and floats[8] is not None:
                if 0 <= floats[8] <= 20:  # Reasonable pressure range
                    data["inlet_pressure_bar"] = floats[8]

            if len(floats) > 9 and floats[9] is not None:
                if 0 <= floats[9] <= 20:
                    data["outlet_pressure_bar"] = floats[9]

        elif opspec == 0x14:  # Temperature response (alternative format)
            # This OpSpec already handled by legacy decoder patterns
            # But we can add explicit support here too
            pass

        return data

    @staticmethod
    def decode(frame: ParsedFrame) -> dict[str, Any]:
        """
        Auto-detect and decode telemetry based on Sub-ID and Object ID.

        This is a convenience method that routes to the appropriate decoder
        based on the frame's identifiers. If the standard decoders don't
        recognize the object, it falls back to legacy pattern matching.

        Args:
            frame: Parsed frame from FrameParser.parse_frame()

        Returns:
            Dictionary with decoded telemetry data, or empty dict if unknown type

        Examples:
            >>> # Decode any telemetry frame automatically
            >>> frame = FrameParser.parse_frame(notification_data)
            >>> telemetry = TelemetryDecoder.decode(frame)
            >>> if telemetry:
            ...     print(f"Received telemetry: {telemetry}")

        Raises:
            ValueError: If frame is not a valid Class 10 frame
        """
        if frame.class_byte != 0x0A:  # CLASS_10
            return {}  # Not a Class 10 frame, nothing to decode here

        if frame.obj_id is None or frame.sub_id is None:
            return {}  # Missing identifiers, can't decode as telemetry

        # Route to appropriate decoder
        match (frame.obj_id, frame.sub_id):
            case (87, 69):  # Motor state
                return TelemetryDecoder.decode_motor_state(frame.payload)

            case (93, 290):  # Flow/Pressure
                return TelemetryDecoder.decode_flow_pressure(frame.payload)

            case (93, 300):  # Temperature
                return TelemetryDecoder.decode_temperature(frame.payload)

            case (88, 0):  # Active alarms
                codes = TelemetryDecoder.decode_alarms_warnings(
                    frame.payload, True
                )
                return {"active_alarms": codes}

            case (88, 11):  # Active warnings
                codes = TelemetryDecoder.decode_alarms_warnings(
                    frame.payload, False
                )
                return {"active_warnings": codes}

            case _:
                # Unknown standard object - try register-read response decoder first
                logger.debug(
                    f"Unknown telemetry object ({frame.obj_id}, {frame.sub_id}), "
                    f"trying register-read response decoder"
                )

                # Try decoding as register-read response (OpSpec 0x30, 0x2b, etc)
                register_data = TelemetryDecoder.decode_register_read_response(
                    frame.raw_data
                )
                if register_data:
                    logger.debug(
                        f"Register-read decoder found: {register_data}"
                    )
                    return register_data

                # Fall back to legacy pattern matching
                logger.debug("Trying legacy pattern matching")
                legacy_data = TelemetryDecoder.decode_legacy_packet(
                    frame.raw_data
                )
                if legacy_data:
                    logger.debug(f"Legacy decoder found: {legacy_data}")
                return legacy_data


# Test vectors for validation in other languages
# These can be used to verify correct implementation
TEST_VECTORS = {
    "motor_state_normal": {
        "description": "Normal motor operation",
        "obj_id": 87,
        "sub_id": 69,
        "payload_hex": "4370000000000000402000000000000043160000453b8000",
        # 43700000 = 240.0V (grid voltage at offset 0)
        # 00000000 = reserved (offset 4)
        # 40200000 = 2.5A (current at offset 8)
        # 00000000 = reserved (offset 12)
        # 43160000 = 150.0W (power at offset 16)
        # 453b8000 = 3000.0 RPM (speed at offset 20)
        "expected": {
            "voltage_ac_v": 240.0,
            "current_a": 2.5,
            "power_w": 150.0,
            "speed_rpm": 3000.0,
            # No converter_temperature_c - payload only 24 bytes
        },
    },
    "flow_pressure_normal": {
        "description": "Normal flow operation",
        "obj_id": 93,
        "sub_id": 290,
        "payload_hex": "3f8000003fc000004040000040400000",
        # 3f800000 = 1.0 m³/h (flow)
        # 3fc00000 = 1.5 m (head)
        # 40400000 = 3.0 bar (inlet)
        # 40400000 = 3.0 bar (outlet)
        "expected": {
            "flow_m3h": 1.0,
            "head_m": 1.5,
            "inlet_pressure_bar": 3.0,
            "outlet_pressure_bar": 3.0,
        },
    },
    "temperature_normal": {
        "description": "Normal temperature readings",
        "obj_id": 93,
        "sub_id": 300,
        "payload_hex": "4234000042480000428c0000",
        # 42340000 = 45.0°C (media)
        # 42480000 = 50.0°C (PCB)
        # 428c0000 = 70.0°C (control box)
        "expected": {
            "media_temperature_c": 45.0,
            "pcb_temperature_c": 50.0,
            "control_box_temperature_c": 70.0,
        },
    },
    "alarms_active": {
        "description": "Two active alarms",
        "obj_id": 88,
        "sub_id": 0,
        "payload_hex": "00010002",
        # 0001 = Alarm code 1
        # 0002 = Alarm code 2
        "expected": {"active_alarms": [1, 2]},
    },
}
