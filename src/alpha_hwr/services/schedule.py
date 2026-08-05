"""
Schedule Management Service for Grundfos ALPHA HWR pumps.

This module handles all schedule-related operations including reading, writing,
enabling/disabling schedules, and validation. The pump supports up to 5 schedule
layers (0-4), with each layer containing one time interval per day of the week.

Protocol Details:
-----------------
- Schedule state: Class 10, Object 1016 (ComfortLevelCheckUserSettings)
  - SubID discovered via scanning (typically 0x5400-0x5500 range)
  - Returns 1 byte: 0x01=enabled, 0x00=disabled

- Schedule entries: Class 10, Object 84
  - SubID: 1000 + layer (1000-1004 for layers 0-4)
  - Format: 3-byte header + (7 days × 6 bytes) = 45 bytes total
  - Each entry: [Enabled][Action][StartH][StartM][EndH][EndM]

- Enable/Disable: Class 10, OpSpec 0x90
  - Writes to Object 1016 at discovered SubID
  - Value: 0x01=enable, 0x00=disable
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from alpha_hwr.models import ScheduleEntry

from ..exceptions import READ_ERRORS
from ..protocol.matcher import Command
from .base import BaseService

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport

logger = logging.getLogger(__name__)


class ScheduleService(BaseService):
    """
    Manages pump schedule operations.

    Handles reading, writing, and validation of weekly pump schedules.
    The pump supports up to 5 schedule layers, with each layer containing
    one time interval per day of the week.

    Example:
        >>> service = ScheduleService(session, transport)
        >>>
        >>> # Check if schedule is enabled
        >>> enabled = await service.get_state()
        >>> print(f"Schedule enabled: {enabled}")
        >>>
        >>> # Read current schedule
        >>> entries = await service.read_entries()
        >>> for entry in entries:
        ...     print(f"{entry.day}: {entry.begin_time}-{entry.end_time}")
        >>>
        >>> # Write new schedule
        >>> new_entries = [
        ...     ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0,
        ...                   end_hour=8, end_minute=0),
        ...     ScheduleEntry(day="Tuesday", begin_hour=6, begin_minute=0,
        ...                   end_hour=8, end_minute=0),
        ... ]
        >>> success = await service.write_entries(new_entries, layer=0)
        >>>
        >>> # Enable schedule
        >>> await service.enable()
    """

    #: ClockProgramOverview byte 5: what the pump does outside every
    #: scheduled window. 0x01 is Stop, 0x02 is Auto - note this is the
    #: opposite of the interval action byte, where 0x02 means run.
    DEFAULT_ACTION_STOP = 0x01

    def __init__(self, session: Session, transport: Transport):
        """
        Initialize the schedule service.

        Args:
            session: Session manager for authentication state
            transport: BLE transport layer for communication
        """
        super().__init__(transport, session)
        self._schedule_sub_id: int | None = None
        self._last_read_failed: list[int] = []

    @property
    def last_read_incomplete(self) -> bool:
        """
        Whether the last :meth:`read_entries` missed a layer.

        An unread layer is not an empty one, and the difference matters to
        anything that writes the result back.
        """
        return bool(self._last_read_failed)

    async def get_state(self) -> bool | None:
        """
        Get the current schedule state (enabled/disabled).

        Reads Object 84 SubID 1 (ClockProgramOverview) to determine if
        the internal schedule is currently active.

        Returns:
            True if enabled, False if disabled, None if failed to read

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> enabled = await service.get_state()
            >>> if enabled:
            ...     print("Schedule is active")
            ... else:
            ...     print("Schedule is disabled")

        Implementation Notes:
            Protocol: Class 10, Object 84, SubID 1 (ClockProgramOverview)
            - Response format: `[Header(3)][Capabilities(4)][Enabled(1)][DefaultAction(1)][BaseSetpoint(4)]`
            - Byte 7 is the enabled flag (0x01=enabled, 0x00=disabled)
            - No scanning required - SubID 1 is a fixed location
        """
        self.session.ensure_authenticated()

        # Read Object 84, SubID 1 (ClockProgramOverview)
        # This is a fixed location - no scanning needed
        payload = await self._read_class10_object(84, 1)

        if payload is None or len(payload) < 8:
            logger.warning("Schedule overview data invalid or too short")
            return None

        # Byte 7 is the enabled flag
        enabled = payload[7] != 0
        logger.debug(f"Schedule enabled: {enabled}")
        return enabled

    async def enable(self) -> bool:
        """
        Enable the internal schedule.

        Activates the pump's built-in schedule functionality. When enabled,
        the pump will automatically start/stop according to the programmed
        schedule entries.

        Returns:
            True if successfully enabled, False otherwise

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> success = await service.enable()
            >>> if success:
            ...     print("Schedule enabled")

        Implementation Notes:
            Protocol: Class 10, OpSpec 0x90, Object 1016
            - APDU: `[0x0A][0x90][SubH][SubL][0x03][0xF8][0x01]`
            - 0x0A = Class 10
            - 0x90 = OpSpec for SET operation
            - SubH, SubL = Discovered SubID (big-endian)
            - 0x03F8 = Object 1016 (big-endian)
            - 0x01 = Enable value
        """
        return await self._set_state(True)

    async def disable(self) -> bool:
        """
        Disable the internal schedule.

        Deactivates the pump's built-in schedule functionality. The pump
        will continue operating according to its current mode, but will
        not automatically start/stop based on the schedule.

        Returns:
            True if successfully disabled, False otherwise

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> success = await service.disable()
            >>> if success:
            ...     print("Schedule disabled")

        Implementation Notes:
            Same as enable() but with value 0x00 instead of 0x01.
        """
        return await self._set_state(False)

    async def read_entries(
        self, layer: int | None = None
    ) -> list[ScheduleEntry]:
        """
        Read schedule entries from the pump.

        Retrieves the current weekly schedule from one or all layers.
        Each layer can contain up to 7 entries (one per day of the week).

        Args:
            layer: Optional specific layer (0-4) to read. If None, reads all layers.

        Returns:
            List of ScheduleEntry objects. Only enabled entries are returned.

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> # Read all layers
            >>> all_entries = await service.read_entries()
            >>>
            >>> # Read specific layer
            >>> layer0 = await service.read_entries(layer=0)
            >>>
            >>> # Display entries
            >>> for entry in all_entries:
            ...     print(f"Layer {entry.layer}, {entry.day}: "
            ...           f"{entry.begin_time}-{entry.end_time}")

        Implementation Notes:
            Protocol: Class 10, Object 84
            - SubID: 1000 + layer (1000-1004 for layers 0-4)
            - Response format: [Header 3 bytes] + [7 days × 6 bytes]
            - Total: 45 bytes

            Each 6-byte entry format:
            - Byte 0: Enabled flag (0x01=enabled, 0x00=disabled)
            - Byte 1: Action code (0x02=run pump)
            - Byte 2: Start hour (0-23)
            - Byte 3: Start minute (0-59)
            - Byte 4: End hour (0-23)
            - Byte 5: End minute (0-59)

            Days are in order: Mon, Tue, Wed, Thu, Fri, Sat, Sun
        """
        self.session.ensure_authenticated()

        entries: list[ScheduleEntry] = []

        # Determine which layers to read
        layers_to_read = range(5) if layer is None else [layer]

        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        failed: list[int] = []
        for layer_idx in layers_to_read:
            try:
                sub_id = 1000 + layer_idx

                # Read Object 84 for this layer
                data = await self._read_class10_object(84, sub_id)

                if data is None or len(data) < 45:
                    logger.warning(
                        f"Schedule data too short for layer {layer_idx}: "
                        f"{len(data) if data else 0} bytes"
                    )
                    failed.append(layer_idx)
                    continue

                # Skip 3-byte header
                payload = data[3:]

                # Parse 7 days × 6 bytes
                for day_idx, day_name in enumerate(days):
                    offset = day_idx * 6
                    entry_bytes = payload[offset : offset + 6]

                    # Only include enabled entries
                    if entry_bytes[0] != 0:
                        entry = ScheduleEntry.from_bytes(
                            entry_bytes, day_name, layer=layer_idx
                        )
                        entries.append(entry)

            except READ_ERRORS as e:
                logger.error(f"Error reading schedule layer {layer_idx}: {e}")
                failed.append(layer_idx)

        # A layer that could not be read is not an empty layer. Reporting
        # the difference matters because callers write this list back:
        # clear_entry reads, drops one day, and writes the rest, so a
        # silently-skipped layer would be written back as all-empty and
        # take the whole layer with it.
        self._last_read_failed = failed
        if failed:
            logger.warning(
                f"Could not read schedule layer(s) {failed}; the result is "
                f"incomplete and must not be written back"
            )

        return entries

    async def write_entries(
        self, entries: list[ScheduleEntry] | list[dict], layer: int = 0
    ) -> bool:
        """
        Write schedule entries to the pump.

        Writes a complete weekly schedule to the specified layer. Each layer
        can contain up to 7 entries (one per day). Entries are validated before
        writing to ensure no overlaps or invalid time ranges.

        Args:
            entries: List of ScheduleEntry objects or dicts with schedule data
            layer: Schedule layer to write to (0-4)

        Returns:
            True if successfully written, False otherwise

        Raises:
            ConnectionError: If not connected or not authenticated
            ValueError: If layer is invalid (not 0-4)

        Example:
            >>> entries = [
            ...     ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0,
            ...                   end_hour=8, end_minute=0, layer=0),
            ...     ScheduleEntry(day="Tuesday", begin_hour=6, begin_minute=0,
            ...                   end_hour=8, end_minute=0, layer=0),
            ... ]
            >>> success = await service.write_entries(entries, layer=0)
            >>> if success:
            ...     print("Schedule written successfully")

        Implementation Notes:
            Protocol: Class 10, Object 84, OpSpec 0xB3
            - SubID: 1000 + layer
            - Payload: 42 bytes (7 days × 6 bytes)
            - APDU format:
              ```
              [0x0A]              # Class 10
              [0xB3]              # OpSpec 5
              [84]                # Object ID
              [SubH][SubL]        # SubID (big-endian)
              [0x00]              # Reserved
              [0xDE][0x01][0x00]  # Type 222 header
              [0x00][0x2A]        # Size (42 bytes)
              [42 bytes data]     # Schedule entries
              ```
        """
        self.session.ensure_authenticated()

        # Validate layer
        if not 0 <= layer <= 4:
            raise ValueError(f"Invalid layer: {layer}. Must be 0-4.")

        # Convert dicts to ScheduleEntry objects if needed
        schedule_entries: list[ScheduleEntry] = []
        for e in entries:
            if isinstance(e, dict):
                schedule_entries.append(ScheduleEntry.from_dict(e))
            elif isinstance(e, ScheduleEntry):
                schedule_entries.append(e)
            else:
                logger.warning(f"Invalid schedule entry type: {type(e)}")

        # Validate entries
        is_valid, errors = self.validate_entries(schedule_entries)
        if not is_valid:
            for err in errors:
                logger.error(f"Schedule validation error: {err}")
            return False

        logger.info(
            f"Writing {len(schedule_entries)} schedule entries to layer {layer}..."
        )

        # Prepare 42-byte payload (7 days × 6 bytes)
        payload_data = bytearray(42)

        days_map = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        filled_days = set()

        for entry in schedule_entries:
            try:
                day_idx = days_map.index(entry.day)

                if day_idx in filled_days:
                    logger.warning(
                        f"Multiple entries for {entry.day} on layer {layer}. "
                        f"Only the last one will be saved."
                    )

                offset = day_idx * 6

                # Fill 6-byte entry
                payload_data[offset + 0] = 0x01 if entry.enabled else 0x00
                payload_data[offset + 1] = entry.action
                payload_data[offset + 2] = entry.begin_hour
                payload_data[offset + 3] = entry.begin_minute
                payload_data[offset + 4] = entry.end_hour
                payload_data[offset + 5] = entry.end_minute

                filled_days.add(day_idx)

            except ValueError:
                logger.warning(f"Invalid day name in entry: {entry.day}")

        # Build APDU
        sub_id = 1000 + layer
        sub_h = (sub_id >> 8) & 0xFF
        sub_l = sub_id & 0xFF

        # APDU format: [Class][OpSpec][ObjID][SubH][SubL][Reserved][Type(3)][Size(2)]
        # OpSpec 0xB3: SET with length 19 (decimal)
        # Note: 84 is 0x54 in hex
        apdu = bytearray(
            [
                0x0A,  # Class 10
                0xB3,  # OpSpec (SET with long payload)
                0x54,  # Object ID 84
                sub_h,
                sub_l,  # SubID
                0x00,  # Reserved
                0xDE,
                0x01,
                0x00,  # Type 222 header
                0x00,
                0x2A,  # Size (42 bytes)
            ]
        )
        apdu.extend(payload_data)

        # Send write command
        success = await self._write_class10_command(0xE7, 0xF8, bytes(apdu))

        if success:
            logger.info(f"Schedule written successfully to layer {layer}")
            # Need to commit configuration for schedule to persist
            await self._send_configuration_commit()
        else:
            logger.error(f"Failed to write schedule to layer {layer}")

        return success

    async def clear_entry(self, day: str, layer: int = 0) -> bool:
        """
        Clear (disable) a schedule entry for a specific day.

        This disables the schedule for a specific day on the specified layer,
        but does not affect other days or layers.

        Args:
            day: Day name (Monday-Sunday)
            layer: Schedule layer (0-4)

        Returns:
            True if successfully cleared, False otherwise

        Raises:
            ConnectionError: If not connected or not authenticated
            ValueError: If day name or layer is invalid

        Example:
            >>> # Clear Monday's schedule on layer 0
            >>> success = await service.clear_entry("Monday", layer=0)
            >>> if success:
            ...     print("Monday schedule cleared")

        Implementation Notes:
            This reads the current schedule for the layer, sets the specified
            day's entry to disabled, and writes it back.
        """
        self.session.ensure_authenticated()

        # Validate day
        days_map = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        if day not in days_map:
            raise ValueError(f"Invalid day name: {day}")

        # Validate layer
        if not 0 <= layer <= 4:
            raise ValueError(f"Invalid layer: {layer}. Must be 0-4.")

        logger.info(f"Clearing schedule entry for {day} on layer {layer}...")

        # Read the layer first: this is a read-modify-write, and the write
        # replaces every day in the layer, not just the one being cleared.
        entries = await self.read_entries(layer=layer)
        if self.last_read_incomplete:
            logger.error(
                f"Refusing to clear {day}: layer {layer} could not be read, "
                f"and writing back what was read would clear the whole layer"
            )
            return False

        # Filter out the entry for the specified day
        filtered_entries = [e for e in entries if e.day != day]

        # Write back the filtered entries
        return await self.write_entries(filtered_entries, layer=layer)

    def validate_entries(
        self,
        entries: list[ScheduleEntry] | list[dict],
    ) -> tuple[bool, list[str]]:
        """
        Validate a list of schedule entries for conflicts and errors.

        Performs comprehensive validation including:
        - Time range validity (not zero duration)
        - No overlaps within same day/layer
        - Valid day names
        - Valid layer values (0-4)

        Args:
            entries: List of ScheduleEntry instances or dicts

        Returns:
            Tuple of (is_valid, list_of_error_messages)
            - (True, []) if all entries are valid
            - (False, ["error1", "error2", ...]) if validation fails

        Example:
            >>> entries = [
            ...     ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0,
            ...                   end_hour=8, end_minute=0),
            ...     ScheduleEntry(day="Monday", begin_hour=7, begin_minute=0,
            ...                   end_hour=9, end_minute=0),  # Overlaps!
            ... ]
            >>> is_valid, errors = service.validate_entries(entries)
            >>> print(is_valid)  # False
            >>> print(errors)
            ['Overlap detected: Monday layer 0: 06:00-08:00 overlaps with 07:00-09:00']

        Implementation Notes:
            Validation logic:
            1. Convert all entries to ScheduleEntry objects
            2. Validate each entry's time range (not zero duration)
            3. Check for overlaps between enabled entries on same day/layer
            4. Warn if too many entries per day/layer combination
        """
        errors: list[str] = []

        # Convert dicts to ScheduleEntry if needed
        schedule_entries: list[ScheduleEntry] = []
        for i, entry in enumerate(entries):
            try:
                if isinstance(entry, dict):
                    schedule_entries.append(ScheduleEntry.from_dict(entry))
                elif isinstance(entry, ScheduleEntry):
                    schedule_entries.append(entry)
                else:
                    errors.append(
                        f"Entry {i}: Invalid type {type(entry).__name__}, "
                        f"expected ScheduleEntry or dict"
                    )
            except READ_ERRORS as e:
                errors.append(f"Entry {i}: Failed to parse: {e}")

        # If we couldn't parse entries, return early
        if errors:
            return (False, errors)

        # Validate each entry's time range
        for i, entry in enumerate(schedule_entries):
            is_valid, error_msg = entry.is_valid_time_range()
            if not is_valid:
                errors.append(
                    f"Entry {i} ({entry.day} {entry.begin_time}-{entry.end_time}): "
                    f"{error_msg}"
                )

        # Check for overlaps - only compare enabled entries
        enabled_entries = [e for e in schedule_entries if e.enabled]

        for i, entry1 in enumerate(enabled_entries):
            for j, entry2 in enumerate(enabled_entries[i + 1 :], start=i + 1):
                if entry1.overlaps_with(entry2):
                    errors.append(
                        f"Overlap detected: {entry1.day} layer {entry1.layer}: "
                        f"{entry1.begin_time}-{entry1.end_time} overlaps with "
                        f"{entry2.begin_time}-{entry2.end_time}"
                    )

        # Check layer counts (warn if too many entries per day/layer)
        day_layer_counts: dict[tuple[str, int], int] = defaultdict(int)

        for entry in enabled_entries:
            key = (entry.day, entry.layer)
            day_layer_counts[key] += 1

        for (day, layer), count in day_layer_counts.items():
            if count > 10:  # Arbitrary high limit
                errors.append(
                    f"Warning: {day} layer {layer} has {count} entries. "
                    f"This may exceed pump capacity."
                )

        return (len(errors) == 0, errors)

    # -------------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------------

    async def _set_state(self, enable: bool) -> bool:
        """
        Internal helper to enable/disable schedule.

        Writes to Object 84, SubID 1 (ClockProgramOverview) using the format
        discovered through protocol analysis.
        """
        self.session.ensure_authenticated()

        try:
            # Read current overview to get current values (need to preserve other fields)
            data = await self._read_class10_object(84, 1)
            if not data or len(data) < 13:
                logger.error("Failed to read current schedule overview")
                return False

            logger.debug(f"Current overview data: {data.hex()}")

            # Extract the complete 10-byte structure (from offset 3, skipping 3-byte header)
            # Byte 0: max_nof_actions
            # Byte 1: max_nof_single_events
            # Byte 2: max_nof_alternative_events_per_day
            # Byte 3: max_nof_events_per_day
            # Byte 4: clock_program_enabled (THIS IS WHAT WE MODIFY)
            # Byte 5: default_action (SchedulingActionType)
            # Bytes 6-9: base_set_point (float32)
            structure_bytes = data[3:13]  # Get complete 10-byte structure

            # Modify enable flag (byte 4 of structure)
            new_structure = bytearray(structure_bytes)
            new_structure[4] = 0x01 if enable else 0x00

            # Byte 5 is default_action, the action outside every window.
            # The Grundfos app always writes Stop here, and preserving
            # whatever the pump held instead is what produced the
            # long-standing "pump will be idle" reading: with Auto (0x02)
            # the app labels the whole schedule idle even though the
            # windows themselves are correct.
            new_structure[5] = self.DEFAULT_ACTION_STOP

            logger.debug(f"New structure bytes: {new_structure.hex()}")

            # Build APDU using standard protocol format
            # OpSpec 0x93 = OpSpec 4 (SET), Length 19
            apdu = bytearray(
                [
                    0x0A,  # Class 10
                    0x93,  # OpSpec 4, Length 19
                    0x54,  # Object 84 (decimal)
                    0x00,  # SubID high byte
                    0x01,  # SubID low byte (SubID = 1)
                    0x00,  # Reserved byte
                    0xDA,
                    0x01,
                    0x00,  # Type 218 (ClockProgramOverview)
                    0x00,
                    0x0A,  # Size = 10 bytes
                ]
            )
            apdu.extend(new_structure)

            success = await self._write_class10_command(0xE7, 0xF8, bytes(apdu))

            if success:
                logger.info(
                    f"Schedule {'enabled' if enable else 'disabled'} successfully"
                )

                # Verify the write worked
                # Note: The pump needs time to process the write command
                # and update its internal state before we can verify.
                if not getattr(self.session, "fast_mode", False):
                    await asyncio.sleep(
                        0.5
                    )  # Give pump time to process and update state

                verify_data = await self._read_class10_object(84, 1)
                if verify_data and len(verify_data) > 7:
                    actual_enabled = verify_data[7] != 0
                    if actual_enabled == enable:
                        logger.info(
                            f"Verified: Schedule is now {'enabled' if enable else 'disabled'}"
                        )
                        return True
                    else:
                        logger.warning(
                            f"Write succeeded but verification failed: expected {enable}, got {actual_enabled}"
                        )
                        return False
                return True
            else:
                logger.error(
                    f"Failed to {'enable' if enable else 'disable'} schedule"
                )
                return False

        except READ_ERRORS:
            logger.exception("Error setting schedule enabled")
            return False

    async def _scan_for_object(
        self, obj_id: int, start_sub: int, end_sub: int
    ) -> int | None:
        """
        Scan for a Class 10 object by trying SubIDs in a range.

        Args:
            obj_id: Object ID to search for
            start_sub: Starting SubID
            end_sub: Ending SubID (inclusive)

        Returns:
            The SubID if found, None otherwise
        """
        logger.info(
            f"Scanning for Class 10 Object {obj_id} (Sub {start_sub}-{end_sub})..."
        )

        for sub_id in range(start_sub, end_sub + 1):
            try:
                # Class 10 GET with both identifiers as 16-bit fields:
                # [0A][03][SubH][SubL][ObjH][ObjL]. This is a different
                # addressing form from the single-byte-object read used
                # elsewhere; the scan probes for an object whose Sub-ID is
                # unknown, so it wants the echo to identify the hit.
                apdu = bytes(
                    [
                        0x0A,
                        0x03,
                        (sub_id >> 8) & 0xFF,
                        sub_id & 0xFF,
                        (obj_id >> 8) & 0xFF,
                        obj_id & 0xFF,
                    ]
                )
                frame = self._build_geni_packet(0xF8, 0xE7, apdu)

                # A probe counts as a hit when the pump echoes back the
                # pair that was asked for. Note the matcher tolerates the
                # pump's Sub-ID-0 and swapped-field quirks, so confirm a
                # hit by reading the object before trusting it.
                probe = Command(
                    expect_a=sub_id,
                    expect_b=obj_id,
                    quiet_timeout=True,
                    description=f"probe of Object {obj_id} Sub {sub_id}",
                )

                logger.debug(f"Probing SubID {sub_id}...")
                resp = await self.transport.send_command(
                    frame, probe, timeout=0.2
                )

                if resp:
                    logger.info(f"FOUND Object {obj_id} at SubID {sub_id}!")
                    return sub_id

                await asyncio.sleep(0.02)

            except READ_ERRORS as e:
                logger.debug(f"Error probing SubID {sub_id}: {e}")
                continue

        logger.warning(
            f"Object {obj_id} not found in range {start_sub}-{end_sub}."
        )
        return None

    async def _write_class10_command(
        self, dst: int, src: int, apdu: bytes
    ) -> bool:
        """
        Write a Class 10 command using query (to match original behavior).

        Args:
            dst: Destination address (typically 0xE7)
            src: Source address (typically 0xF8)
            apdu: Complete APDU bytes (Class + OpSpec + data)

        Returns:
            True if write was sent and got any response (or timeout), False on exception

        Note:
            Matches the original implementation which uses _query and treats
            both responses and timeouts (empty bytes) as success.
        """
        try:
            frame = self._build_geni_packet(src, dst, bytes(apdu))

            logger.debug(f"Writing Class 10 command: {frame.hex()}")

            # A timeout here is the expected case, not a fault: the pump
            # uses a two-phase commit for flash-backed writes and its
            # acknowledgement usually lands after the response window has
            # closed. That is why the return value cannot mean "the pump
            # took it" - only a readback can establish that.
            response = await self.transport.send_command(
                frame,
                Command(
                    expect_short_ack=True,
                    quiet_timeout=True,
                    description="Class 10 write",
                ),
                timeout=3.0,
            )

            if response is not None:
                logger.debug(
                    f"Got response to Class 10 write: {response.hex()}"
                )

            return True

        except READ_ERRORS as e:
            logger.error(f"Error writing Class 10 command: {e}")
            return False
