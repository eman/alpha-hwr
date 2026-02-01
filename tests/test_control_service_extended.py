"""
Extended tests for control service operations.

This module tests additional ControlService methods not covered by existing tests:
- set_constant_speed() - Set constant speed mode
- set_proportional_pressure() - Set proportional pressure mode
- set_autoadapt_radiator() - Set AutoAdapt radiator mode
- set_autoadapt_underfloor() - Set AutoAdapt underfloor mode
- set_autoadapt_combined() - Set AutoAdapt combined mode
- set_autoadapt() - Set generic AutoAdapt mode
"""

import pytest
from unittest.mock import AsyncMock


class TestSetConstantSpeed:
    """Tests for set_constant_speed() method."""

    @pytest.mark.asyncio
    async def test_set_constant_speed_valid(self, mock_client_simple):
        """Test setting constant speed with valid RPM value."""
        # Mock transport.query() which is used by _send_with_retry
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"  # Minimal Class 3 response
        )

        result = await mock_client_simple.control.set_constant_speed(2500.0)

        assert result is True
        assert mock_client_simple.transport.query.call_count >= 2

    @pytest.mark.asyncio
    async def test_set_constant_speed_min_value(self, mock_client_simple):
        """Test setting constant speed at minimum valid RPM (500)."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_constant_speed(500.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_constant_speed_max_value(self, mock_client_simple):
        """Test setting constant speed at maximum valid RPM (4500)."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_constant_speed(4500.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_constant_speed_too_low(self, mock_client_simple):
        """Test setting constant speed below minimum (< 500 RPM)."""
        result = await mock_client_simple.control.set_constant_speed(400.0)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_constant_speed_too_high(self, mock_client_simple):
        """Test setting constant speed above maximum (> 4500 RPM)."""
        result = await mock_client_simple.control.set_constant_speed(5000.0)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_constant_speed_typical_values(self, mock_client_simple):
        """Test setting constant speed with typical residential values."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        # Test typical values: 1500, 2000, 2500, 3000 RPM
        for rpm in [1500.0, 2000.0, 2500.0, 3000.0]:
            result = await mock_client_simple.control.set_constant_speed(rpm)
            assert result is True


class TestSetProportionalPressure:
    """Tests for set_proportional_pressure() method."""

    @pytest.mark.asyncio
    async def test_set_proportional_pressure_valid(self, mock_client_simple):
        """Test setting proportional pressure with valid value."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_proportional_pressure(2.5)

        assert result is True
        assert mock_client_simple.transport.query.call_count >= 2

    @pytest.mark.asyncio
    async def test_set_proportional_pressure_min_value(
        self, mock_client_simple
    ):
        """Test setting proportional pressure at minimum (0.5m)."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_proportional_pressure(0.5)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_proportional_pressure_max_value(
        self, mock_client_simple
    ):
        """Test setting proportional pressure at maximum (10m)."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_proportional_pressure(
            10.0
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_proportional_pressure_too_low(self, mock_client_simple):
        """Test setting proportional pressure below minimum (< 0.5m)."""
        result = await mock_client_simple.control.set_proportional_pressure(0.3)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_proportional_pressure_too_high(self, mock_client_simple):
        """Test setting proportional pressure above maximum (> 10m)."""
        result = await mock_client_simple.control.set_proportional_pressure(
            12.0
        )

        assert result is False


class TestSetAutoadaptModes:
    """Tests for AutoAdapt mode setting methods."""

    @pytest.mark.asyncio
    async def test_set_autoadapt_radiator_valid(self, mock_client_simple):
        """Test setting AutoAdapt Radiator mode with valid pressure."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_autoadapt_radiator(3.0)

        assert result is True
        assert mock_client_simple.transport.query.call_count >= 2

    @pytest.mark.asyncio
    async def test_set_autoadapt_radiator_min_value(self, mock_client_simple):
        """Test AutoAdapt Radiator at minimum pressure (0.5m)."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_autoadapt_radiator(0.5)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_autoadapt_radiator_max_value(self, mock_client_simple):
        """Test AutoAdapt Radiator at maximum pressure (10m)."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_autoadapt_radiator(10.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_autoadapt_radiator_too_low(self, mock_client_simple):
        """Test AutoAdapt Radiator below minimum."""
        result = await mock_client_simple.control.set_autoadapt_radiator(0.3)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_autoadapt_radiator_too_high(self, mock_client_simple):
        """Test AutoAdapt Radiator above maximum."""
        result = await mock_client_simple.control.set_autoadapt_radiator(12.0)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_autoadapt_underfloor_valid(self, mock_client_simple):
        """Test setting AutoAdapt Underfloor mode with valid pressure."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_autoadapt_underfloor(2.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_autoadapt_underfloor_boundary_values(
        self, mock_client_simple
    ):
        """Test AutoAdapt Underfloor at boundary values."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        # Test min and max
        assert (
            await mock_client_simple.control.set_autoadapt_underfloor(0.5)
            is True
        )
        assert (
            await mock_client_simple.control.set_autoadapt_underfloor(10.0)
            is True
        )
        # Test out of bounds
        assert (
            await mock_client_simple.control.set_autoadapt_underfloor(0.3)
            is False
        )
        assert (
            await mock_client_simple.control.set_autoadapt_underfloor(12.0)
            is False
        )

    @pytest.mark.asyncio
    async def test_set_autoadapt_combined_valid(self, mock_client_simple):
        """Test setting AutoAdapt Combined mode with valid pressure."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_autoadapt_combined(3.5)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_autoadapt_combined_boundary_values(
        self, mock_client_simple
    ):
        """Test AutoAdapt Combined at boundary values."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        # Test min and max
        assert (
            await mock_client_simple.control.set_autoadapt_combined(0.5) is True
        )
        assert (
            await mock_client_simple.control.set_autoadapt_combined(10.0)
            is True
        )
        # Test out of bounds
        assert (
            await mock_client_simple.control.set_autoadapt_combined(0.3)
            is False
        )
        assert (
            await mock_client_simple.control.set_autoadapt_combined(12.0)
            is False
        )

    @pytest.mark.asyncio
    async def test_set_autoadapt_generic_valid(self, mock_client_simple):
        """Test setting generic AutoAdapt mode with valid pressure."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        result = await mock_client_simple.control.set_autoadapt(2.5)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_autoadapt_generic_boundary_values(
        self, mock_client_simple
    ):
        """Test generic AutoAdapt at boundary values."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        # Test min and max
        assert await mock_client_simple.control.set_autoadapt(0.5) is True
        assert await mock_client_simple.control.set_autoadapt(10.0) is True
        # Test out of bounds
        assert await mock_client_simple.control.set_autoadapt(0.3) is False
        assert await mock_client_simple.control.set_autoadapt(12.0) is False


class TestControlServiceErrorHandling:
    """Tests for error handling in control service methods."""

    @pytest.mark.asyncio
    async def test_set_constant_speed_transport_exception(
        self, mock_client_simple
    ):
        """Test set_constant_speed when transport raises exception."""
        # Mock query to raise exception after max retries
        mock_client_simple.transport.query = AsyncMock(
            side_effect=Exception("Transport error")
        )

        result = await mock_client_simple.control.set_constant_speed(2500.0)

        # Should fail after retries
        assert result is False

    @pytest.mark.asyncio
    async def test_set_proportional_pressure_transport_exception(
        self, mock_client_simple
    ):
        """Test set_proportional_pressure when transport raises exception."""
        mock_client_simple.transport.query = AsyncMock(
            side_effect=Exception("Transport error")
        )

        result = await mock_client_simple.control.set_proportional_pressure(2.5)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_autoadapt_radiator_transport_exception(
        self, mock_client_simple
    ):
        """Test set_autoadapt_radiator when transport raises exception."""
        mock_client_simple.transport.query = AsyncMock(
            side_effect=Exception("Transport error")
        )

        result = await mock_client_simple.control.set_autoadapt_radiator(3.0)

        assert result is False


class TestControlServiceIntegration:
    """Integration tests for control service operations."""

    @pytest.mark.asyncio
    async def test_mode_switching_sequence(self, mock_client_simple):
        """Test switching between different control modes."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        # Switch through multiple modes
        assert (
            await mock_client_simple.control.set_constant_speed(2500.0) is True
        )
        assert (
            await mock_client_simple.control.set_proportional_pressure(2.5)
            is True
        )
        assert (
            await mock_client_simple.control.set_autoadapt_radiator(3.0) is True
        )
        assert (
            await mock_client_simple.control.set_autoadapt_underfloor(2.0)
            is True
        )

        # Each mode switch should have made query calls (set_mode + set_setpoint)
        assert mock_client_simple.transport.query.call_count >= 8

    @pytest.mark.asyncio
    async def test_setpoint_validation_across_modes(self, mock_client_simple):
        """Test that validation works correctly across different modes."""
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x27\x07\xe7\xf8\x03\x00\x00"
        )

        # Valid values for each mode
        assert (
            await mock_client_simple.control.set_constant_speed(2500.0) is True
        )
        assert (
            await mock_client_simple.control.set_proportional_pressure(5.0)
            is True
        )
        assert (
            await mock_client_simple.control.set_autoadapt_radiator(4.0) is True
        )

        # Invalid values for each mode
        assert (
            await mock_client_simple.control.set_constant_speed(100.0) is False
        )
        assert (
            await mock_client_simple.control.set_proportional_pressure(15.0)
            is False
        )
        assert (
            await mock_client_simple.control.set_autoadapt_radiator(15.0)
            is False
        )
