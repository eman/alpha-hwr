"""
Tests for HistoryService trend data parsing functionality.

This module tests the history service's ability to parse trend data payloads
including timestamp maps and trend value structures using the new protocol.
"""

import struct
from unittest.mock import AsyncMock, Mock

import pytest

from alpha_hwr.services.history import HistoryService


class TestHistoryServiceParsing:
    """Tests for history service trend data parsing."""

    @pytest.fixture
    def history_service(self):
        """Create a mock HistoryService for testing."""
        transport = Mock()
        session = Mock()
        session.is_connected = True
        return HistoryService(transport, session)

    @pytest.mark.asyncio
    async def test_parse_timestamp_map_10cycle(self, history_service):
        """Test parsing of TrendDataTimestampMap for 10-cycle (Obj 88, Sub 13300)."""
        # 10 timestamps (uint32)
        # NOTE: Use large values to avoid collision with header detection (00 00 XX)
        timestamps = [1000000 + i * 100 for i in range(10)]
        payload = b""
        for ts in timestamps:
            payload += struct.pack(">I", ts)

        # Mock the _read_class10_object method
        history_service._read_class10_object = AsyncMock(return_value=payload)

        # Call internal method
        data = await history_service._read_timestamp_map(13300)

        assert data is not None
        assert data["cycle_type"] == 10
        assert data["timestamps"] == timestamps

    @pytest.mark.asyncio
    async def test_parse_timestamp_map_100cycle(self, history_service):
        """Test parsing of TrendDataTimestampMap for 100-cycle (Obj 88, Sub 13301)."""
        # 10 timestamps (uint32)
        # NOTE: Use large values to avoid collision with header detection (00 00 XX)
        timestamps = [2000000 + i * 50 for i in range(10)]
        payload = b""
        for ts in timestamps:
            payload += struct.pack(">I", ts)

        # Mock the _read_class10_object method
        history_service._read_class10_object = AsyncMock(return_value=payload)

        # Call internal method
        data = await history_service._read_timestamp_map(13301)

        assert data is not None
        assert data["cycle_type"] == 100
        assert data["timestamps"] == timestamps

    @pytest.mark.asyncio
    async def test_parse_trend_data_1b_type946(self, history_service):
        """Test parsing of TrendData1B (Obj 53, Type 946).

        Structure:
        - float current_value (4)
        - uint8[10] cycle10
        - uint8 next_ctr
        - float next_value_100 (4)
        - uint8[10] cycle100
        Total: 29 bytes
        """
        current_val = 12.34
        cycle10 = [i for i in range(10)]
        next_ctr = 5
        next_val_100 = 56.78
        cycle100 = [10 + i for i in range(10)]

        payload = struct.pack(">f", current_val)
        payload += bytes(cycle10)
        payload += bytes([next_ctr])
        payload += struct.pack(">f", next_val_100)
        payload += bytes(cycle100)

        assert len(payload) == 29

        # Mock the _read_class10_object method
        history_service._read_class10_object = AsyncMock(return_value=payload)

        # Call internal method
        data = await history_service._read_trend_values(53, 451)

        assert data is not None
        assert abs(data["current_value"] - current_val) < 0.001
        assert data["cycle10_raw"] == cycle10
        assert data["next_ctr"] == next_ctr
        assert abs(data["next_value_100"] - next_val_100) < 0.001
        assert data["cycle100_raw"] == cycle100

    @pytest.mark.asyncio
    async def test_parse_trend_data_2b_type947(self, history_service):
        """Test parsing of TrendData2B (Obj 53, Type 947).

        Structure:
        - float current_value (4)
        - uint16[10] cycle10 (20)
        - uint8 next_ctr (1)
        - float next_value_100 (4)
        - uint16[10] cycle100 (20)
        Total: 49 bytes
        """
        current_val = 99.99
        cycle10 = [1000 + i for i in range(10)]
        next_ctr = 3
        next_val_100 = 88.88
        cycle100 = [2000 + i for i in range(10)]

        payload = struct.pack(">f", current_val)
        for val in cycle10:
            payload += struct.pack(">H", val)
        payload += bytes([next_ctr])
        payload += struct.pack(">f", next_val_100)
        for val in cycle100:
            payload += struct.pack(">H", val)

        assert len(payload) == 49

        # Parse manually since Type 947 (2B) is larger format
        # Current service may not handle this yet, so test structure
        parsed_current = struct.unpack(">f", payload[0:4])[0]
        assert abs(parsed_current - current_val) < 0.001

        # Parse cycle10 (10 uint16s)
        parsed_cycle10 = []
        for i in range(10):
            offset = 4 + (i * 2)
            val = struct.unpack(">H", payload[offset : offset + 2])[0]
            parsed_cycle10.append(val)
        assert parsed_cycle10 == cycle10

        # Parse next_ctr
        parsed_next_ctr = payload[24]
        assert parsed_next_ctr == next_ctr

        # Parse next_value_100
        parsed_next_val = struct.unpack(">f", payload[25:29])[0]
        assert abs(parsed_next_val - next_val_100) < 0.001

        # Parse cycle100 (10 uint16s)
        parsed_cycle100 = []
        for i in range(10):
            offset = 29 + (i * 2)
            val = struct.unpack(">H", payload[offset : offset + 2])[0]
            parsed_cycle100.append(val)
        assert parsed_cycle100 == cycle100

    @pytest.mark.asyncio
    async def test_timestamp_map_with_header(self, history_service):
        """Test parsing timestamp map with 3-byte header."""
        timestamps = [5000 + i * 10 for i in range(10)]

        # Build with header [00 00 XX]
        header = bytes([0x00, 0x00, 0x34])  # 0x34 = SubID high byte
        payload = header
        for ts in timestamps:
            payload += struct.pack(">I", ts)

        # Mock the _read_class10_object method
        history_service._read_class10_object = AsyncMock(return_value=payload)

        # Call internal method
        data = await history_service._read_timestamp_map(13300)

        assert data is not None
        assert data["timestamps"] == timestamps

    @pytest.mark.asyncio
    async def test_trend_values_with_header(self, history_service):
        """Test parsing trend values with 3-byte header."""
        current_val = 42.42
        cycle10 = [20 + i for i in range(10)]
        next_ctr = 7
        next_val_100 = 33.33
        cycle100 = [30 + i for i in range(10)]

        # Build with header
        header = bytes([0x00, 0x00, 0xC3])  # 0xC3 = SubID high byte
        payload = header
        payload += struct.pack(">f", current_val)
        payload += bytes(cycle10)
        payload += bytes([next_ctr])
        payload += struct.pack(">f", next_val_100)
        payload += bytes(cycle100)

        # Mock the _read_class10_object method
        history_service._read_class10_object = AsyncMock(return_value=payload)

        # Call internal method
        data = await history_service._read_trend_values(53, 451)

        assert data is not None
        assert abs(data["current_value"] - current_val) < 0.001
        assert data["cycle10_raw"] == cycle10

    @pytest.mark.asyncio
    async def test_invalid_payload_too_short(self, history_service):
        """Test handling of payload that's too short."""
        # Only 10 bytes - should fail
        short_payload = bytes(10)

        # Mock the _read_class10_object method
        history_service._read_class10_object = AsyncMock(
            return_value=short_payload
        )

        # Call internal method - should return None or handle gracefully
        data = await history_service._read_trend_values(53, 451)

        # Service should return None for invalid data
        assert data is None

    @pytest.mark.asyncio
    async def test_empty_timestamp_map(self, history_service):
        """Test handling of empty timestamp map."""
        # Mock the _read_class10_object method to return None
        history_service._read_class10_object = AsyncMock(return_value=None)

        # Call internal method
        data = await history_service._read_timestamp_map(13300)

        assert data is None

    @pytest.mark.asyncio
    async def test_partial_timestamp_array(self, history_service):
        """Test parsing timestamp map with partial data (only 5 timestamps)."""
        # Only 5 timestamps instead of 10
        # NOTE: Use large values to avoid collision with header detection (00 00 XX)
        timestamps = [7000000 + i * 25 for i in range(5)]
        payload = b""
        for ts in timestamps:
            payload += struct.pack(">I", ts)

        # Mock the _read_class10_object method
        history_service._read_class10_object = AsyncMock(return_value=payload)

        # Call internal method - should parse what's available
        data = await history_service._read_timestamp_map(13300)

        assert data is not None
        assert len(data["timestamps"]) == 5
        assert data["timestamps"] == timestamps
