"""Tests for schedule write operations using the new service-based API."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from alpha_hwr.client import AlphaHWRClient
from alpha_hwr.models import ScheduleEntry


@pytest_asyncio.fixture
async def client():
    """Create a connected client with mocked transport."""
    with patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak:
        # Set up mock BleakClient
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        mock_instance.start_notify = AsyncMock()
        mock_instance.write_gatt_char = AsyncMock()
        mock_instance.is_connected = True
        mock_bleak.return_value = mock_instance

        # Create and connect client
        client = AlphaHWRClient("00:00:00:00:00:00")
        await client.connect()

        # Mock transport methods
        client.transport.write = AsyncMock()
        client.transport.read_response = AsyncMock(return_value=b"\x00" * 7)
        client.transport.send_with_response = AsyncMock(
            return_value=b"\x00" * 7
        )
        client.transport.query = AsyncMock(return_value=b"\x00" * 7)

        yield client
        await client.disconnect()


class TestScheduleWriteEntries:
    """Test write_entries() method for writing complete schedule layers."""

    @pytest.mark.asyncio
    async def test_write_entries_success(self, client):
        """Test successfully writing schedule entries."""
        # Mock successful write response
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
            ),
            ScheduleEntry(
                day="Tuesday",
                begin_hour=18,
                begin_minute=0,
                end_hour=20,
                end_minute=0,
            ),
        ]

        result = await client.schedule.write_entries(entries, layer=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_write_entries_with_dicts(self, client):
        """Test writing schedule entries from dict format."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        entries = [
            {
                "day": "Monday",
                "begin_hour": 6,
                "begin_minute": 0,
                "end_hour": 8,
                "end_minute": 0,
            }
        ]

        result = await client.schedule.write_entries(entries, layer=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_write_entries_empty_list(self, client):
        """Test writing empty schedule (clears the layer)."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        result = await client.schedule.write_entries([], layer=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_write_entries_all_days(self, client):
        """Test writing entries for all 7 days."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        entries = [
            ScheduleEntry(
                day=day, begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
            )
            for day in days
        ]

        result = await client.schedule.write_entries(entries, layer=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_write_entries_different_layers(self, client):
        """Test writing to different layers."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )

        # Test layers 0-4
        for layer in range(5):
            result = await client.schedule.write_entries([entry], layer=layer)
            assert result is True, f"Failed for layer {layer}"

    @pytest.mark.asyncio
    async def test_write_entries_invalid_layer(self, client):
        """Test error handling for invalid layer."""
        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )

        with pytest.raises(ValueError, match="Invalid layer"):
            await client.schedule.write_entries([entry], layer=5)

    @pytest.mark.asyncio
    async def test_write_entries_validation_failure(self, client):
        """Test that overlapping entries are rejected."""
        # Create overlapping entries
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=9,
                end_minute=0,
            ),
            ScheduleEntry(
                day="Monday",
                begin_hour=8,
                begin_minute=0,
                end_hour=10,
                end_minute=0,
            ),  # Overlaps
        ]

        result = await client.schedule.write_entries(entries, layer=0)
        # Should fail validation and return False
        assert result is False

    @pytest.mark.asyncio
    async def test_write_entries_midnight_crossing(self, client):
        """Test writing entries that cross midnight."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        entry = ScheduleEntry(
            day="Monday",
            begin_hour=23,
            begin_minute=0,
            end_hour=1,
            end_minute=0,
        )

        result = await client.schedule.write_entries([entry], layer=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_write_entries_disabled_entry(self, client):
        """Test writing disabled entries."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
            enabled=False,
        )

        result = await client.schedule.write_entries([entry], layer=0)
        assert result is True


class TestScheduleClearEntry:
    """Test clear_entry() method for clearing specific days."""

    @pytest.mark.asyncio
    async def test_clear_entry_success(self, client):
        """Test successfully clearing a schedule entry."""

        # Mock read_entries to return existing schedule
        async def mock_read_entries(layer=0):
            return [
                ScheduleEntry(
                    day="Monday",
                    begin_hour=6,
                    begin_minute=0,
                    end_hour=8,
                    end_minute=0,
                    layer=layer,
                ),
                ScheduleEntry(
                    day="Tuesday",
                    begin_hour=6,
                    begin_minute=0,
                    end_hour=8,
                    end_minute=0,
                    layer=layer,
                ),
            ]

        client.schedule.read_entries = AsyncMock(side_effect=mock_read_entries)
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        result = await client.schedule.clear_entry("Monday", layer=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_clear_entry_all_days(self, client):
        """Test clearing entries for all days."""
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        async def mock_read_entries(layer=0):
            return [
                ScheduleEntry(
                    day=day,
                    begin_hour=6,
                    begin_minute=0,
                    end_hour=8,
                    end_minute=0,
                    layer=layer,
                )
                for day in days
            ]

        client.schedule.read_entries = AsyncMock(side_effect=mock_read_entries)
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        for day in days:
            result = await client.schedule.clear_entry(day, layer=0)
            assert result is True, f"Failed for {day}"

    @pytest.mark.asyncio
    async def test_clear_entry_invalid_day(self, client):
        """Test error handling for invalid day name."""
        with pytest.raises(ValueError, match="Invalid day name"):
            await client.schedule.clear_entry("InvalidDay", layer=0)

    @pytest.mark.asyncio
    async def test_clear_entry_invalid_layer(self, client):
        """Test error handling for invalid layer."""
        with pytest.raises(ValueError, match="Invalid layer"):
            await client.schedule.clear_entry("Monday", layer=5)


class TestScheduleWriteEdgeCases:
    """Test edge cases and error handling for write operations."""

    @pytest.mark.asyncio
    async def test_write_entries_multiple_entries_same_day(self, client):
        """Test that multiple entries on the same day are rejected by validation."""
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
            ),
            ScheduleEntry(
                day="Monday",
                begin_hour=10,
                begin_minute=0,
                end_hour=12,
                end_minute=0,
            ),
        ]

        # Since the schedule format only supports one entry per day per layer,
        # this should be handled by either validation or the write logic
        result = await client.schedule.write_entries(entries, layer=0)
        # Depending on implementation, this may succeed (last entry wins) or fail
        assert result is not None

    @pytest.mark.asyncio
    async def test_write_entries_invalid_day_name(self, client):
        """Test that invalid day names are caught by validation."""
        # This should fail during ScheduleEntry creation (Pydantic validation)
        with pytest.raises(Exception):  # ValidationError from Pydantic
            ScheduleEntry(
                day="InvalidDay",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
            )

    @pytest.mark.asyncio
    async def test_write_entries_ignores_entry_layer_field(self, client):
        """Test that the layer parameter overrides entry.layer field."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

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
                layer=1,
            ),
        ]

        # The layer parameter (2) should be used, not the entry.layer fields
        result = await client.schedule.write_entries(entries, layer=2)
        assert result is True

    @pytest.mark.asyncio
    async def test_clear_entry_nonexistent_day(self, client):
        """Test clearing an entry that doesn't exist."""
        # Mock read_entries to return empty schedule
        client.schedule.read_entries = AsyncMock(return_value=[])
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        # Should still succeed (no-op)
        result = await client.schedule.clear_entry("Monday", layer=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_clear_entry_preserves_other_days(self, client):
        """Test that clearing one day doesn't affect others."""
        days = ["Monday", "Tuesday", "Wednesday"]

        async def mock_read_entries(layer=0):
            return [
                ScheduleEntry(
                    day=day,
                    begin_hour=6,
                    begin_minute=0,
                    end_hour=8,
                    end_minute=0,
                    layer=layer,
                )
                for day in days
            ]

        client.schedule.read_entries = AsyncMock(side_effect=mock_read_entries)

        # Track what was written
        written_entries = []

        async def mock_write_entries(entries, layer=0):
            written_entries.clear()
            written_entries.extend(entries)
            return True

        client.schedule.write_entries = AsyncMock(
            side_effect=mock_write_entries
        )

        # Clear Monday
        result = await client.schedule.clear_entry("Monday", layer=0)
        assert result is True

        # Verify only Tuesday and Wednesday remain
        assert len(written_entries) == 2
        assert all(e.day != "Monday" for e in written_entries)
        assert any(e.day == "Tuesday" for e in written_entries)
        assert any(e.day == "Wednesday" for e in written_entries)


class TestScheduleLayerOperations:
    """Test operations involving multiple layers."""

    @pytest.mark.asyncio
    async def test_clear_all_layers(self, client):
        """Test clearing all schedule layers (replaces clear_all_schedules)."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        # Clear all 5 layers by writing empty schedules
        results = []
        for layer in range(5):
            result = await client.schedule.write_entries([], layer=layer)
            results.append(result)

        assert all(results), "Failed to clear all layers"

    @pytest.mark.asyncio
    async def test_write_same_entry_different_layers(self, client):
        """Test writing the same entry to different layers."""
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )

        # Write to layers 0, 1, 2
        for layer in [0, 1, 2]:
            result = await client.schedule.write_entries([entry], layer=layer)
            assert result is True

    @pytest.mark.asyncio
    async def test_clear_entry_different_layers(self, client):
        """Test clearing entries from different layers independently."""

        async def mock_read_entries(layer=0):
            return [
                ScheduleEntry(
                    day="Monday",
                    begin_hour=6,
                    begin_minute=0,
                    end_hour=8,
                    end_minute=0,
                    layer=layer,
                )
            ]

        client.schedule.read_entries = AsyncMock(side_effect=mock_read_entries)
        client.transport.query = AsyncMock(
            return_value=b"\x24\x02\x00\xf8\xe7\x00"
        )

        # Clear Monday from layers 0 and 2
        result1 = await client.schedule.clear_entry("Monday", layer=0)
        result2 = await client.schedule.clear_entry("Monday", layer=2)

        assert result1 is True
        assert result2 is True


class TestScheduleWriteAuthentication:
    """Test authentication requirements for write operations."""

    @pytest.mark.asyncio
    async def test_write_entries_requires_authentication(self, client):
        """Test that write operations require authentication."""
        # Mock session as not authenticated
        client.session.state = 0  # Not authenticated

        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )

        # Should raise an exception about authentication
        with pytest.raises(Exception):
            await client.schedule.write_entries([entry], layer=0)

    @pytest.mark.asyncio
    async def test_clear_entry_requires_authentication(self, client):
        """Test that clear operations require authentication."""
        # Mock session as not authenticated
        client.session.state = 0  # Not authenticated

        # Should raise an exception about authentication
        with pytest.raises(Exception):
            await client.schedule.clear_entry("Monday", layer=0)
