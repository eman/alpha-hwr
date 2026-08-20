"""
Time management service for Grundfos ALPHA HWR pumps.

This service handles reading and synchronizing the pump's real-time clock (RTC).
The RTC is used for schedule execution and event logging.

Protocol Details
----------------
The pump's RTC is managed via GENI DataObjects:

1. **Read Time** - Object 94, SubID 101 (DateTimeActual):
   - Returns: `[Status(2)][Length(1)][Year(2BE)][Month][Day][Hour][Minute][Second]`
   - Status 0x0000 = valid, 0xFFFF = unset
   - Year is big-endian uint16

2. **Set Time** - Class 10 SET on SubID 0x5E00 (Object 94), ObjID 0x6401 (SubID 100):
   - Uses standard Class 10 SET frame via ``build_data_object_set``
   - Data payload (16 bytes): ``[Type322Header(6)][Year(2BE)][Month][Day][Hour][Min][Sec][Pad(3)]``
   - Type322Header is constant: ``41 02 00 00 0B 01``
   - Pump responds with Class 10 ACK (OpSpec 0x01)
   - Note: Class 16 ID 0 (set_unix_rtc) does NOT work despite being documented

Example (TypeScript):
```typescript
async setClock(date: Date): Promise<boolean> {
    // Type 322 data: [header(6)][year(2)][month][day][hour][min][sec][pad(3)]
    const data = new Uint8Array(16);
    // Type 322 header (constant)
    data.set([0x41, 0x02, 0x00, 0x00, 0x0B, 0x01]);
    data[6] = (date.getFullYear() >> 8) & 0xFF;
    data[7] = date.getFullYear() & 0xFF;
    data[8] = date.getMonth() + 1;
    data[9] = date.getDate();
    data[10] = date.getHours();
    data[11] = date.getMinutes();
    data[12] = date.getSeconds();
    // bytes 13-15: padding (zeros)

    // Standard Class 10 SET frame
    const frame = buildDataObjectSet(0x5E00, 0x6401, data);
    const response = await this.transport.query(frame);
    return response?.[5] === 0x01; // ACK
}
```

Example (Rust):
```rust
pub async fn set_clock(&self, dt: DateTime<Local>) -> Result<bool, Error> {
    // Type 322 data: [header(6)][year(2)][month][day][hour][min][sec][pad(3)]
    let mut data = vec![0x41, 0x02, 0x00, 0x00, 0x0B, 0x01];
    data.extend_from_slice(&(dt.year() as u16).to_be_bytes());
    data.push(dt.month() as u8);
    data.push(dt.day() as u8);
    data.push(dt.hour() as u8);
    data.push(dt.minute() as u8);
    data.push(dt.second() as u8);
    data.resize(16, 0); // Pad to 16 bytes

    // Standard Class 10 SET frame
    let frame = build_data_object_set(0x5E00, 0x6401, &data)?;
    let resp = self.transport.query(&frame).await?;
    Ok(resp.map_or(false, |r| r[5] == 0x01)) // ACK
}
```
"""

from __future__ import annotations

import asyncio
import logging
import struct
from datetime import datetime
from typing import TYPE_CHECKING

from ..exceptions import READ_ERRORS
from ..protocol.matcher import Command
from .base import BaseService

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport


logger = logging.getLogger(__name__)


class TimeService(BaseService):
    """
    Service for managing pump real-time clock (RTC).

    This service provides APIs for reading and synchronizing the pump's
    internal clock. The RTC is used for schedule execution and event logging.

    Example:
        >>> from alpha_hwr.services import TimeService
        >>>
        >>> # Initialize
        >>> time_service = TimeService(transport, session)  # doctest: +SKIP
        >>>
        >>> # Read pump time
        >>> pump_time = await time_service.get_clock()  # doctest: +SKIP
        >>> print(f"Pump time: {pump_time}")  # doctest: +SKIP
        >>>
        >>> # Sync with system time
        >>> success = await time_service.set_clock()  # doctest: +SKIP
        >>> if success:  # doctest: +SKIP
        ...     print("Clock synchronized")
        >>>
        >>> # Set to specific time
        >>> from datetime import datetime
        >>> dt = datetime(2026, 12, 25, 10, 0, 0)
        >>> await time_service.set_clock(dt)  # doctest: +SKIP
    """

    def __init__(self, transport: Transport, session: Session) -> None:
        """
        Initialize time service.

        Args:
            transport: Transport layer for BLE communication
            session: Session manager for state tracking
        """
        super().__init__(transport, session)

    async def get_clock(self) -> datetime | None:
        """
        Read the pump's internal real-time clock.

        Reads from Object 94, SubID 101 (DateTimeActual, Type 322).
        Returns the current pump time as a datetime object.

        Returns:
            Current pump time as datetime, or None if read failed or clock is unset.
            If clock is unset (year < 1970), returns epoch time (1970-01-01 00:00:00).

        Raises:
            ConnectionError: If not connected

        Example:
            >>> pump_time = await time_service.get_clock()  # doctest: +SKIP
            >>> if pump_time:  # doctest: +SKIP
            ...     if pump_time.year < 1980:
            ...         print("Clock is unset, needs sync")
            ...     else:
            ...         print(f"Pump time: {pump_time.strftime('%Y-%m-%d %H:%M:%S')}")

        Implementation Notes:
            - Uses Class 10 GET on Object 94, SubID 101
            - Response format: `[Status(2)][Length(1)][Year(2)][Month(1)][Day(1)][Hour(1)][Minute(1)][Second(1)]`
            - Status 0x0000 = valid, 0xFFFF = unset
            - Year is big-endian uint16
            - Invalid dates (year < 1970, month/day = 0) indicate unset clock
        """
        if not self.session.is_connected():
            raise ConnectionError("Not connected to pump")

        try:
            # Read Class 10: Object 94, SubID 101 (DateTimeActual)
            data = await self._read_class10_object(94, 101)

            if data and len(data) >= 10:
                logger.debug(f"Raw clock data: {data.hex()} (len={len(data)})")

                # Parse Type 322 structure:
                # `[Status(2)][Length(1)][Year(2)][Month(1)][Day(1)][Hour(1)][Minute(1)][Second(1)]`
                status = (data[0] << 8) | data[1]

                # Data starts after Status (2) and Length (1)
                payload = data[3:]

                if len(payload) >= 7:
                    # Year is big-endian uint16
                    yr = struct.unpack(">H", payload[0:2])[0]
                    mo, da, hr, mi, sc = payload[2:7]

                    logger.debug(
                        f"Parsed clock: {yr}-{mo:02d}-{da:02d} {hr:02d}:{mi:02d}:{sc:02d}, status={status:#06x}"
                    )

                    # Handle unset/invalid clock
                    if yr < 1970 or yr > 2100 or mo == 0 or da == 0:
                        logger.warning(
                            f"Pump clock is unset or invalid: {yr}-{mo}-{da}"
                        )
                        # Naive by design - see the note on set_time().
                        # Local-epoch sentinel: callers detect an unset
                        # clock via `year <= 1980`.
                        return datetime.fromtimestamp(0)  # noqa: DTZ006

                    return datetime(yr, mo, da, hr, mi, sc)  # noqa: DTZ001
                else:
                    logger.warning(
                        f"Clock payload too short: {len(payload)} bytes"
                    )
            else:
                logger.warning(
                    f"Clock data missing or too short: {len(data) if data else 0} bytes"
                )

        except READ_ERRORS as e:
            logger.error(f"Failed to read pump clock: {e}")
            import traceback

            logger.debug(traceback.format_exc())

        return None

    async def set_clock(self, dt: datetime | None = None) -> bool:
        """
        Synchronize the pump's internal real-time clock.

        Sends a standard Class 10 SET to SubID 0x5E00 (Object 94),
        ObjID 0x6401 (SubID 100 = DateTimeConfig) with a Type 322
        data payload.

        Args:
            dt: Datetime to set. If None, uses current LOCAL system
                time.

        Returns:
            True if clock was successfully set, False otherwise.

        Raises:
            ConnectionError: If not connected or not authenticated.

        Example:
            >>> # Sync with system time
            >>> await time_service.set_clock()  # doctest: +SKIP
            >>>
            >>> # Set to specific time
            >>> from datetime import datetime
            >>> dt = datetime(2026, 1, 30, 11, 35, 0)
            >>> await time_service.set_clock(dt)  # doctest: +SKIP

        Implementation Notes:
            - Uses ``build_data_object_set(0x5E00, 0x6401, data)``
            - Data format (16 bytes): Type 322 header (6) +
              ``[Year(2BE)][Month][Day][Hour][Min][Sec]`` + padding (3)
            - Type 322 header is constant: ``41 02 00 00 0B 01``
            - Pump responds with Class 10 ACK (OpSpec 0x01)
        """
        self.session.ensure_authenticated()

        if dt is None:
            # Deliberately naive local time: the pump stores bare
            # wall-clock fields (year/month/day/hour/min/sec) with no
            # offset, and its schedules run against that wall clock. A
            # UTC-aware value here would shift the pump's clock by the
            # local offset.
            dt = datetime.now()  # noqa: DTZ005

        logger.info(
            f"Synchronizing pump clock to {dt.isoformat()} (local time)..."
        )

        try:
            from ..protocol import FrameBuilder

            # Type 322 data payload (16 bytes):
            # [header(6)][Year(2BE)][Month][Day][Hour][Min][Sec][pad(3)]
            _TYPE_322_HEADER = bytes([0x41, 0x02, 0x00, 0x00, 0x0B, 0x01])
            data = bytearray(_TYPE_322_HEADER)
            data.extend(struct.pack(">H", dt.year))
            data.append(dt.month)
            data.append(dt.day)
            data.append(dt.hour)
            data.append(dt.minute)
            data.append(dt.second)
            data.extend(bytes(3))  # Pad to 16 bytes

            logger.debug(
                f"DateTime payload: {data.hex()} "
                f"({dt.year:04d}-{dt.month:02d}-{dt.day:02d} "
                f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d})"
            )

            # Class 10 SET: SubID 0x5E00 (Obj 94), ObjID 0x6401 (Sub 100)
            frame = FrameBuilder.build_data_object_set(
                sub_id=0x5E00,
                obj_id=0x6401,
                data=bytes(data),
            )
            logger.debug(f"Clock SET frame: {frame.hex()} ({len(frame)} bytes)")

            # The clock write is acknowledged by a bare Class 10 ack, which
            # carries no identifiers - the operation specifier is the only
            # thing that distinguishes it from a telemetry notification.
            response = await self.transport.send_command(
                frame,
                Command(
                    expect_short_ack=True,
                    accept_opspecs=frozenset({0x01}),
                    description="clock set",
                ),
                timeout=3.0,
            )

            if not response:
                logger.warning("No ACK received for clock set")
                return False

            # Give the pump time to apply
            if not getattr(self.session, "fast_mode", False):
                await asyncio.sleep(0.5)

            # Verify by reading clock back
            new_time = await self.get_clock()
            if new_time:
                time_diff = abs((new_time - dt).total_seconds())
                if time_diff < 5 or getattr(self.session, "fast_mode", False):
                    logger.info("Clock synchronized successfully")
                    return True
                else:
                    logger.warning(
                        f"Clock sync may have failed - time diff: {time_diff}s"
                    )

            return False

        except READ_ERRORS as e:
            logger.error(f"Failed to set pump clock: {e}")
            import traceback

            logger.debug(traceback.format_exc())

        return False

    # Helper methods

    async def _send_with_retry(
        self, packet: bytes, description: str, retries: int = 3
    ) -> bool:
        """
        Send packet with retry logic and wait for ACK.

        Waits for either:
        - ACK (OpSpec 0x01)
        - Telemetry notification (OpSpec 0x0E)
        """

        # Either the write acknowledgement or a passive notification counts:
        # having heard anything at all back means the pump processed the
        # write, and it does not always answer with the ack.
        command = Command(
            expect_short_ack=True,
            accept_opspecs=frozenset({0x01, 0x0E}),
            description=description,
        )

        for attempt in range(retries):
            try:
                response = await self.transport.send_command(
                    packet,
                    command,
                    timeout=3.0,
                )

                if response:
                    logger.debug(f"{description} acknowledged")
                    return True

                logger.warning(
                    f"{description} attempt {attempt + 1} - no ACK received"
                )

            except READ_ERRORS as e:
                logger.warning(
                    f"{description} attempt {attempt + 1} failed: {e}"
                )

            if attempt < retries - 1 and not getattr(
                self.session, "fast_mode", False
            ):
                await asyncio.sleep(0.5)

        return False
