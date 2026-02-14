"""
Event log service for Grundfos ALPHA HWR pumps.

This service provides access to the pump's event log, which records historical
events such as start/stop cycles, mode changes, and errors.

Protocol Details
----------------
Event log data is stored in GENI DataObjects (Object 88):

1. **Event Log Metadata** (SubID 10199):
   - 7 bytes containing current state information
   - Structure (fully decoded):
     * Bytes 0-1: Current cycle counter (uint16 BE)
     * Bytes 2-3: Available entries (uint16 BE, 0-20)
     * Bytes 4-5: Max buffer size (uint16 BE, always 20)
     * Byte  6:   Reserved/flags (uint8, typically 0)

2. **Event Log Entries** (SubID 10200-10219):
   - 20 entries total (circular buffer)
   - SubID 10200 = newest (index 0)
   - SubID 10219 = oldest (index 19)
   - Each entry is 16 bytes

3. **Entry Structure** (16 bytes):
   - Bytes 0-1: Unknown header (uint16 BE)
   - Bytes 2-3: Unknown field (uint16 BE)
   - Byte 4: Cycle counter
   - Byte 5: Unknown byte
   - Byte 6: Mode byte (0x48 = constant pressure observed)
   - Byte 7-8: Constants
   - Byte 9: Event type flag (0x01 = start, 0x02 = stop)
   - Bytes 10-13: Unix timestamp (uint32 BE)
   - Bytes 14-15: Trailing data (uint16 BE)

Example (TypeScript):
```typescript
async getEventLogEntries(): Promise<EventLogEntry[]> {
    const entries: EventLogEntry[] = [];

    for (let subid = 10200; subid <= 10219; subid++) {
        const data = await this.readObject(88, subid);
        if (data && data.length === 16) {
            const entry = this.parseEventLogEntry(data, subid);
            entries.push(entry);
        }
    }

    return entries;
}

async getEventLogMetadata(): Promise<EventLogMetadata> {
    const data = await this.readObject(88, 10199);

    // Parse 7-byte structure
    const currentCycle = data.readUInt16BE(0);
    const availableEntries = data.readUInt16BE(2);
    const maxBufferSize = data.readUInt16BE(4);
    const reserved = data[6];

    return {
        currentCycle,
        availableEntries,
        maxBufferSize,
        reserved
    };
}
```
"""

from __future__ import annotations

import logging
import struct
import warnings
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from .base import BaseService

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport

from alpha_hwr.models import EventLogEntry, EventLogMetadata

logger = logging.getLogger(__name__)


class EventLogService(BaseService):
    """
    Service for accessing pump event log.

    The pump maintains a circular buffer of 20 event log entries that record
    historical events such as pump start/stop cycles, mode changes, and errors.

    Example:
        >>> from alpha_hwr.services import EventLogService
        >>>
        >>> # Initialize
        >>> event_log = EventLogService(transport, session)
        >>>
        >>> # Get all entries
        >>> entries = await event_log.get_all_entries()
        >>> for entry in entries:
        ...     print(f"{entry.timestamp}: Cycle {entry.cycle_counter}")
        >>>
        >>> # Get single entry
        >>> newest = await event_log.get_entry(0)
        >>> oldest = await event_log.get_entry(19)
    """

    def __init__(self, transport: Transport, session: Session) -> None:
        """
        Initialize event log service.

        Args:
            transport: Transport layer for BLE communication
            session: Session manager for state tracking
        """
        super().__init__(transport, session)

    async def get_entry(self, index: int) -> Optional[EventLogEntry]:
        """
        Read a single event log entry from the pump.

        Args:
            index: Entry index (0 = newest, 19 = oldest)

        Returns:
            EventLogEntry object, or None if read failed

        Raises:
            ValueError: If index is not in range 0-19
            ConnectionError: If not connected

        Example:
            >>> # Get newest entry
            >>> entry = await event_log.get_entry(0)
            >>> if entry:
            ...     print(f"Last event: {entry.timestamp}")
        """
        if not 0 <= index <= 19:
            raise ValueError(f"Index must be 0-19, got {index}")

        if not self.session.is_connected():
            raise ConnectionError("Not connected to pump")

        try:
            subid = 10200 + index
            data = await self._read_class10_object(88, subid)

            if not data or len(data) < 16:
                logger.warning(
                    f"Invalid event log entry data for index {index}"
                )
                return None

            # Skip 3-byte header if present
            payload = (
                data[3:] if len(data) > 19 and data[:2] == b"\x00\x00" else data
            )

            if len(payload) < 16:
                logger.warning(
                    f"Event log payload too short: {len(payload)} bytes for index {index}"
                )
                return None

            return self._parse_entry(payload[:16], index, subid)

        except Exception as e:
            logger.error(f"Error reading event log entry {index}: {e}")
            return None

    async def get_all_entries(self) -> list[EventLogEntry]:
        """
        Read all event log entries from the pump.

        Returns:
            List of EventLogEntry objects, ordered from newest (0) to oldest (19).
            Entries that fail to read will be skipped.

        Example:
            >>> entries = await event_log.get_all_entries()
            >>> print(f"Retrieved {len(entries)} event log entries")
            >>> for entry in entries[:5]:  # Show 5 most recent
            ...     print(f"  {entry.timestamp}: Cycle {entry.cycle_counter}")
        """
        if not self.session.is_connected():
            raise ConnectionError("Not connected to pump")

        logger.info("Fetching all event log entries...")

        entries = []

        for index in range(20):
            entry = await self.get_entry(index)
            if entry:
                entries.append(entry)

        logger.info(f"Retrieved {len(entries)}/20 event log entries")

        return entries

    async def get_metadata(self) -> Optional[EventLogMetadata]:
        """
        Read event log metadata from the pump.

        The metadata (SubID 10199) contains information about the current
        cycle counter and available entries.

        Structure (7 bytes):
        - Bytes 0-1: Current cycle counter (uint16 BE)
        - Bytes 2-3: Available entries (uint16 BE)
        - Bytes 4-5: Max buffer size (uint16 BE, always 20)
        - Byte  6:   Reserved/flags (uint8, typically 0)

        Returns:
            EventLogMetadata object with decoded fields, or None if read failed

        Example:
            >>> metadata = await event_log.get_metadata()
            >>> if metadata:
            ...     print(f"Current cycle: {metadata.current_cycle}")
            ...     print(f"Available entries: {metadata.available_entries}")
        """
        if not self.session.is_connected():
            raise ConnectionError("Not connected to pump")

        try:
            data = await self._read_class10_object(88, 10199)

            if not data:
                logger.warning("No data for event log metadata")
                return None

            # Skip 3-byte header if present
            payload = (
                data[3:] if len(data) > 3 and data[:2] == b"\x00\x00" else data
            )

            if len(payload) < 7:
                logger.warning(
                    f"Event log metadata too short: {len(payload)} bytes, expected 7"
                )
                return None

            # Parse metadata structure (7 bytes)
            current_cycle = struct.unpack(">H", payload[0:2])[0]
            available_entries = struct.unpack(">H", payload[2:4])[0]
            max_buffer_size = struct.unpack(">H", payload[4:6])[0]
            reserved = payload[6]

            logger.debug(
                f"Decoded metadata: cycle={current_cycle}, "
                f"available={available_entries}, max={max_buffer_size}"
            )

            return EventLogMetadata(
                current_cycle=current_cycle,
                available_entries=available_entries,
                max_buffer_size=max_buffer_size,
                reserved=reserved,
                raw_hex=payload.hex(),
            )

        except Exception as e:
            logger.error(f"Error reading event log metadata: {e}")
            return None

    async def get_cycle_timestamps(
        self, count: int = 10
    ) -> list[datetime] | None:
        """
        Get timestamps of recent pump cycles from cycle timestamp map.

        .. deprecated::
            Use ``client.history.get_cycle_timestamps(count)`` instead.
            This method will be removed in a future release.

        Args:
            count: Number of timestamps to retrieve (10 or 100)

        Returns:
            List of datetime objects, or None if read failed
        """
        warnings.warn(
            "EventLogService.get_cycle_timestamps() is deprecated. "
            "Use HistoryService.get_cycle_timestamps() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from .history import HistoryService

        history = HistoryService(self.transport, self.session)
        return await history.get_cycle_timestamps(count)

    # Helper methods

    def _parse_entry(
        self, raw_data: bytes, index: int, subid: int
    ) -> Optional[EventLogEntry]:
        """
        Parse a 16-byte event log entry.

        Args:
            raw_data: Raw 16-byte response
            index: Entry index (0-19)
            subid: SubID (10200-10219)

        Returns:
            EventLogEntry object, or None if parsing failed
        """
        try:
            if len(raw_data) != 16:
                logger.warning(
                    f"Event log entry must be 16 bytes, got {len(raw_data)}"
                )
                return None

            # Parse fields based on investigation findings
            cycle_counter = raw_data[4]
            mode_byte = raw_data[6]
            event_type_flag = raw_data[9]

            # Parse Unix timestamp (big-endian uint32)
            timestamp_raw = struct.unpack(">I", raw_data[10:14])[0]
            timestamp = datetime.fromtimestamp(timestamp_raw, tz=timezone.utc)

            return EventLogEntry(
                index=index,
                subid=subid,
                cycle_counter=cycle_counter,
                timestamp=timestamp,
                mode_byte=mode_byte,
                event_type_flag=event_type_flag,
                raw_hex=raw_data.hex(),
            )

        except Exception as e:
            logger.error(f"Error parsing event log entry: {e}")
            return None
