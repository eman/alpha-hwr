"""
Tests for history service operations.

This module tests the HistoryService including:
- get_trend_data() - Retrieve all historical trend data
- get_cycle_timestamps() - Get timestamps of recent pump cycles
- Error handling and edge cases
"""

import struct
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from conftest import build_class10_response


class TestGetTrendData:
    """Tests for get_trend_data() method."""

    @pytest.mark.asyncio
    async def test_get_trend_data_success(self, mock_client_simple):
        """Test successfully retrieving trend data."""
        # Build mock timestamp maps (10 timestamps each)
        timestamps_10 = [1000000 + i * 100 for i in range(10)]
        timestamps_100 = [2000000 + i * 1000 for i in range(10)]

        ts_payload_10 = b"".join(struct.pack(">I", ts) for ts in timestamps_10)
        ts_payload_100 = b"".join(
            struct.pack(">I", ts) for ts in timestamps_100
        )

        # Build mock trend value payloads (20 uint16 values: 10 for cycle-10, 10 for cycle-100)
        flow_values = [100 + i * 5 for i in range(20)]  # Flow in 0.1 m³/h units
        head_values = [50 + i * 2 for i in range(20)]  # Head in 0.1 m units
        temp_values = [
            200 + i for i in range(20)
        ]  # Temp in 0.1°C units (20.0°C + i)
        power_values = [1000 + i * 10 for i in range(20)]  # Power time in hours

        flow_payload = b"".join(struct.pack(">H", v) for v in flow_values)
        head_payload = b"".join(struct.pack(">H", v) for v in head_values)
        temp_payload = b"".join(struct.pack(">H", v) for v in temp_values)
        power_payload = b"".join(struct.pack(">H", v) for v in power_values)

        # Mock responses in order:
        # 1. Timestamp map 10-cycle (Obj 88, Sub 13300)
        # 2. Timestamp map 100-cycle (Obj 88, Sub 13301)
        # 3. Flow values (Obj 53, Sub 451)
        # 4. Head values (Obj 53, Sub 452)
        # 5. Temp values (Obj 53, Sub 453)
        # 6. Power time values (Obj 53, Sub 454)
        responses = [
            build_class10_response(88, 13300, ts_payload_10),
            build_class10_response(88, 13301, ts_payload_100),
            build_class10_response(53, 451, flow_payload),
            build_class10_response(53, 452, head_payload),
            build_class10_response(53, 453, temp_payload),
            build_class10_response(53, 454, power_payload),
        ]

        mock_client_simple.transport.query = AsyncMock(side_effect=responses)

        result = await mock_client_simple.history.get_trend_data()

        # Should return a TrendDataCollection
        assert result is not None
        assert result.flow_series is not None
        assert result.head_series is not None
        assert result.media_temperature_series is not None
        assert result.power_on_time_series is not None

        # Check that series have data points
        assert len(result.flow_series.cycle_10_points) > 0
        assert len(result.flow_series.cycle_100_points) > 0

    @pytest.mark.asyncio
    async def test_get_trend_data_timestamp_failure(self, mock_client_simple):
        """Test get_trend_data when timestamp fetch fails."""
        # Mock timestamp reads to return None (failure)
        mock_client_simple.transport.query = AsyncMock(return_value=None)

        result = await mock_client_simple.history.get_trend_data()

        # Should return None when timestamps can't be fetched
        assert result is None

    @pytest.mark.asyncio
    async def test_get_trend_data_partial_failure(self, mock_client_simple):
        """Test get_trend_data when some trend values fail."""
        # Build timestamp maps
        timestamps_10 = [1000000 + i * 100 for i in range(10)]
        timestamps_100 = [2000000 + i * 1000 for i in range(10)]

        ts_payload_10 = b"".join(struct.pack(">I", ts) for ts in timestamps_10)
        ts_payload_100 = b"".join(
            struct.pack(">I", ts) for ts in timestamps_100
        )

        # Build only flow payload
        flow_values = [100 + i * 5 for i in range(20)]
        flow_payload = b"".join(struct.pack(">H", v) for v in flow_values)

        # Mock responses: timestamps succeed, flow succeeds, others fail (None)
        responses = [
            build_class10_response(88, 13300, ts_payload_10),
            build_class10_response(88, 13301, ts_payload_100),
            build_class10_response(53, 451, flow_payload),  # Flow succeeds
            None,  # Head fails
            None,  # Temp fails
            None,  # Power fails
        ]

        mock_client_simple.transport.query = AsyncMock(side_effect=responses)

        result = await mock_client_simple.history.get_trend_data()

        # Should still return collection with partial data
        assert result is not None
        assert result.flow_series is not None
        assert result.head_series is None
        assert result.media_temperature_series is None
        assert result.power_on_time_series is None

    @pytest.mark.asyncio
    async def test_get_trend_data_empty_values(self, mock_client_simple):
        """Test get_trend_data with empty value arrays."""
        # Build timestamp maps
        timestamps_10 = [1000000 + i * 100 for i in range(10)]
        timestamps_100 = [2000000 + i * 1000 for i in range(10)]

        ts_payload_10 = b"".join(struct.pack(">I", ts) for ts in timestamps_10)
        ts_payload_100 = b"".join(
            struct.pack(">I", ts) for ts in timestamps_100
        )

        # Empty payloads (0 bytes)
        empty_payload = b""

        responses = [
            build_class10_response(88, 13300, ts_payload_10),
            build_class10_response(88, 13301, ts_payload_100),
            build_class10_response(53, 451, empty_payload),
            build_class10_response(53, 452, empty_payload),
            build_class10_response(53, 453, empty_payload),
            build_class10_response(53, 454, empty_payload),
        ]

        mock_client_simple.transport.query = AsyncMock(side_effect=responses)

        result = await mock_client_simple.history.get_trend_data()

        # Should handle empty payloads gracefully
        assert result is not None


class TestGetCycleTimestamps:
    """Tests for get_cycle_timestamps() method."""

    @pytest.mark.asyncio
    async def test_get_cycle_timestamps_10_cycles(self, mock_client_simple):
        """Test getting timestamps for 10 recent cycles."""
        # Build timestamp payload (10 Unix timestamps)
        timestamps = [
            1700000000 + i * 3600 for i in range(10)
        ]  # 2023+ timestamps
        payload = b"".join(struct.pack(">I", ts) for ts in timestamps)

        response = build_class10_response(88, 13300, payload)
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        result = await mock_client_simple.history.get_cycle_timestamps(count=10)

        # Should return list of datetime objects
        assert result is not None
        assert len(result) == 10
        assert all(isinstance(dt, datetime) for dt in result)

    @pytest.mark.asyncio
    async def test_get_cycle_timestamps_100_cycles(self, mock_client_simple):
        """Test getting timestamps for 100 recent cycles."""
        # Build timestamp payload (10 Unix timestamps for 100-cycle map)
        timestamps = [1700000000 + i * 36000 for i in range(10)]
        payload = b"".join(struct.pack(">I", ts) for ts in timestamps)

        response = build_class10_response(88, 13301, payload)
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        result = await mock_client_simple.history.get_cycle_timestamps(
            count=100
        )

        assert result is not None
        assert len(result) == 10
        assert all(isinstance(dt, datetime) for dt in result)

    @pytest.mark.asyncio
    async def test_get_cycle_timestamps_old_timestamps(
        self, mock_client_simple
    ):
        """Test handling of old timestamps (< year 2000)."""
        # Build timestamps that are small (relative to epoch)
        # These should get offset added: 946684800 (Jan 1, 2000)
        old_timestamps = [100000 + i * 1000 for i in range(10)]
        payload = b"".join(struct.pack(">I", ts) for ts in old_timestamps)

        response = build_class10_response(88, 13300, payload)
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        result = await mock_client_simple.history.get_cycle_timestamps(count=10)

        assert result is not None
        assert len(result) == 10
        # All timestamps should be after year 2000
        for dt in result:
            assert dt.year >= 2000

    @pytest.mark.asyncio
    async def test_get_cycle_timestamps_read_failure(self, mock_client_simple):
        """Test get_cycle_timestamps when read fails."""
        mock_client_simple.transport.query = AsyncMock(return_value=None)

        result = await mock_client_simple.history.get_cycle_timestamps(count=10)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cycle_timestamps_invalid_data(self, mock_client_simple):
        """Test get_cycle_timestamps with invalid/corrupt data."""
        # Send truncated payload (not enough bytes for 10 timestamps)
        truncated_payload = b"\x00\x01\x02\x03"

        response = build_class10_response(88, 13300, truncated_payload)
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        result = await mock_client_simple.history.get_cycle_timestamps(count=10)

        # Should handle gracefully (either None or partial data)
        # Implementation-dependent behavior
        assert result is None or isinstance(result, list)


class TestHistoryServiceEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_get_trend_data_not_connected(self, mock_client_simple):
        """Test get_trend_data when not connected."""
        # Simulate disconnected state
        mock_client_simple.history.session.is_connected = lambda: False

        with pytest.raises(ConnectionError):
            await mock_client_simple.history.get_trend_data()

    @pytest.mark.asyncio
    async def test_get_cycle_timestamps_not_connected(self, mock_client_simple):
        """Test get_cycle_timestamps when not connected."""
        # Simulate disconnected state
        mock_client_simple.history.session.is_connected = lambda: False

        with pytest.raises(ConnectionError):
            await mock_client_simple.history.get_cycle_timestamps(count=10)

    @pytest.mark.asyncio
    async def test_get_trend_data_transport_exception(self, mock_client_simple):
        """Test get_trend_data when transport raises exception."""
        mock_client_simple.transport.query = AsyncMock(
            side_effect=BleakError("Transport error")
        )

        result = await mock_client_simple.history.get_trend_data()

        # Should catch exception and return None
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cycle_timestamps_transport_exception(
        self, mock_client_simple
    ):
        """Test get_cycle_timestamps when transport raises exception."""
        mock_client_simple.transport.query = AsyncMock(
            side_effect=BleakError("Transport error")
        )

        result = await mock_client_simple.history.get_cycle_timestamps(count=10)

        # Should catch exception and return None
        assert result is None


class TestHistoryServiceIntegration:
    """Integration tests for history service."""

    @pytest.mark.asyncio
    async def test_sequential_trend_requests(self, mock_client_simple):
        """Test making multiple trend data requests."""
        # Build minimal valid responses
        timestamps_10 = [1000000 + i * 100 for i in range(10)]
        timestamps_100 = [2000000 + i * 1000 for i in range(10)]

        ts_payload_10 = b"".join(struct.pack(">I", ts) for ts in timestamps_10)
        ts_payload_100 = b"".join(
            struct.pack(">I", ts) for ts in timestamps_100
        )

        flow_values = [100 + i * 5 for i in range(20)]
        flow_payload = b"".join(struct.pack(">H", v) for v in flow_values)

        # Each call to get_trend_data needs 6 responses
        responses = [
            # First call
            build_class10_response(88, 13300, ts_payload_10),
            build_class10_response(88, 13301, ts_payload_100),
            build_class10_response(53, 451, flow_payload),
            None,
            None,
            None,
            # Second call
            build_class10_response(88, 13300, ts_payload_10),
            build_class10_response(88, 13301, ts_payload_100),
            build_class10_response(53, 451, flow_payload),
            None,
            None,
            None,
        ]

        mock_client_simple.transport.query = AsyncMock(side_effect=responses)

        # Make two requests
        result1 = await mock_client_simple.history.get_trend_data()
        result2 = await mock_client_simple.history.get_trend_data()

        assert result1 is not None
        assert result2 is not None
        assert mock_client_simple.transport.query.call_count == 12

    @pytest.mark.asyncio
    async def test_mixed_history_operations(self, mock_client_simple):
        """Test mixing get_trend_data and get_cycle_timestamps calls."""
        # Build responses
        timestamps = [1700000000 + i * 3600 for i in range(10)]
        ts_payload = b"".join(struct.pack(">I", ts) for ts in timestamps)

        # Will be used for both get_cycle_timestamps and get_trend_data
        responses = [
            # get_cycle_timestamps call (10-cycle)
            build_class10_response(88, 13300, ts_payload),
            # get_trend_data call needs 6 responses
            build_class10_response(88, 13300, ts_payload),
            build_class10_response(88, 13301, ts_payload),
            None,
            None,
            None,
            None,
        ]

        mock_client_simple.transport.query = AsyncMock(side_effect=responses)

        # Get cycle timestamps
        cycles = await mock_client_simple.history.get_cycle_timestamps(count=10)
        assert cycles is not None
        assert len(cycles) == 10

        # Get trend data
        trends = await mock_client_simple.history.get_trend_data()
        assert trends is not None
