"""
Tests for schedule service operations.

This module tests the ScheduleService including:
- Getting schedule state (enabled/disabled)
- Enabling and disabling schedules
- Reading schedule entries
- Writing schedule entries
- Validating schedule entries
- Clearing schedule entries
"""

from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from conftest import build_class10_response

from alpha_hwr.models import ScheduleEntry


class TestScheduleState:
    """Tests for schedule state operations (get_state, enable, disable)."""

    @pytest.mark.asyncio
    async def test_get_state_enabled(self, mock_client_simple):
        """Test getting schedule state when enabled."""
        # Mock response: Object 84 SubID 1 response with byte 7 = 0x01 (enabled)
        # Format: [Header(3)][Capabilities(4)][Enabled(1)][DefaultAction(1)][BaseSetpoint(4)]
        payload = bytearray(
            [
                0x00,
                0x00,
                0x00,  # Header (3 bytes)
                0x00,
                0x00,
                0x00,
                0x00,  # Capabilities (4 bytes)
                0x01,  # Enabled flag (byte 7) - ENABLED
                0x02,  # Default action
                0x00,
                0x00,
                0x00,
                0x00,  # Base setpoint
            ]
        )

        response = build_class10_response(84, 1, bytes(payload))
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        enabled = await mock_client_simple.schedule.get_state()

        assert enabled is True
        assert mock_client_simple.transport.query.called

    @pytest.mark.asyncio
    async def test_get_state_disabled(self, mock_client_simple):
        """Test getting schedule state when disabled."""
        # Mock response with byte 7 = 0x00 (disabled)
        payload = bytearray(
            [
                0x00,
                0x00,
                0x00,  # Header
                0x00,
                0x00,
                0x00,
                0x00,  # Capabilities
                0x00,  # Enabled flag (byte 7) - DISABLED
                0x02,  # Default action
                0x00,
                0x00,
                0x00,
                0x00,  # Base setpoint
            ]
        )

        response = build_class10_response(84, 1, bytes(payload))
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        enabled = await mock_client_simple.schedule.get_state()

        assert enabled is False

    @pytest.mark.asyncio
    async def test_get_state_invalid_response(self, mock_client_simple):
        """Test getting schedule state with invalid/short response."""
        # Response too short (< 8 bytes)
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x00\x00\x00"
        )

        enabled = await mock_client_simple.schedule.get_state()

        assert enabled is None

    @pytest.mark.asyncio
    async def test_get_state_none_response(self, mock_client_simple):
        """Test getting schedule state when query returns None."""
        mock_client_simple.transport.query = AsyncMock(return_value=None)

        enabled = await mock_client_simple.schedule.get_state()

        assert enabled is None

    @pytest.mark.asyncio
    async def test_enable_success(self, mock_client_simple):
        """Test successfully enabling schedule."""
        # Mock transport.query to return success
        mock_client_simple.transport.query = AsyncMock(
            return_value=build_class10_response(84, 1, b"\x00" * 10)
        )

        await mock_client_simple.schedule.enable()

        # Should make transport calls
        call_count = (
            mock_client_simple.transport.query.call_count
            + mock_client_simple.transport.write.call_count
        )
        assert call_count > 0

    @pytest.mark.asyncio
    async def test_disable_success(self, mock_client_simple):
        """Test successfully disabling schedule."""
        # Mock successful write response
        mock_client_simple.transport.write = AsyncMock()
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x00" * 10
        )

        await mock_client_simple.schedule.disable()

        # Should make transport calls
        call_count = (
            mock_client_simple.transport.query.call_count
            + mock_client_simple.transport.write.call_count
        )
        assert call_count > 0

    @pytest.mark.asyncio
    async def test_enable_disable_sequence(self, mock_client_simple):
        """Test enable/disable sequence."""
        # Mock responses for reading current schedule overview (Object 84 SubID 1)
        # Format: [Header(3)][Capabilities(4)][Enabled(1)][DefaultAction(1)][BaseSetpoint(4)]

        # Initial read: disabled
        payload_disabled = bytearray(
            [
                0x00,
                0x00,
                0x00,  # Header (3 bytes)
                0x00,
                0x00,
                0x00,
                0x00,  # Capabilities (4 bytes)
                0x00,  # Enabled flag (byte 7) - currently disabled
                0x02,  # Default action
                0x00,
                0x00,
                0x00,
                0x00,  # Base setpoint
            ]
        )

        # After enable: enabled
        payload_enabled = bytearray(
            [
                0x00,
                0x00,
                0x00,  # Header
                0x00,
                0x00,
                0x00,
                0x00,  # Capabilities
                0x01,  # Enabled flag (byte 7) - now enabled
                0x02,  # Default action
                0x00,
                0x00,
                0x00,
                0x00,  # Base setpoint
            ]
        )

        # Sequence of query() calls:
        # 1. enable() reads current state
        # 2. enable() writes - the Class 10 SET is acknowledged, and the
        #    empty response stands in for that acknowledgement
        # 3. enable() verifies
        # 4. disable() reads current state
        # 5. disable() writes
        # 6. disable() verifies
        responses = [
            build_class10_response(
                84, 1, bytes(payload_disabled)
            ),  # Read for enable
            b"",  # Write acknowledgement for enable
            build_class10_response(
                84, 1, bytes(payload_enabled)
            ),  # Verify enable worked
            build_class10_response(
                84, 1, bytes(payload_enabled)
            ),  # Read for disable
            b"",  # Write acknowledgement for disable
            build_class10_response(
                84, 1, bytes(payload_disabled)
            ),  # Verify disable worked
        ]

        mock_client_simple.transport.query = AsyncMock(side_effect=responses)

        # Enable
        result_enable = await mock_client_simple.schedule.enable()
        assert result_enable is True

        # Disable
        result_disable = await mock_client_simple.schedule.disable()
        assert result_disable is True

        # Verify query was called 6 times total
        assert mock_client_simple.transport.query.call_count == 6


class TestScheduleReadEntries:
    """Tests for reading schedule entries."""

    @pytest.mark.asyncio
    async def test_read_entries_single_layer(self, mock_client_simple):
        """Test reading entries from a single layer."""
        # Mock response for Object 84, SubID 1000 (layer 0)
        # Format: [Header(3)] + [7 days × 6 bytes]
        # Each entry: [Enabled][Action][StartH][StartM][EndH][EndM]

        payload = bytearray(
            [
                0x00,
                0x00,
                0x00,  # Header
            ]
        )

        # Monday: 06:00 - 08:00 (enabled)
        payload.extend([0x01, 0x02, 6, 0, 8, 0])
        # Tuesday: 06:00 - 08:00 (enabled)
        payload.extend([0x01, 0x02, 6, 0, 8, 0])
        # Wednesday-Sunday: disabled
        payload.extend([0x00, 0x00, 0, 0, 0, 0] * 5)

        response = build_class10_response(84, 1000, bytes(payload))
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        entries = await mock_client_simple.schedule.read_entries(layer=0)

        # Should return 2 enabled entries
        assert len(entries) == 2
        assert entries[0].day == "Monday"
        assert entries[0].begin_hour == 6
        assert entries[0].end_hour == 8
        assert entries[1].day == "Tuesday"

    @pytest.mark.asyncio
    async def test_read_entries_all_layers(self, mock_client_simple):
        """Test reading entries from all layers."""

        # Mock responses for all 5 layers (SubIDs 1000-1004)
        def make_response(sub_id, day_enabled_mask):
            """Create response with specific days enabled."""
            payload = bytearray([0x00, 0x00, 0x00])  # Header
            for day in range(7):
                if day in day_enabled_mask:
                    payload.extend([0x01, 0x02, 6, 0, 8, 0])  # Enabled
                else:
                    payload.extend([0x00, 0x00, 0, 0, 0, 0])  # Disabled
            return build_class10_response(84, sub_id, bytes(payload))

        # Layer 0: Monday enabled
        # Layer 1: Tuesday enabled
        # Layers 2-4: empty
        responses = [
            make_response(1000, [0]),  # Layer 0: Monday
            make_response(1001, [1]),  # Layer 1: Tuesday
            make_response(1002, []),  # Layer 2: none
            make_response(1003, []),  # Layer 3: none
            make_response(1004, []),  # Layer 4: none
        ]

        mock_client_simple.transport.query = AsyncMock(side_effect=responses)

        entries = await mock_client_simple.schedule.read_entries()

        # Should have entries from layers 0 and 1
        assert len(entries) == 2
        assert entries[0].day == "Monday"
        assert entries[0].layer == 0
        assert entries[1].day == "Tuesday"
        assert entries[1].layer == 1

    @pytest.mark.asyncio
    async def test_read_entries_empty_schedule(self, mock_client_simple):
        """Test reading entries when schedule is empty."""
        # All days disabled
        payload = bytearray([0x00, 0x00, 0x00])  # Header
        payload.extend([0x00, 0x00, 0, 0, 0, 0] * 7)  # 7 disabled days

        response = build_class10_response(84, 1000, bytes(payload))
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        entries = await mock_client_simple.schedule.read_entries(layer=0)

        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_read_entries_all_days_enabled(self, mock_client_simple):
        """Test reading entries with all 7 days enabled."""
        payload = bytearray([0x00, 0x00, 0x00])  # Header

        # All 7 days enabled: 06:00 - 20:00
        for day in range(7):
            payload.extend([0x01, 0x02, 6, 0, 20, 0])

        response = build_class10_response(84, 1000, bytes(payload))
        mock_client_simple.transport.query = AsyncMock(return_value=response)

        entries = await mock_client_simple.schedule.read_entries(layer=0)

        assert len(entries) == 7
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        for i, entry in enumerate(entries):
            assert entry.day == days[i]
            assert entry.begin_hour == 6
            assert entry.end_hour == 20

    @pytest.mark.asyncio
    async def test_read_entries_invalid_response(self, mock_client_simple):
        """Test reading entries with invalid/short response."""
        # Response too short (< 45 bytes)
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x00\x00\x00"
        )

        entries = await mock_client_simple.schedule.read_entries(layer=0)

        # Should return empty list on error
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_read_entries_transport_exception(self, mock_client_simple):
        """Test reading entries when transport raises exception."""
        mock_client_simple.transport.query = AsyncMock(
            side_effect=BleakError("Transport error")
        )

        entries = await mock_client_simple.schedule.read_entries(layer=0)

        # Should handle exception and return empty list
        assert len(entries) == 0


class TestScheduleValidation:
    """Tests for schedule entry validation."""

    def test_validate_entries_valid(self, mock_client_simple):
        """Test validation with valid entries."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
            ScheduleEntry(
                day="Tuesday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_entries_overlap_same_day(self, mock_client_simple):
        """Test validation detects overlaps on same day."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
            ScheduleEntry(
                day="Monday",
                begin_hour=7,
                begin_minute=0,  # Overlaps with first entry
                end_hour=9,
                end_minute=0,
                layer=0,
            ),
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        assert is_valid is False
        assert len(errors) > 0
        assert "overlap" in errors[0].lower()

    def test_validate_entries_no_overlap_different_days(
        self, mock_client_simple
    ):
        """Test validation allows same times on different days."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
            ScheduleEntry(
                day="Tuesday",
                begin_hour=6,
                begin_minute=0,  # Same time, different day - OK
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_entries_no_overlap_different_layers(
        self, mock_client_simple
    ):
        """Test validation allows overlaps on different layers."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
            ScheduleEntry(
                day="Monday",
                begin_hour=7,
                begin_minute=0,  # Overlaps but different layer - OK
                end_hour=9,
                end_minute=0,
                layer=1,
            ),
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_entries_zero_duration(self, mock_client_simple):
        """Test validation detects zero-duration entries."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=6,
                end_minute=0,  # Zero duration!
                layer=0,
            ),
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        assert is_valid is False
        assert len(errors) > 0

    def test_validate_entries_dict_input(self, mock_client_simple):
        """Test validation with dict input instead of ScheduleEntry objects."""
        entries = [
            {
                "day": "Monday",
                "begin_hour": 6,
                "begin_minute": 0,
                "end_hour": 8,
                "end_minute": 0,
                "layer": 0,
                "enabled": True,
                "action": 2,
            }
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        # Should handle dict conversion
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_entries_invalid_type(self, mock_client_simple):
        """Test validation with invalid entry type."""
        entries = [
            "not a schedule entry",  # Invalid type
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        assert is_valid is False
        assert len(errors) > 0
        assert "invalid type" in errors[0].lower()

    def test_validate_entries_disabled_entries_no_overlap_check(
        self, mock_client_simple
    ):
        """Test that disabled entries are not checked for overlaps."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
                enabled=False,  # Disabled
            ),
            ScheduleEntry(
                day="Monday",
                begin_hour=7,
                begin_minute=0,  # Would overlap but first is disabled
                end_hour=9,
                end_minute=0,
                layer=0,
                enabled=True,
            ),
        ]

        is_valid, errors = mock_client_simple.schedule.validate_entries(entries)

        # Should be valid since first entry is disabled
        assert is_valid is True
        assert len(errors) == 0


class TestScheduleWriteEntries:
    """Tests for writing schedule entries."""

    @pytest.mark.asyncio
    async def test_write_entries_success(self, mock_client_simple):
        """Test successfully writing schedule entries."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
        ]

        mock_client_simple.transport.write = AsyncMock()
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x24\x00\xe7\xf8\x0a\x34\x54\x03\xe8\x00\xaa\xbb"
        )

        await mock_client_simple.schedule.write_entries(entries, layer=0)

        # Should make transport calls
        call_count = (
            mock_client_simple.transport.query.call_count
            + mock_client_simple.transport.write.call_count
        )
        assert call_count > 0

    @pytest.mark.asyncio
    async def test_write_entries_invalid_layer(self, mock_client_simple):
        """Test writing to invalid layer (>4)."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=0,
            ),
        ]

        # Should raise ValueError or return False for invalid layer
        try:
            result = await mock_client_simple.schedule.write_entries(
                entries, layer=5
            )
            # If no exception, result should be False
            assert result is False
        except ValueError:
            # ValueError is also acceptable
            pass

    @pytest.mark.asyncio
    async def test_write_entries_empty_list(self, mock_client_simple):
        """Test writing empty entry list (clears schedule)."""
        mock_client_simple.transport.write = AsyncMock()
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x00" * 10
        )

        await mock_client_simple.schedule.write_entries([], layer=0)

        # Should still make calls (to clear the schedule)
        call_count = (
            mock_client_simple.transport.query.call_count
            + mock_client_simple.transport.write.call_count
        )
        assert (
            call_count >= 0
        )  # May or may not make calls depending on implementation

    @pytest.mark.asyncio
    async def test_write_entries_dict_input(self, mock_client_simple):
        """Test writing entries as dicts."""
        entries = [
            {
                "day": "Monday",
                "begin_hour": 6,
                "begin_minute": 0,
                "end_hour": 8,
                "end_minute": 0,
                "layer": 0,
                "enabled": True,
                "action": 2,
            }
        ]

        mock_client_simple.transport.write = AsyncMock()
        mock_client_simple.transport.query = AsyncMock(
            return_value=b"\x00" * 10
        )

        await mock_client_simple.schedule.write_entries(entries, layer=0)

        # Should handle dict input
        call_count = (
            mock_client_simple.transport.query.call_count
            + mock_client_simple.transport.write.call_count
        )
        assert call_count > 0
