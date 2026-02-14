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

2. **Set Time** - Object 94, SubID 100 (DateTimeConfig):
   - Payload: `[Year(2BE)][Month][Day][Hour][Minute][Second]` + 13 padding bytes (19 total)
   - Frame: `[0x27][Length][0x07][0x5E][0x64][0x70][DateTime...][CRC]`
   - Note: Class 16 ID 0 (set_unix_rtc) does NOT work despite being documented

Example (TypeScript):
```typescript
async setClock(date: Date): Promise<boolean> {
    const payload = new Uint8Array(19);
    payload[0] = (date.getFullYear() >> 8) & 0xFF;
    payload[1] = date.getFullYear() & 0xFF;
    payload[2] = date.getMonth() + 1;
    payload[3] = date.getDate();
    payload[4] = date.getHours();
    payload[5] = date.getMinutes();
    payload[6] = date.getSeconds();
    // bytes 7-18: padding (zeros)

    const apdu = new Uint8Array([0x07, 0x5E, 0x64, 0x70, ...payload]);
    const frame = this.buildFrame(0x27, apdu);
    await this.transport.write(frame);
    return true;
}
```

Example (Rust):
```rust
pub async fn set_clock(&self, dt: DateTime<Local>) -> Result<bool, Error> {
    let mut payload = Vec::with_capacity(19);
    payload.extend_from_slice(&(dt.year() as u16).to_be_bytes());
    payload.push(dt.month() as u8);
    payload.push(dt.day() as u8);
    payload.push(dt.hour() as u8);
    payload.push(dt.minute() as u8);
    payload.push(dt.second() as u8);
    payload.resize(19, 0);

    let mut apdu = vec![0x07, 0x5E, 0x64, 0x70];
    apdu.extend_from_slice(&payload);

    let frame = self.build_frame(0x27, &apdu)?;
    self.transport.write(&frame).await?;
    Ok(true)
}
```
"""

from __future__ import annotations

import asyncio
import logging
import struct
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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
        >>> time_service = TimeService(transport, session)
        >>>
        >>> # Read pump time
        >>> pump_time = await time_service.get_clock()
        >>> print(f"Pump time: {pump_time}")
        >>>
        >>> # Sync with system time
        >>> success = await time_service.set_clock()
        >>> if success:
        ...     print("Clock synchronized")
        >>>
        >>> # Set to specific time
        >>> from datetime import datetime
        >>> dt = datetime(2026, 12, 25, 10, 0, 0)
        >>> await time_service.set_clock(dt)
    """

    def __init__(self, transport: Transport, session: Session) -> None:
        """
        Initialize time service.

        Args:
            transport: Transport layer for BLE communication
            session: Session manager for state tracking
        """
        super().__init__(transport, session)

    async def get_clock(self) -> Optional[datetime]:
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
            >>> pump_time = await time_service.get_clock()
            >>> if pump_time:
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
                        return datetime.fromtimestamp(0)  # Epoch

                    return datetime(yr, mo, da, hr, mi, sc)
                else:
                    logger.warning(
                        f"Clock payload too short: {len(payload)} bytes"
                    )
            else:
                logger.warning(
                    f"Clock data missing or too short: {len(data) if data else 0} bytes"
                )

        except Exception as e:
            logger.error(f"Failed to read pump clock: {e}")
            import traceback

            logger.debug(traceback.format_exc())

        return None

    async def set_clock(self, dt: Optional[datetime] = None) -> bool:
        """
        Synchronize the pump's internal real-time clock.

        Writes to Object 94, SubID 100 (DateTimeConfig) using the standard
        protocol format.

        Args:
            dt: Datetime to set. If None, uses current LOCAL system time.

        Returns:
            True if clock was successfully set, False otherwise

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> # Sync with system time
            >>> await time_service.set_clock()
            >>>
            >>> # Set to specific time
            >>> from datetime import datetime
            >>> dt = datetime(2026, 1, 30, 11, 35, 0)
            >>> await time_service.set_clock(dt)

        Implementation Notes:
            - Uses Object 94, SubID 100 (DateTimeConfig) with SET operation
            - Format: `[UnknownByte][Object][SubID][OpSpec][DateTime...]`
            - DateTime format: `[Year(2BE)][Month][Day][Hour][Minute][Second][...]`
            - This is confirmed by protocol behavior
        """
        self.session.ensure_authenticated()

        if dt is None:
            # Use LOCAL time
            dt = datetime.now()

        logger.info(
            f"Synchronizing pump clock to {dt.isoformat()} (local time)..."
        )

        try:
            # Build datetime payload in the format iOS uses
            # `[Year(2 bytes, big-endian)][Month][Day][Hour][Minute][Second][padding...]`
            datetime_bytes = bytearray()
            datetime_bytes.extend(
                struct.pack(">H", dt.year)
            )  # Year as big-endian uint16
            datetime_bytes.append(dt.month)
            datetime_bytes.append(dt.day)
            datetime_bytes.append(dt.hour)
            datetime_bytes.append(dt.minute)
            datetime_bytes.append(dt.second)

            # Add padding bytes (iOS sends 19 total bytes)
            # The meaning of these extra bytes is unclear, but we'll send zeros
            datetime_bytes.extend(bytes(13))  # Pad to 19 bytes total

            logger.debug(
                f"DateTime bytes: {datetime_bytes.hex()} "
                f"({dt.year:04d}-{dt.month:02d}-{dt.day:02d} "
                f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d})"
            )

            # Build APDU: `[UnknownByte][Object][SubID][OpSpec][Data...]`
            # From iOS captures:
            # - UnknownByte: 0x07 (purpose unknown, possibly address/routing)
            # - Object: 0x5E (94)
            # - SubID: 0x64 (100 = DateTimeConfig)
            # - OpSpec: 0x70 (SET operation + length field)
            apdu = bytearray(
                [
                    0x07,  # Unknown byte (seen in iOS packets)
                    0x5E,  # Object 94
                    0x64,  # SubID 100 (DateTimeConfig)
                    0x70,  # OpSpec: SET operation
                ]
            )
            apdu.extend(datetime_bytes)

            # Build GENI frame: [Delimiter][Length][APDU][CRC]
            length = len(apdu)
            frame_without_crc = bytes([0x27, length]) + bytes(apdu)

            # Calculate CRC
            from ..utils import calc_crc16_read

            crc = calc_crc16_read(frame_without_crc[1:])
            frame = frame_without_crc + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

            logger.debug(f"Clock SET frame: {frame.hex()} ({len(frame)} bytes)")

            # Send command
            await self.transport.write(frame)

            # Give the pump time to process
            if not getattr(self.session, "fast_mode", False):
                await asyncio.sleep(0.5)

            # Verify by reading clock back
            new_time = await self.get_clock()
            if new_time:
                time_diff = abs((new_time - dt).total_seconds())
                if time_diff < 5 or getattr(
                    self.session, "fast_mode", False
                ):  # Within 5 seconds is success
                    logger.info("Clock synchronized successfully")
                    return True
                else:
                    logger.warning(
                        f"Clock sync may have failed - time diff: {time_diff}s"
                    )

            return False

        except Exception as e:
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

        def ack_filter(data: bytes) -> bool:
            """Match ACK or telemetry notification responses."""
            if len(data) < 6:
                return False
            # data[4] is Class, data[5] is OpSpec
            # Accept: 0x01 (ACK) or 0x0E (Telemetry Notification)
            return data[5] == 0x01 or data[5] == 0x0E

        for attempt in range(retries):
            try:
                response = await self.transport.query(
                    packet,
                    match_func=ack_filter,
                    timeout=3.0,
                )

                if response:
                    logger.debug(f"{description} acknowledged")
                    return True

                logger.warning(
                    f"{description} attempt {attempt + 1} - no ACK received"
                )

            except Exception as e:
                logger.warning(
                    f"{description} attempt {attempt + 1} failed: {e}"
                )

            if attempt < retries - 1 and not getattr(
                self.session, "fast_mode", False
            ):
                await asyncio.sleep(0.5)

        return False
