"""
Tests for ScheduleEntry model and validation logic.
"""

import pytest
from pydantic import ValidationError
from unittest.mock import Mock

from alpha_hwr.models import ScheduleEntry
from alpha_hwr.services import ScheduleService


class TestScheduleEntryBasics:
    """Test basic ScheduleEntry creation and validation."""

    def test_create_valid_entry(self):
        """Test creating a valid schedule entry."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
        )
        assert entry.day == "Monday"
        assert entry.begin_hour == 6
        assert entry.begin_minute == 0
        assert entry.end_hour == 8
        assert entry.end_minute == 0
        assert entry.action == 0x02  # Default
        assert entry.layer == 0  # Default
        assert entry.enabled is True  # Default

    def test_invalid_day_name(self):
        """Test that invalid day names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduleEntry(
                day="Funday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
            )
        assert "Day must be one of" in str(exc_info.value)

    def test_invalid_hour_range(self):
        """Test that hours outside 0-23 are rejected."""
        with pytest.raises(ValidationError):
            ScheduleEntry(
                day="Monday",
                begin_hour=25,  # Invalid
                begin_minute=0,
                end_hour=8,
                end_minute=0,
            )

    def test_invalid_minute_range(self):
        """Test that minutes outside 0-59 are rejected."""
        with pytest.raises(ValidationError):
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=60,  # Invalid
                end_hour=8,
                end_minute=0,
            )

    def test_invalid_layer(self):
        """Test that layers outside 0-4 are rejected."""
        with pytest.raises(ValidationError):
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=5,  # Invalid (only 0-4 allowed)
            )


class TestScheduleEntryProperties:
    """Test ScheduleEntry computed properties."""

    def test_day_index(self):
        """Test day_index property."""
        assert (
            ScheduleEntry(
                day="Monday",
                begin_hour=0,
                begin_minute=0,
                end_hour=1,
                end_minute=0,
            ).day_index
            == 0
        )
        assert (
            ScheduleEntry(
                day="Tuesday",
                begin_hour=0,
                begin_minute=0,
                end_hour=1,
                end_minute=0,
            ).day_index
            == 1
        )
        assert (
            ScheduleEntry(
                day="Sunday",
                begin_hour=0,
                begin_minute=0,
                end_hour=1,
                end_minute=0,
            ).day_index
            == 6
        )

    def test_begin_time_format(self):
        """Test begin_time formatted string."""
        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=5, end_hour=8, end_minute=0
        )
        assert entry.begin_time == "06:05"

    def test_end_time_format(self):
        """Test end_time formatted string."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=18,
            end_minute=30,
        )
        assert entry.end_time == "18:30"

    def test_time_objects(self):
        """Test time object properties."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=30,
            end_hour=8,
            end_minute=45,
        )
        assert entry.begin_time_obj.hour == 6
        assert entry.begin_time_obj.minute == 30
        assert entry.end_time_obj.hour == 8
        assert entry.end_time_obj.minute == 45


class TestScheduleEntryDuration:
    """Test duration calculation including midnight crossing."""

    def test_simple_duration(self):
        """Test simple duration within same day."""
        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )
        assert entry.get_duration_minutes() == 120  # 2 hours

    def test_duration_with_minutes(self):
        """Test duration calculation with minutes."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=30,
            end_hour=8,
            end_minute=45,
        )
        assert entry.get_duration_minutes() == 135  # 2h 15m

    def test_midnight_crossing_duration(self):
        """Test duration when crossing midnight."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=22,
            begin_minute=0,
            end_hour=2,
            end_minute=0,
        )
        assert entry.get_duration_minutes() == 240  # 4 hours (22:00-02:00)

    def test_crosses_midnight_flag(self):
        """Test crosses_midnight() method."""
        normal = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )
        assert not normal.crosses_midnight()

        crossing = ScheduleEntry(
            day="Monday",
            begin_hour=22,
            begin_minute=0,
            end_hour=2,
            end_minute=0,
        )
        assert crossing.crosses_midnight()

    def test_zero_duration_detected(self):
        """Test that zero duration entries are detected as invalid."""
        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=6, end_minute=0
        )
        is_valid, error = entry.is_valid_time_range()
        assert not is_valid
        assert error is not None
        assert "identical" in error


class TestScheduleEntryOverlap:
    """Test overlap detection between schedule entries."""

    def test_no_overlap_separate_times(self):
        """Test that separate time slots don't overlap."""
        entry1 = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )
        entry2 = ScheduleEntry(
            day="Monday",
            begin_hour=10,
            begin_minute=0,
            end_hour=12,
            end_minute=0,
        )
        assert not entry1.overlaps_with(entry2)
        assert not entry2.overlaps_with(entry1)

    def test_no_overlap_adjacent_times(self):
        """Test that adjacent time slots don't overlap (boundary condition)."""
        entry1 = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )
        entry2 = ScheduleEntry(
            day="Monday",
            begin_hour=8,
            begin_minute=0,
            end_hour=10,
            end_minute=0,
        )
        assert not entry1.overlaps_with(entry2)
        assert not entry2.overlaps_with(entry1)

    def test_overlap_partial(self):
        """Test partial overlap detection."""
        entry1 = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )
        entry2 = ScheduleEntry(
            day="Monday", begin_hour=7, begin_minute=0, end_hour=9, end_minute=0
        )
        assert entry1.overlaps_with(entry2)
        assert entry2.overlaps_with(entry1)

    def test_overlap_complete_containment(self):
        """Test overlap when one entry completely contains another."""
        entry1 = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=10,
            end_minute=0,
        )
        entry2 = ScheduleEntry(
            day="Monday", begin_hour=7, begin_minute=0, end_hour=8, end_minute=0
        )
        assert entry1.overlaps_with(entry2)
        assert entry2.overlaps_with(entry1)

    def test_no_overlap_different_days(self):
        """Test that entries on different days don't overlap."""
        entry1 = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )
        entry2 = ScheduleEntry(
            day="Tuesday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
        )
        assert not entry1.overlaps_with(entry2)

    def test_no_overlap_different_layers(self):
        """Test that entries on different layers don't overlap."""
        entry1 = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
            layer=0,
        )
        entry2 = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
            layer=1,
        )
        assert not entry1.overlaps_with(entry2)

    def test_no_overlap_disabled_entry(self):
        """Test that disabled entries don't trigger overlap."""
        entry1 = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
            enabled=False,
        )
        entry2 = ScheduleEntry(
            day="Monday", begin_hour=7, begin_minute=0, end_hour=9, end_minute=0
        )
        assert not entry1.overlaps_with(entry2)
        assert not entry2.overlaps_with(entry1)

    def test_overlap_midnight_crossing(self):
        """Test overlap detection with midnight-crossing entries."""
        # Entry1: 22:00-02:00 (crosses midnight)
        entry1 = ScheduleEntry(
            day="Monday",
            begin_hour=22,
            begin_minute=0,
            end_hour=2,
            end_minute=0,
        )
        # Entry2: 01:00-03:00 (overlaps with entry1's morning segment)
        entry2 = ScheduleEntry(
            day="Monday", begin_hour=1, begin_minute=0, end_hour=3, end_minute=0
        )
        assert entry1.overlaps_with(entry2)

    def test_overlap_both_midnight_crossing(self):
        """Test overlap when both entries cross midnight."""
        entry1 = ScheduleEntry(
            day="Monday",
            begin_hour=22,
            begin_minute=0,
            end_hour=2,
            end_minute=0,
        )
        entry2 = ScheduleEntry(
            day="Monday",
            begin_hour=23,
            begin_minute=0,
            end_hour=1,
            end_minute=0,
        )
        assert entry1.overlaps_with(entry2)


class TestScheduleEntryBinaryFormat:
    """Test binary serialization and deserialization."""

    def test_to_bytes(self):
        """Test converting ScheduleEntry to binary format."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=30,
            end_hour=8,
            end_minute=45,
            action=0x02,
            enabled=True,
        )
        data = entry.to_bytes()
        assert len(data) == 6
        assert data[0] == 0x01  # Enabled
        assert data[1] == 0x02  # Action
        assert data[2] == 6  # Begin hour
        assert data[3] == 30  # Begin minute
        assert data[4] == 8  # End hour
        assert data[5] == 45  # End minute

    def test_to_bytes_disabled(self):
        """Test binary format for disabled entry."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
            enabled=False,
        )
        data = entry.to_bytes()
        assert data[0] == 0x00  # Disabled

    def test_from_bytes(self):
        """Test parsing ScheduleEntry from binary format."""
        data = bytes([0x01, 0x02, 6, 30, 8, 45])
        entry = ScheduleEntry.from_bytes(data, day="Monday", layer=0)
        assert entry.day == "Monday"
        assert entry.enabled is True
        assert entry.action == 0x02
        assert entry.begin_hour == 6
        assert entry.begin_minute == 30
        assert entry.end_hour == 8
        assert entry.end_minute == 45
        assert entry.layer == 0

    def test_round_trip_binary(self):
        """Test round-trip conversion to/from binary."""
        original = ScheduleEntry(
            day="Wednesday",
            begin_hour=18,
            begin_minute=0,
            end_hour=20,
            end_minute=30,
            action=0x02,
            layer=2,
        )
        data = original.to_bytes()
        restored = ScheduleEntry.from_bytes(data, day="Wednesday", layer=2)
        assert original.begin_hour == restored.begin_hour
        assert original.begin_minute == restored.begin_minute
        assert original.end_hour == restored.end_hour
        assert original.end_minute == restored.end_minute
        assert original.action == restored.action
        assert original.enabled == restored.enabled


class TestScheduleEntryDictFormat:
    """Test dictionary serialization and deserialization."""

    def test_to_dict(self):
        """Test converting ScheduleEntry to dictionary."""
        entry = ScheduleEntry(
            day="Monday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
            layer=1,
        )
        d = entry.to_dict()
        assert d["day"] == "Monday"
        assert d["begin_hour"] == 6
        assert d["begin_minute"] == 0
        assert d["end_hour"] == 8
        assert d["end_minute"] == 0
        assert d["begin_time"] == "06:00"
        assert d["end_time"] == "08:00"
        assert d["layer"] == 1
        assert d["enabled"] is True

    def test_from_dict(self):
        """Test creating ScheduleEntry from dictionary."""
        d = {
            "day": "Tuesday",
            "begin_hour": 18,
            "begin_minute": 30,
            "end_hour": 20,
            "end_minute": 0,
            "action": 0x02,
            "layer": 2,
            "enabled": True,
        }
        entry = ScheduleEntry.from_dict(d)
        assert entry.day == "Tuesday"
        assert entry.begin_hour == 18
        assert entry.begin_minute == 30
        assert entry.end_hour == 20
        assert entry.end_minute == 0
        assert entry.layer == 2

    def test_round_trip_dict(self):
        """Test round-trip conversion to/from dictionary."""
        original = ScheduleEntry(
            day="Friday",
            begin_hour=12,
            begin_minute=15,
            end_hour=14,
            end_minute=45,
            layer=3,
        )
        d = original.to_dict()
        restored = ScheduleEntry.from_dict(d)
        assert original.day == restored.day
        assert original.begin_hour == restored.begin_hour
        assert original.begin_minute == restored.begin_minute
        assert original.end_hour == restored.end_hour
        assert original.end_minute == restored.end_minute
        assert original.layer == restored.layer


class TestClientScheduleValidation:
    """Test schedule validation via client.schedule.validate_entries() method."""

    def test_validate_empty_list(self):
        """Test validating empty schedule list."""
        # Create a minimal ScheduleService for validation (doesn't need transport/session)
        service = ScheduleService(session=Mock(), transport=Mock())
        is_valid, errors = service.validate_entries([])
        assert is_valid
        assert len(errors) == 0

    def test_validate_single_valid_entry(self):
        """Test validating single valid entry."""
        service = ScheduleService(session=Mock(), transport=Mock())
        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
        )
        is_valid, errors = service.validate_entries([entry])
        assert is_valid
        assert len(errors) == 0

    def test_validate_multiple_valid_entries(self):
        """Test validating multiple valid entries."""
        service = ScheduleService(session=Mock(), transport=Mock())
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
                begin_hour=18,
                begin_minute=0,
                end_hour=20,
                end_minute=0,
            ),
            ScheduleEntry(
                day="Tuesday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
            ),
        ]
        is_valid, errors = service.validate_entries(entries)
        assert is_valid
        assert len(errors) == 0

    def test_validate_detects_overlap(self):
        """Test that validation detects overlapping entries."""
        service = ScheduleService(session=Mock(), transport=Mock())
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
                begin_hour=7,
                begin_minute=0,
                end_hour=9,
                end_minute=0,
            ),  # Overlaps
        ]
        is_valid, errors = service.validate_entries(entries)
        assert not is_valid
        assert len(errors) > 0
        assert "Overlap detected" in errors[0]

    def test_validate_zero_duration(self):
        """Test that validation detects zero-duration entries."""
        service = ScheduleService(session=Mock(), transport=Mock())
        entry = ScheduleEntry(
            day="Monday", begin_hour=6, begin_minute=0, end_hour=6, end_minute=0
        )
        is_valid, errors = service.validate_entries([entry])
        assert not is_valid
        assert len(errors) > 0
        assert "identical" in errors[0]

    def test_validate_from_dict(self):
        """Test validation works with dictionary input."""
        service = ScheduleService(session=Mock(), transport=Mock())
        entries = [
            {
                "day": "Monday",
                "begin_hour": 6,
                "begin_minute": 0,
                "end_hour": 8,
                "end_minute": 0,
                "action": 0x02,
                "layer": 0,
                "enabled": True,
            }
        ]
        is_valid, errors = service.validate_entries(entries)
        assert is_valid
        assert len(errors) == 0

    def test_validate_different_layers_no_conflict(self):
        """Test that same time on different layers doesn't conflict."""
        service = ScheduleService(session=Mock(), transport=Mock())
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
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                layer=1,
            ),
        ]
        is_valid, errors = service.validate_entries(entries)
        assert is_valid
        assert len(errors) == 0

    def test_validate_disabled_entries_no_conflict(self):
        """Test that disabled entries don't cause conflicts."""
        service = ScheduleService(session=Mock(), transport=Mock())
        entries = [
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                enabled=False,
            ),
            ScheduleEntry(
                day="Monday",
                begin_hour=7,
                begin_minute=0,
                end_hour=9,
                end_minute=0,
            ),
        ]
        is_valid, errors = service.validate_entries(entries)
        assert is_valid
        assert len(errors) == 0
