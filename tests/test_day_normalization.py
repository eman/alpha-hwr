import pytest
from alpha_hwr.models import ScheduleEntry


def test_day_normalization():
    """Test that day names are normalized to title case and validated correctly."""
    # Test lowercase
    entry = ScheduleEntry(
        day="monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
    )
    assert entry.day == "Monday"

    # Test mixed case
    entry = ScheduleEntry(
        day="tUeSdAy", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
    )
    assert entry.day == "Tuesday"

    # Test already correct case
    entry = ScheduleEntry(
        day="Wednesday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
    )
    assert entry.day == "Wednesday"

    # Test invalid day
    with pytest.raises(ValueError, match="Day must be one of"):
        ScheduleEntry(
            day="notaday",
            begin_hour=6,
            begin_minute=0,
            end_hour=8,
            end_minute=0,
        )


def test_day_index_with_normalization():
    """Test day_index property works with normalized days."""
    entry = ScheduleEntry(
        day="sunday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0
    )
    assert entry.day == "Sunday"
    assert entry.day_index == 6
