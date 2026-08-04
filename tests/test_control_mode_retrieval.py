from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError

from alpha_hwr import ControlMode

# Note: client fixture is now provided by conftest.py as mock_client_simple


class TestControlModeRetrieval:
    @pytest.mark.asyncio
    async def test_get_control_mode_class10_success(self, mock_client_simple):
        """Test successful retrieval via Class 10 (Object 86, Sub-ID 6)."""
        # Mock the transport query response
        # Response format: [STX][LEN][DST][SRC][Class][OpSpec][ObjH][ObjL][SubH][SubL][DATA...][CRC_H][CRC_L]
        # DATA format: [00 00 XX] [control_source][operation_mode][control_mode][set_point(4 bytes)]
        #
        # Frame: STX=0x27, LEN=0x0D (13), DST=0xF8, SRC=0xE7
        # APDU: Class=0x0A, OpSpec=0x43 (response), Obj=86 (0x56), Sub=6 (0x00 0x06)
        # DATA: [00 00 07] [00 06 02] + 4-byte float (setpoint)
        frame = bytearray(
            [
                0x27,  # STX
                0x14,  # LEN (20 bytes: DST + SRC + APDU + DATA)
                0xF8,  # DST
                0xE7,  # SRC
                0x0A,  # Class 10
                0x43,  # OpSpec (response)
                0x56,  # Object 86
                0x00,  # Sub-ID high
                0x00,
                0x06,  # Sub-ID low = 6
                # DATA payload:
                0x00,
                0x00,
                0x07,  # Header
                0x00,  # control_source
                0x06,  # operation_mode
                0x02,  # control_mode = CONSTANT_SPEED
                0x7F,
                0xFF,
                0xFF,
                0xFF,  # setpoint (float NaN for testing)
                # CRC (we'll add dummy values)
                0x00,
                0x00,
            ]
        )

        mock_client_simple.transport.query = AsyncMock(
            return_value=bytes(frame)
        )

        mode_info = await mock_client_simple.control.get_mode()

        assert mode_info is not None
        assert mode_info.control_mode == 2  # CONSTANT_SPEED
        assert mode_info.control_mode == ControlMode.CONSTANT_SPEED

    @pytest.mark.asyncio
    async def test_get_control_mode_different_modes(self, mock_client_simple):
        """Test various control mode values."""
        test_cases = [
            (0, ControlMode.CONSTANT_PRESSURE),
            (5, ControlMode.AUTO_ADAPT),
            (8, ControlMode.CONSTANT_FLOW),
            # Note: Mode 27 (TEMPERATURE_RANGE_CONTROL) requires a different object read, skipping for now
        ]

        for mode_id, expected_enum in test_cases:
            # Create GENI frame response with mode_id at the appropriate position
            frame = bytearray(
                [
                    0x27,  # STX
                    0x14,  # LEN
                    0xF8,  # DST
                    0xE7,  # SRC
                    0x0A,  # Class 10
                    0x43,  # OpSpec
                    0x56,  # Object 86
                    0x00,
                    0x00,
                    0x06,  # Sub-ID = 6
                    # DATA:
                    0x00,
                    0x00,
                    0x07,  # Header
                    0x00,  # control_source
                    0x06,  # operation_mode
                    mode_id,  # control_mode (variable)
                    0x7F,
                    0xFF,
                    0xFF,
                    0xFF,  # setpoint
                    0x00,
                    0x00,  # CRC
                ]
            )

            mock_client_simple.transport.query = AsyncMock(
                return_value=bytes(frame)
            )

            mode_info = await mock_client_simple.control.get_mode()
            assert mode_info is not None
            assert mode_info.control_mode == mode_id
            assert ControlMode(mode_info.control_mode) == expected_enum

    @pytest.mark.asyncio
    async def test_get_control_mode_no_data(self, mock_client_simple):
        """Test when query returns no data."""
        mock_client_simple.transport.query = AsyncMock(return_value=None)

        mode_info = await mock_client_simple.control.get_mode()

        assert mode_info is None

    @pytest.mark.asyncio
    async def test_get_control_mode_short_response(self, mock_client_simple):
        """Test when response is too short (less than 6 bytes)."""
        # Short response (only 5 bytes)
        short_data = bytes([0x00, 0x00, 0x07, 0x00, 0x06])
        mock_client_simple.transport.query = AsyncMock(return_value=short_data)

        mode_info = await mock_client_simple.control.get_mode()

        assert mode_info is None

    @pytest.mark.asyncio
    async def test_get_control_mode_exception_handling(
        self, mock_client_simple
    ):
        """Test exception handling."""
        mock_client_simple.transport.query = AsyncMock(
            side_effect=BleakError("Mock Error")
        )

        mode_info = await mock_client_simple.control.get_mode()

        assert mode_info is None
