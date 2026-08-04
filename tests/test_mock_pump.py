"""Tests for the mock pump."""

import pytest
from mocks.mock_pump import MockPump

from alpha_hwr.protocol import FrameBuilder, FrameParser, TelemetryDecoder


class TestMockPump:
    """Test the mock pump functionality."""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """Test basic connection/disconnection."""
        pump = MockPump()

        assert not pump.state.connected
        await pump.connect()
        assert pump.state.connected

        await pump.disconnect()
        assert not pump.state.connected

    @pytest.mark.asyncio
    async def test_authentication(self):
        """Test authentication."""
        pump = MockPump()
        await pump.connect()

        assert not pump.state.authenticated
        await pump.authenticate(fast_mode=True)
        assert pump.state.authenticated

    @pytest.mark.asyncio
    async def test_motor_state_telemetry(self):
        """Test reading motor state telemetry."""
        pump = MockPump()
        await pump.connect()
        await pump.authenticate(fast_mode=True)

        # Build read request for motor state (obj_id=87, sub_id=69 -> register 0x570045)
        register = (87 << 16) | 69  # 0x570045
        cmd = FrameBuilder.build_class10_read(register)
        response = await pump.send_command(cmd)

        # Parse response
        frame = FrameParser.parse_frame(response)
        assert frame.valid
        assert frame.class_byte == 10
        # For Class 10, obj_id is the full register in the response
        # The parser extracts this differently

        # Decode telemetry
        data = TelemetryDecoder.decode_motor_state(frame.payload)
        assert "voltage_ac_v" in data
        assert "speed_rpm" in data
        assert data["voltage_ac_v"] == 230.0

    @pytest.mark.asyncio
    async def test_control_start_stop(self):
        """Test start/stop commands."""
        pump = MockPump()
        await pump.connect()
        await pump.authenticate(fast_mode=True)

        # Initially stopped
        assert not pump.state.running
        assert pump.state.speed_rpm == 0.0

        # Build start command using Class 10 DataObject SET
        start_payload = bytearray(
            [0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00]
        )
        start_payload.extend(bytes([0x45, 0x65, 0x70, 0x00]))  # Suffix
        cmd = FrameBuilder.build_data_object_set(
            sub_id=0x5600, obj_id=0x0601, data=bytes(start_payload)
        )

        response = await pump.send_command(cmd)
        frame = FrameParser.parse_frame(response)
        assert frame.valid

        # Pump should be running
        assert pump.state.running
        assert pump.state.speed_rpm > 0

        # Build stop command using Class 10 DataObject SET
        stop_payload = bytearray(
            [0x2F, 0x01, 0x00, 0x00, 0x07, 0x00, 0x01, 0x00]
        )
        stop_payload.extend(bytes([0x45, 0x65, 0x70, 0x00]))
        cmd = FrameBuilder.build_data_object_set(
            sub_id=0x5600, obj_id=0x0601, data=bytes(stop_payload)
        )

        response = await pump.send_command(cmd)
        frame = FrameParser.parse_frame(response)
        assert frame.valid

        # Pump should be stopped
        assert not pump.state.running
        assert pump.state.speed_rpm == 0.0

    @pytest.mark.asyncio
    async def test_flow_pressure_telemetry(self):
        """Test reading flow/pressure telemetry."""
        pump = MockPump()
        await pump.connect()
        await pump.authenticate(fast_mode=True)

        # obj_id=93 (0x5D), sub_id=290 (0x0122) -> register 0x5D0122
        register = (93 << 16) | 290
        cmd = FrameBuilder.build_class10_read(register)
        response = await pump.send_command(cmd)

        frame = FrameParser.parse_frame(response)
        assert frame.valid
        # Verify it's a Class 10 response
        assert frame.class_byte == 10

        data = TelemetryDecoder.decode_flow_pressure(frame.payload)
        assert "flow_m3h" in data
        assert "head_m" in data

    @pytest.mark.asyncio
    async def test_temperature_telemetry(self):
        """Test reading temperature telemetry."""
        pump = MockPump()
        await pump.connect()
        await pump.authenticate(fast_mode=True)

        # obj_id=93 (0x5D), sub_id=300 (0x012C) -> register 0x5D012C
        register = (93 << 16) | 300
        cmd = FrameBuilder.build_class10_read(register)
        response = await pump.send_command(cmd)

        frame = FrameParser.parse_frame(response)
        assert frame.valid

        data = TelemetryDecoder.decode_temperature(frame.payload)
        assert "media_temperature_c" in data
        assert "pcb_temperature_c" in data

    @pytest.mark.asyncio
    async def test_timestamp_map(self):
        """Test reading timestamp maps."""
        pump = MockPump()
        await pump.connect()
        await pump.authenticate(fast_mode=True)

        # Read 10-cycle timestamps: obj_id=88 (0x58), sub_id=13300 (0x33F4) -> register 0x5833F4
        register = (88 << 16) | 13300
        cmd = FrameBuilder.build_class10_read(register)
        response = await pump.send_command(cmd)

        frame = FrameParser.parse_frame(response)
        assert frame.valid
        assert frame.class_byte == 10
        assert len(frame.payload) >= 40  # 10 timestamps * 4 bytes

    @pytest.mark.asyncio
    async def test_trend_data(self):
        """Test reading trend data."""
        pump = MockPump()
        await pump.connect()
        await pump.authenticate(fast_mode=True)

        # Read flow trend data: obj_id=53 (0x35), sub_id=451 (0x01C3) -> register 0x3501C3
        register = (53 << 16) | 451
        cmd = FrameBuilder.build_class10_read(register)
        response = await pump.send_command(cmd)

        frame = FrameParser.parse_frame(response)
        assert frame.valid
        assert frame.class_byte == 10
        # TrendData1B size (29) + 3-byte header = 32
        assert len(frame.payload) == 32
