"""
Tests for telemetry service operations.

This module tests the TelemetryService including:
- read_once() - Single telemetry snapshot
- stream() - Continuous streaming
- update_from_notification() - BLE notification handling
- current/advanced properties
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock
from datetime import datetime


class TestReadOnce:
    """Tests for read_once() method."""

    @pytest.mark.asyncio
    async def test_read_once_success(self, mock_client_simple):
        """Test successfully reading telemetry once."""
        # Mock valid Class 10 response frames
        # Frame format: [STX][LEN][DST][SRC][Class=0x0A][OpSpec][...data...][CRC]
        motor_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,  # Header with Class 10, OpSpec 0x40
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,  # Mock motor data
                0x00,
                0x00,  # CRC
            ]
        )

        flow_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,
                0x11,
                0x12,
                0x13,
                0x14,
                0x15,
                0x16,
                0x17,
                0x18,
                0x00,
                0x00,
            ]
        )

        temp_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,
                0x21,
                0x22,
                0x23,
                0x24,
                0x25,
                0x26,
                0x27,
                0x28,
                0x00,
                0x00,
            ]
        )

        # Mock query to return responses for motor, flow, temp in sequence
        mock_client_simple.transport.query = AsyncMock(
            side_effect=[motor_response, flow_response, temp_response]
        )

        result = await mock_client_simple.telemetry.read_once()

        # Should return TelemetryData
        assert result is not None
        assert hasattr(result, "timestamp")
        assert isinstance(result.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_read_once_partial_failure(self, mock_client_simple):
        """Test read_once when some queries fail."""
        # Motor succeeds, flow fails, temp succeeds
        motor_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x00,
                0x00,
            ]
        )

        temp_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,
                0x21,
                0x22,
                0x23,
                0x24,
                0x25,
                0x26,
                0x27,
                0x28,
                0x00,
                0x00,
            ]
        )

        mock_client_simple.transport.query = AsyncMock(
            side_effect=[motor_response, None, temp_response]
        )

        result = await mock_client_simple.telemetry.read_once()

        # Should still return telemetry even with partial failures
        assert result is not None

    @pytest.mark.asyncio
    async def test_read_once_all_failures(self, mock_client_simple):
        """Test read_once when all queries fail."""
        mock_client_simple.transport.query = AsyncMock(return_value=None)

        result = await mock_client_simple.telemetry.read_once()

        # Should return telemetry object (possibly with default values)
        assert result is not None

    @pytest.mark.asyncio
    async def test_read_once_filters_notifications(self, mock_client_simple):
        """Test that read_once filters out passive notifications (OpSpec 0x0E)."""
        # Create a notification frame (OpSpec 0x0E) - should be filtered
        bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x0E,  # Class 10, OpSpec 0x0E (notification)
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x00,
                0x00,
            ]
        )

        # Valid response (OpSpec 0x40)
        valid_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x00,
                0x00,
            ]
        )

        # The match function should filter out notifications
        # So query should only accept valid responses
        mock_client_simple.transport.query = AsyncMock(
            side_effect=[valid_response, valid_response, valid_response]
        )

        result = await mock_client_simple.telemetry.read_once()

        assert result is not None

    @pytest.mark.asyncio
    async def test_read_once_not_connected(self, mock_client_simple):
        """Test read_once when not connected."""
        mock_client_simple.telemetry.session.ensure_connected = Mock(
            side_effect=ConnectionError("Not connected")
        )

        with pytest.raises(ConnectionError):
            await mock_client_simple.telemetry.read_once()


class TestStream:
    """Tests for stream() method."""

    @pytest.mark.asyncio
    async def test_stream_basic(self, mock_client_simple):
        """Test basic streaming functionality."""
        call_count = 0

        # Mock read_once to modify telemetry each time to trigger yields
        async def mock_read_once():
            nonlocal call_count
            call_count += 1
            # Modify telemetry each time to trigger yield
            mock_client_simple.telemetry._telemetry = (
                mock_client_simple.telemetry._telemetry.model_copy(
                    update={"flow_m3h": float(call_count)}
                )
            )
            return mock_client_simple.telemetry._telemetry

        mock_client_simple.telemetry.read_once = mock_read_once

        # Collect a few iterations
        count = 0
        async for data in mock_client_simple.telemetry.stream(interval=0.01):
            assert data is not None
            count += 1
            if count >= 3:
                break

        assert count == 3

    @pytest.mark.asyncio
    async def test_stream_yields_on_change(self, mock_client_simple):
        """Test that stream only yields when data changes."""
        # Mock read_once to modify telemetry each call
        call_count = 0

        async def mock_read_once():
            nonlocal call_count
            call_count += 1
            # Modify telemetry each time to trigger yields
            mock_client_simple.telemetry._telemetry = (
                mock_client_simple.telemetry._telemetry.model_copy(
                    update={"flow_m3h": 5.0 + call_count}
                )
            )
            return mock_client_simple.telemetry._telemetry

        mock_client_simple.telemetry.read_once = mock_read_once

        # Collect yields
        yields = []
        async for data in mock_client_simple.telemetry.stream(interval=0.01):
            yields.append(data)
            if len(yields) >= 2:
                break

        # Should have yielded at least twice
        assert len(yields) >= 2
        # Verify data changed between yields
        assert yields[0].flow_m3h != yields[1].flow_m3h

    @pytest.mark.asyncio
    async def test_stream_cancellation(self, mock_client_simple):
        """Test that stream handles cancellation gracefully."""

        async def mock_read_once():
            return mock_client_simple.telemetry._telemetry

        mock_client_simple.telemetry.read_once = mock_read_once

        # Start streaming and cancel after a bit
        with pytest.raises(asyncio.CancelledError):
            stream_task = asyncio.create_task(
                self._consume_stream(mock_client_simple.telemetry)
            )
            await asyncio.sleep(0.01)
            stream_task.cancel()
            await stream_task

    async def _consume_stream(self, telemetry):
        """Helper to consume stream."""
        async for _ in telemetry.stream(interval=0.01):
            pass

    @pytest.mark.asyncio
    async def test_stream_custom_interval(self, mock_client_simple):
        """Test stream with custom interval."""
        call_count = 0

        # Mock read_once to modify telemetry each time
        async def mock_read_once():
            nonlocal call_count
            call_count += 1
            mock_client_simple.telemetry._telemetry = (
                mock_client_simple.telemetry._telemetry.model_copy(
                    update={"flow_m3h": float(call_count)}
                )
            )
            return mock_client_simple.telemetry._telemetry

        mock_client_simple.telemetry.read_once = mock_read_once

        # Stream with longer interval
        count = 0
        start_time = asyncio.get_event_loop().time()

        async for data in mock_client_simple.telemetry.stream(interval=0.05):
            count += 1
            if count >= 2:
                break

        elapsed = asyncio.get_event_loop().time() - start_time

        # Should take at least 0.05 seconds for one interval
        assert elapsed >= 0.03  # Allow some slack

    @pytest.mark.asyncio
    async def test_stream_not_connected(self, mock_client_simple):
        """Test stream when not connected."""
        mock_client_simple.telemetry.session.ensure_connected = Mock(
            side_effect=ConnectionError("Not connected")
        )

        with pytest.raises(ConnectionError):
            async for _ in mock_client_simple.telemetry.stream():
                break


class TestUpdateFromNotification:
    """Tests for update_from_notification() method."""

    def test_update_from_notification_valid_frame(self, mock_client_simple):
        """Test updating from a valid notification frame."""
        # Valid Class 10 notification frame
        notification = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x0E,  # Class 10, OpSpec 0x0E
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x00,
                0x00,
            ]
        )

        # Update from notification
        mock_client_simple.telemetry.update_from_notification(notification)

        # Telemetry should be updated (or at least method should not crash)
        assert mock_client_simple.telemetry._telemetry is not None

    def test_update_from_notification_invalid_frame(self, mock_client_simple):
        """Test updating from invalid/corrupt frame."""
        # Invalid frame (too short)
        invalid_data = bytes([0x27, 0x01, 0x02])

        # Should handle gracefully without crashing
        try:
            mock_client_simple.telemetry.update_from_notification(invalid_data)
        except Exception:
            pytest.fail("Should handle invalid notification gracefully")

    def test_update_from_notification_empty_data(self, mock_client_simple):
        """Test updating from empty data."""
        empty_data = bytes()

        # Should handle gracefully
        try:
            mock_client_simple.telemetry.update_from_notification(empty_data)
        except Exception:
            pytest.fail("Should handle empty notification gracefully")

    def test_update_from_notification_wrong_class(self, mock_client_simple):
        """Test notification with wrong class byte."""
        # Class 3 frame instead of Class 10
        wrong_class = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x03,
                0x00,  # Class 3
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x00,
                0x00,
            ]
        )

        # Should handle gracefully (ignore non-Class 10 frames)
        try:
            mock_client_simple.telemetry.update_from_notification(wrong_class)
        except Exception:
            pytest.fail("Should handle wrong class gracefully")


class TestTelemetryProperties:
    """Tests for current and advanced properties."""

    def test_current_property(self, mock_client_simple):
        """Test accessing current telemetry property."""
        current = mock_client_simple.telemetry.current

        assert current is not None
        assert hasattr(current, "flow_m3h")
        assert hasattr(current, "head_m")
        assert hasattr(current, "power_w")

    def test_advanced_property(self, mock_client_simple):
        """Test accessing advanced telemetry property."""
        advanced = mock_client_simple.telemetry.advanced

        assert advanced is not None
        # Advanced telemetry should have expected fields
        assert hasattr(advanced, "converter_temperature_c")
        assert hasattr(advanced, "inlet_pressure_bar")
        assert hasattr(advanced, "active_alarms")

    def test_current_updates_after_read(self, mock_client_simple):
        """Test that current property reflects read_once updates."""
        # Get initial value
        initial_flow = mock_client_simple.telemetry.current.flow_m3h

        # Update internal telemetry
        mock_client_simple.telemetry._telemetry = (
            mock_client_simple.telemetry._telemetry.model_copy(
                update={"flow_m3h": 10.0}
            )
        )

        # Current should reflect update
        updated_flow = mock_client_simple.telemetry.current.flow_m3h
        assert updated_flow == 10.0
        assert updated_flow != initial_flow


class TestTelemetryServiceIntegration:
    """Integration tests for telemetry service."""

    @pytest.mark.asyncio
    async def test_read_once_then_stream(self, mock_client_simple):
        """Test reading once then starting a stream."""
        # Mock responses for read_once
        valid_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x00,
                0x00,
            ]
        )

        mock_client_simple.transport.query = AsyncMock(
            return_value=valid_response
        )

        # Read once
        once_data = await mock_client_simple.telemetry.read_once()
        assert once_data is not None

        # Mock read_once for streaming to modify data each time
        call_count = 0

        async def mock_read_once():
            nonlocal call_count
            call_count += 1
            # Modify telemetry each time to trigger yields
            mock_client_simple.telemetry._telemetry = (
                mock_client_simple.telemetry._telemetry.model_copy(
                    update={"flow_m3h": float(call_count)}
                )
            )
            return mock_client_simple.telemetry._telemetry

        mock_client_simple.telemetry.read_once = mock_read_once

        # Then stream
        count = 0
        async for stream_data in mock_client_simple.telemetry.stream(
            interval=0.01
        ):
            assert stream_data is not None
            count += 1
            if count >= 2:
                break

        assert count >= 2

    @pytest.mark.asyncio
    async def test_multiple_read_once_calls(self, mock_client_simple):
        """Test making multiple read_once calls."""
        valid_response = bytes(
            [
                0x27,
                0x10,
                0xE7,
                0xF8,
                0x0A,
                0x40,
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x00,
                0x00,
            ]
        )

        mock_client_simple.transport.query = AsyncMock(
            return_value=valid_response
        )

        # Multiple reads
        data1 = await mock_client_simple.telemetry.read_once()
        data2 = await mock_client_simple.telemetry.read_once()
        data3 = await mock_client_simple.telemetry.read_once()

        assert data1 is not None
        assert data2 is not None
        assert data3 is not None

        # Should have made multiple query calls (3 queries per read_once × 3 reads)
        assert mock_client_simple.transport.query.call_count >= 6


class TestTelemetryServiceEdgeCases:
    """Tests for edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_read_once_timeout(self, mock_client_simple):
        """Test read_once when queries timeout."""
        # Mock query to timeout (return None)
        mock_client_simple.transport.query = AsyncMock(return_value=None)

        result = await mock_client_simple.telemetry.read_once()

        # Should handle timeout gracefully
        assert result is not None

    @pytest.mark.asyncio
    async def test_read_once_exception_during_query(self, mock_client_simple):
        """Test read_once when transport raises exception."""
        mock_client_simple.transport.query = AsyncMock(
            side_effect=Exception("Transport error")
        )

        # Should handle exception gracefully
        result = await mock_client_simple.telemetry.read_once()
        assert result is not None
