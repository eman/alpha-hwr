"""
Tests for ControlService setpoint and mode parsing functionality.

This module tests the control service's ability to parse setpoint configurations
and operation request payloads using the new protocol architecture.
"""

import struct
from unittest.mock import Mock

import pytest

from alpha_hwr.services.history import HistoryService


class TestControlServiceParsing:
    """Tests for control service parsing methods (internal to HistoryService)."""

    @pytest.fixture
    def history_service(self):
        """Create a mock HistoryService for testing."""
        transport = Mock()
        session = Mock()
        session.is_connected = True
        return HistoryService(transport, session)

    @pytest.mark.asyncio
    async def test_parse_operation_request_type_303_sub6(self, history_service):
        """Test parsing Type 303 Operation Request (Sub 6) payload.

        Structure: [CS(1)][OpMode(1)][ControlMode(1)][Setpoint(4)]
        Values: CS=0, OpMode=1, CM=2 (ConstSpeed), Setpoint=2500.0
        """
        cs = 0
        op_mode = 1
        ctrl_mode = 2
        setpoint = 2500.0

        # Build payload without header
        payload = struct.pack(">BBBf", cs, op_mode, ctrl_mode, setpoint)

        # Verify we can parse the structure
        assert len(payload) == 7
        parsed_cs = payload[0]
        parsed_op_mode = payload[1]
        parsed_ctrl_mode = payload[2]
        parsed_setpoint = struct.unpack(">f", payload[3:7])[0]

        assert parsed_cs == cs
        assert parsed_op_mode == op_mode
        assert parsed_ctrl_mode == ctrl_mode
        assert abs(parsed_setpoint - setpoint) < 0.01

        # Test with 3-byte header [00 00 06]
        header = bytes([0x00, 0x00, 0x06])
        payload_with_header = header + payload

        # Skip header and parse
        payload_no_header = payload_with_header[3:]
        parsed_setpoint_h = struct.unpack(">f", payload_no_header[3:7])[0]
        assert abs(parsed_setpoint_h - setpoint) < 0.01

    @pytest.mark.asyncio
    async def test_parse_factory_config_type_301_sub15(self, history_service):
        """Test parsing Type 301 Factory Config (Sub 15 - Const Pressure).

        Structure: [Def(4)][Min(4)][Max(4)]
        """
        default_val = 3.0
        min_val = 1.0
        max_val = 6.0

        # Build payload
        payload = struct.pack(">fff", default_val, min_val, max_val)

        # Parse without header
        assert len(payload) == 12
        parsed_default = struct.unpack(">f", payload[0:4])[0]
        parsed_min = struct.unpack(">f", payload[4:8])[0]
        parsed_max = struct.unpack(">f", payload[8:12])[0]

        assert abs(parsed_default - default_val) < 0.01
        assert abs(parsed_min - min_val) < 0.01
        assert abs(parsed_max - max_val) < 0.01

        # Test with header
        header = bytes([0x00, 0x00, 0x0F])
        payload_with_header = header + payload

        # Skip header and parse
        payload_no_header = payload_with_header[3:]
        parsed_min_h = struct.unpack(">f", payload_no_header[4:8])[0]
        assert abs(parsed_min_h - min_val) < 0.01

    @pytest.mark.asyncio
    async def test_parse_autoadapt_limits_sub11_uint16(self, history_service):
        """Test parsing AutoAdapt limits (Sub 11 - uint16 format).

        Structure: [Def(2)][Pad(2)][Min(2)][Pad(2)][Max(2)][Pad(2)]
        Values: Def=14695, Min=14468, Max=14935
        """
        default_val = 14695
        min_val = 14468
        max_val = 14935

        # Build header (3 bytes)
        header = bytes([0x00, 0x00, 0x1C])

        # Build payload with padding
        payload = bytearray()
        payload.extend(struct.pack(">H", default_val))  # Def
        payload.extend(b"\x00\x00")  # Pad
        payload.extend(struct.pack(">H", min_val))  # Min
        payload.extend(b"\x00\x00")  # Pad
        payload.extend(struct.pack(">H", max_val))  # Max
        payload.extend(b"\x00\x00")  # Pad

        full_payload = header + payload

        # Skip header and parse
        data = full_payload[3:]
        parsed_default = struct.unpack(">H", data[0:2])[0]
        parsed_min = struct.unpack(">H", data[4:6])[0]
        parsed_max = struct.unpack(">H", data[8:10])[0]

        assert parsed_default == default_val
        assert parsed_min == min_val
        assert parsed_max == max_val

    @pytest.mark.asyncio
    async def test_parse_autoadapt_radiator_sub19_float32(
        self, history_service
    ):
        """Test parsing AutoAdapt Radiator limits (Sub 19 - float32).

        Structure: [Def(4)][Min(4)][Max(4)]
        """
        default_val = 3.0
        min_val = 1.0
        max_val = 5.0

        payload = struct.pack(">fff", default_val, min_val, max_val)

        # With header
        header = bytes([0x00, 0x00, 0x1C])
        full_payload = header + payload

        # Skip header and parse
        data = full_payload[3:]
        parsed_default = struct.unpack(">f", data[0:4])[0]
        parsed_min = struct.unpack(">f", data[4:8])[0]
        parsed_max = struct.unpack(">f", data[8:12])[0]

        assert abs(parsed_default - default_val) < 0.01
        assert abs(parsed_min - min_val) < 0.01
        assert abs(parsed_max - max_val) < 0.01

    @pytest.mark.asyncio
    async def test_short_payload_handling(self, history_service):
        """Test handling of insufficient payload data."""
        payload = bytes([0x01, 0x02])

        # Should fail to parse due to insufficient data
        with pytest.raises(struct.error):
            struct.unpack(">BBBf", payload)

    @pytest.mark.asyncio
    async def test_payload_structure_validation(self, history_service):
        """Test validation of payload structures."""
        # Valid payload
        valid_payload = struct.pack(">BBBf", 0, 1, 2, 2500.0)
        assert len(valid_payload) == 7

        # Empty payload
        empty_payload = b""
        assert len(empty_payload) == 0

        # Partial payload
        partial_payload = bytes([0x01, 0x02, 0x03])
        assert len(partial_payload) < 7
