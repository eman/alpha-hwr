"""
Historical data service for Grundfos ALPHA HWR pumps.

This service provides access to historical trend data including flow, head,
and temperature measurements over the last 10 and 100 pump cycles.

Protocol Details
----------------
Trend data is stored in GENI DataObjects:

1. **Timestamp Maps**:
   - Object 88, SubID 13300: Last 10 cycles timestamps
   - Object 88, SubID 13301: Last 100 cycles timestamps
   - Format: Array of 10 uint32 timestamps (big-endian)

2. **Trend Data Values** (Object 53):
   - SubID 451: Flow history (m³/h, scale 0.1)
   - SubID 452: Head history (m, scale 0.1)
   - SubID 453: Media temperature history (°C, scale 1.0)
   - SubID 454: Power-on time history (hours, scale 1.0)

3. **Data Structure** (Type 946 - TrendData1B):
   - Current value (float, 4 bytes)
   - Last 10 cycle values (10 bytes, 1 byte each)
   - Next counter (1 byte)
   - Next 100-cycle value (float, 4 bytes)
   - Last 10 of 100-cycle values (10 bytes, 1 byte each)
   - Total: 29 bytes

Example (TypeScript):
```typescript
async getTrendData(): Promise<TrendDataCollection> {
    const ts10 = await this.readObject(88, 13300);
    const ts100 = await this.readObject(88, 13301);
    const flow = await this.readObject(53, 451);

    // Parse timestamps
    const timestamps10 = this.parseTimestamps(ts10);
    const timestamps100 = this.parseTimestamps(ts100);

    // Build series
    const flowSeries = this.buildSeries(
        "Flow", "m³/h", flow, timestamps10, timestamps100, 0.1
    );

    return { flowSeries, headSeries, mediaTemperatureSeries };
}
```
"""

from __future__ import annotations

import logging
import struct
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..exceptions import READ_ERRORS, ConnectionError
from ..pump_time import from_pump_time
from .base import BaseService

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport

from alpha_hwr.models import (
    TrendDataCollection,
    TrendDataPoint,
    TrendDataSeries,
)

logger = logging.getLogger(__name__)


class HistoryService(BaseService):
    """
    Service for accessing historical trend data from the pump.

    This service provides methods to retrieve and parse historical measurements
    including flow, head, and temperature data over the last 10 and 100 cycles.

    Example:
        >>> from alpha_hwr.services import HistoryService
        >>>
        >>> # Initialize
        >>> history = HistoryService(transport, session)  # doctest: +SKIP
        >>>
        >>> # Get all trend data
        >>> trends = await history.get_trend_data()  # doctest: +SKIP
        >>> if trends.flow_series:  # doctest: +SKIP
        ...     print(f"Current flow: {trends.flow_series.cycle_10_points[0].value} m³/h")
        >>>
        >>> # Get cycle timestamps
        >>> timestamps = await history.get_cycle_timestamps(count=10)  # doctest: +SKIP
        >>> print(f"Last cycle: {timestamps[0]}")  # doctest: +SKIP
    """

    def __init__(self, transport: Transport, session: Session) -> None:
        """
        Initialize history service.

        Args:
            transport: Transport layer for BLE communication
            session: Session manager for state tracking
        """
        super().__init__(transport, session)

    async def get_trend_data(self) -> TrendDataCollection | None:
        """
        Retrieve all historical trend data from the pump.

        Fetches:
        - 10-cycle timestamp map (Obj 88, Sub 13300)
        - 100-cycle timestamp map (Obj 88, Sub 13301)
        - Flow history (Obj 53, Sub 451)
        - Head history (Obj 53, Sub 452)
        - Media temperature history (Obj 53, Sub 453)

        Returns:
            TrendDataCollection with all series, or None if retrieval failed.

        Example:
            >>> trends = await history.get_trend_data()  # doctest: +SKIP
            >>> if trends and trends.flow_series:  # doctest: +SKIP
            ...     for point in trends.flow_series.cycle_10_points:
            ...         print(f"{point.timestamp}: {point.value} m³/h")
        """
        if not self.session.is_connected():
            raise ConnectionError("Not connected to pump")

        try:
            logger.info("Fetching trend data...")

            # 1. Fetch timestamp maps
            ts_data_10 = await self._read_timestamp_map(13300)
            ts_data_100 = await self._read_timestamp_map(13301)

            if not ts_data_10 or not ts_data_100:
                logger.warning("Failed to fetch trend timestamps")
                return None

            timestamps_10 = ts_data_10.get("timestamps", [])
            timestamps_100 = ts_data_100.get("timestamps", [])

            logger.debug(
                f"Retrieved {len(timestamps_10)} 10-cycle timestamps, "
                f"{len(timestamps_100)} 100-cycle timestamps"
            )

            # 2. Fetch trend values
            flow_data = await self._read_trend_values(53, 451)
            head_data = await self._read_trend_values(53, 452)
            temp_data = await self._read_trend_values(53, 453)
            power_time_data = await self._read_trend_values(53, 454)

            # 3. Build series
            flow_series = (
                self._build_series(
                    "Flow",
                    "m³/h",
                    flow_data,
                    timestamps_10,
                    timestamps_100,
                    scale=0.1,
                )
                if flow_data
                else None
            )

            head_series = (
                self._build_series(
                    "Head",
                    "m",
                    head_data,
                    timestamps_10,
                    timestamps_100,
                    scale=0.1,
                )
                if head_data
                else None
            )

            temp_series = (
                self._build_series(
                    "Media Temperature",
                    "°C",
                    temp_data,
                    timestamps_10,
                    timestamps_100,
                    scale=1.0,
                )
                if temp_data
                else None
            )

            power_time_series = (
                self._build_series(
                    "Power-On Time",
                    "hours",
                    power_time_data,
                    timestamps_10,
                    timestamps_100,
                    scale=1.0,
                )
                if power_time_data
                else None
            )

            logger.info(
                f"Trend data retrieved: flow={flow_series is not None}, "
                f"head={head_series is not None}, temp={temp_series is not None}, "
                f"power_time={power_time_series is not None}"
            )

            return TrendDataCollection(
                flow_series=flow_series,
                head_series=head_series,
                media_temperature_series=temp_series,
                power_on_time_series=power_time_series,
            )

        except ConnectionError:
            # A half-built collection is not a result. Three of the four
            # series are legitimately None on a pump that does not keep
            # them, so a caller cannot tell a dropped link from a sparse
            # trend once the object is handed back.
            raise

        except READ_ERRORS as e:
            logger.error(f"Error fetching trend data: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return None

    async def get_cycle_timestamps(
        self, count: int = 10
    ) -> list[datetime] | None:
        """
        Get timestamps of recent pump cycles.

        Args:
            count: Number of timestamps to retrieve (10 or 100)

        Returns:
            List of datetime objects for each cycle, or None if read failed.
            Most recent cycle is first in list.

        Example:
            >>> timestamps = await history.get_cycle_timestamps(count=10)  # doctest: +SKIP
            >>> if timestamps:  # doctest: +SKIP
            ...     print(f"Last cycle: {timestamps[0]}")
            ...     print(f"Cycle 10 ago: {timestamps[-1]}")
        """
        if not self.session.is_connected():
            raise ConnectionError("Not connected to pump")

        try:
            subid = 13300 if count == 10 else 13301
            data = await self._read_timestamp_map(subid)

            if not data:
                return None

            timestamps = data.get("timestamps", [])

            # Convert to datetime objects
            result = []
            for ts in timestamps:
                # Timestamps are Unix timestamps (seconds since epoch)
                # If timestamp is small (< year 2000), add offset
                if ts < 946684800:  # Jan 1, 2000
                    ts += 946684800

                result.append(from_pump_time(ts))

            return result

        except ConnectionError:
            raise

        except READ_ERRORS as e:
            logger.error(f"Error fetching cycle timestamps: {e}")
            return None

    # Helper methods

    async def _read_timestamp_map(self, subid: int) -> dict[str, Any] | None:
        """
        Read timestamp map from Object 88.

        Args:
            subid: 13300 for 10-cycle, 13301 for 100-cycle

        Returns:
            Dict with 'timestamps' list and 'cycle_type', or None
        """
        try:
            data = await self._read_class10_object(88, subid)

            if not data or len(data) < 7:
                logger.warning(f"Invalid timestamp map data for SubID {subid}")
                return None

            # Skip 3-byte header if present [00 00 XX]
            payload = (
                data[3:] if len(data) > 3 and data[:2] == b"\x00\x00" else data
            )

            # Parse array of uint32 timestamps (big-endian)
            count = len(payload) // 4
            timestamps = []

            for i in range(count):
                offset = i * 4
                if offset + 4 <= len(payload):
                    ts = struct.unpack(">I", payload[offset : offset + 4])[0]
                    timestamps.append(ts)

            logger.debug(
                f"Parsed {len(timestamps)} timestamps from SubID {subid}"
            )

            return {
                "timestamps": timestamps,
                "cycle_type": 10 if subid == 13300 else 100,
            }

        except ConnectionError:
            # Not "this map is unreadable" - every read after it will fail
            # the same way, and a trend series missing because the link
            # went looks exactly like one the pump does not keep.
            raise

        except READ_ERRORS as e:
            logger.error(f"Error reading timestamp map {subid}: {e}")
            return None

    async def _read_trend_values(
        self, obj_id: int, subid: int
    ) -> dict[str, Any] | None:
        """
        Read trend data values from Object 53.

        Args:
            obj_id: Object ID (usually 53)
            subid: SubID (451=flow, 452=head, 453=temp, 454=power-on)

        Returns:
            Dict with parsed trend data, or None
        """
        try:
            data = await self._read_class10_object(obj_id, subid)

            if not data:
                logger.warning(f"No data for Object {obj_id}, SubID {subid}")
                return None

            # Skip 3-byte header if present
            payload = (
                data[3:] if len(data) > 3 and data[:2] == b"\x00\x00" else data
            )

            # Parse Type 946 (TrendData1B): 29 bytes
            if len(payload) >= 29:
                current_val = struct.unpack(">f", payload[0:4])[0]
                cycle10_raw = list(payload[4:14])
                next_ctr = payload[14]
                next_val_100 = struct.unpack(">f", payload[15:19])[0]
                cycle100_raw = list(payload[19:29])

                logger.debug(
                    f"Parsed trend data: current={current_val:.2f}, "
                    f"10-cycle={len(cycle10_raw)} points, 100-cycle={len(cycle100_raw)} points"
                )

                return {
                    "current_value": current_val,
                    "cycle10_raw": cycle10_raw,
                    "next_ctr": next_ctr,
                    "next_value_100": next_val_100,
                    "cycle100_raw": cycle100_raw,
                    "type": "TrendData1B",
                }
            else:
                logger.warning(
                    f"Unexpected payload size for trend data: {len(payload)} bytes"
                )
                return None

        except ConnectionError:
            # See _read_timestamp_map: a dropped link is not "this trend
            # is empty".
            raise

        except READ_ERRORS as e:
            logger.error(
                f"Error reading trend values Obj{obj_id}/Sub{subid}: {e}"
            )
            return None

    def _build_series(
        self,
        name: str,
        unit: str,
        raw_data: dict[str, Any],
        timestamps_10: list[int],
        timestamps_100: list[int],
        scale: float = 1.0,
    ) -> TrendDataSeries | None:
        """
        Build a TrendDataSeries from raw data and timestamps.

        Args:
            name: Series name (e.g., "Flow")
            unit: Unit of measurement (e.g., "m³/h")
            raw_data: Raw trend data dict
            timestamps_10: List of 10-cycle timestamps
            timestamps_100: List of 100-cycle timestamps
            scale: Scale factor to apply to values

        Returns:
            TrendDataSeries object, or None if invalid data
        """
        if not raw_data:
            return None

        try:
            # Build 10-cycle points
            cycle10_vals = raw_data.get("cycle10_raw", [])
            points_10 = []

            for i, val in enumerate(cycle10_vals):
                if i < len(timestamps_10):
                    val_scaled = val * scale
                    ts = timestamps_10[i]

                    # Convert timestamp (adjust if < year 2000)
                    if ts < 946684800:
                        ts += 946684800

                    points_10.append(
                        TrendDataPoint(
                            timestamp=from_pump_time(ts),
                            value=val_scaled,
                        )
                    )

            # Build 100-cycle points
            cycle100_vals = raw_data.get("cycle100_raw", [])
            points_100 = []

            for i, val in enumerate(cycle100_vals):
                if i < len(timestamps_100):
                    val_scaled = val * scale
                    ts = timestamps_100[i]

                    if ts < 946684800:
                        ts += 946684800

                    points_100.append(
                        TrendDataPoint(
                            timestamp=from_pump_time(ts),
                            value=val_scaled,
                        )
                    )

            return TrendDataSeries(
                name=name,
                unit=unit,
                cycle_10_points=points_10,
                cycle_100_points=points_100,
            )

        except READ_ERRORS as e:
            logger.error(f"Error building series '{name}': {e}")
            return None
