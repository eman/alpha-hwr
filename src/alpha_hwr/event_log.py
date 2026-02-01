"""Event log decoder for ALPHA HWR historical data."""

import struct
from datetime import datetime, timezone
from typing import Dict, List


class EventLogEntry:
    """Represents a single event log entry from the pump."""

    def __init__(self, raw_data: bytes, subid: int):
        """
        Parse a 16-byte event log entry.

        Args:
            raw_data: Raw 16-byte response from SubID 10200-10219
            subid: The SubID this entry was read from (10200-10219)
        """
        if len(raw_data) != 16:
            raise ValueError(
                f"Event log entry must be 16 bytes, got {len(raw_data)}"
            )

        self.raw_data = raw_data
        self.subid = subid
        self.index = subid - 10200  # 0 = newest, 19 = oldest

        # Parse fields (based on investigation findings)
        self.unknown_header = struct.unpack(">H", raw_data[0:2])[0]
        self.unknown_field = struct.unpack(">H", raw_data[2:4])[0]
        self.cycle_counter = raw_data[4]
        self.unknown_byte = raw_data[5]
        self.mode_byte = raw_data[6]
        self.constant_1 = raw_data[7]
        self.constant_2 = raw_data[8]
        self.event_type_flag = raw_data[9]

        # Parse Unix timestamp (big-endian uint32)
        timestamp_raw = struct.unpack(">I", raw_data[10:14])[0]
        self.timestamp = datetime.fromtimestamp(timestamp_raw, tz=timezone.utc)

        self.trailing_data = struct.unpack(">H", raw_data[14:16])[0]

    def __repr__(self) -> str:
        return (
            f"EventLogEntry(index={self.index}, cycle={self.cycle_counter}, "
            f"timestamp={self.timestamp.isoformat()}, mode=0x{self.mode_byte:02X}, "
            f"event_type={self.event_type_flag})"
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "index": self.index,
            "subid": self.subid,
            "cycle_counter": self.cycle_counter,
            "timestamp": self.timestamp,
            "timestamp_iso": self.timestamp.isoformat(),
            "mode_byte": self.mode_byte,
            "mode_char": chr(self.mode_byte)
            if 32 <= self.mode_byte <= 126
            else None,
            "event_type_flag": self.event_type_flag,
            "raw_hex": self.raw_data.hex(),
        }


class CycleTimestampMap:
    """Represents the cycle timestamp map (SubID 13300)."""

    def __init__(self, raw_data: bytes):
        """
        Parse the 43-byte cycle timestamp map.

        Args:
            raw_data: Raw 43-byte response from SubID 13300
        """
        if len(raw_data) != 43:
            raise ValueError(
                f"Cycle timestamp map must be 43 bytes, got {len(raw_data)}"
            )

        self.raw_data = raw_data

        # First 3 bytes are header: 00 00 28 (0x28 = 40 bytes of data)
        self.header = raw_data[0:3]

        # Next 40 bytes contain 10 timestamps (4 bytes each, big-endian)
        self.timestamps: List[datetime] = []
        for i in range(10):
            offset = 3 + (i * 4)
            timestamp_raw = struct.unpack(">I", raw_data[offset : offset + 4])[
                0
            ]
            dt = datetime.fromtimestamp(timestamp_raw, tz=timezone.utc)
            self.timestamps.append(dt)

    def __repr__(self) -> str:
        return f"CycleTimestampMap(count={len(self.timestamps)}, latest={self.timestamps[0].isoformat()})"

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "count": len(self.timestamps),
            "timestamps": [ts.isoformat() for ts in self.timestamps],
            "timestamps_unix": [int(ts.timestamp()) for ts in self.timestamps],
        }


class EventLogMetadata:
    """Represents event log metadata (SubID 10199)."""

    def __init__(self, raw_data: bytes):
        """
        Parse event log metadata.

        Args:
            raw_data: Raw response from SubID 10199
        """
        self.raw_data = raw_data
        # Structure not fully decoded - will need live device testing
        # Based on investigation, this contains current cycle number and available entries

    def __repr__(self) -> str:
        return f"EventLogMetadata(raw={self.raw_data.hex()})"


def decode_event_log_entry(raw_data: bytes, subid: int) -> EventLogEntry:
    """
    Decode a single event log entry.

    Args:
        raw_data: Raw 16-byte response
        subid: SubID (10200-10219)

    Returns:
        Parsed EventLogEntry object
    """
    return EventLogEntry(raw_data, subid)


def decode_cycle_timestamps(raw_data: bytes) -> CycleTimestampMap:
    """
    Decode the cycle timestamp map.

    Args:
        raw_data: Raw 43-byte response from SubID 13300

    Returns:
        Parsed CycleTimestampMap object
    """
    return CycleTimestampMap(raw_data)


def decode_event_log_metadata(raw_data: bytes) -> EventLogMetadata:
    """
    Decode event log metadata.

    Args:
        raw_data: Raw response from SubID 10199

    Returns:
        Parsed EventLogMetadata object
    """
    return EventLogMetadata(raw_data)
