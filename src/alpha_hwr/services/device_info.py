"""
Device information service.

This service handles reading device identification and metadata:
- Product family, type, and version (from BLE advertisement)
- Serial number, software version, hardware version (from Class 7 strings)
- Device statistics (alarms, runtime, energy consumption)

Device info can be retrieved from two sources:

1. **BLE Advertisement Data**:
   - Available without connection
   - Service UUID: 0000fdd0-0000-1000-8000-00805f9b34fb
   - Bytes [3,4,5] contain: product_family, product_type, product_version

2. **Class 7 String Parameters** (requires connection):
   - String ID 9: Serial number
   - String ID 50: Software version
   - String ID 52: Hardware version (backend SW)
   - String ID 58: BLE version
   - Request format: [0x07][0x01][StringID]

Example in TypeScript:
```typescript
class DeviceInfoService {
    async readBasic(): Promise<DeviceInfo> {
        // Scan BLE advertisement
        // Extract service data
        // Parse product family/type/version
    }

    async readDetailed(): Promise<DeviceInfo> {
        // Read Class 7 strings
        // Serial, SW version, HW version, BLE version
    }
}
```

Example in Rust:
```rust
pub struct DeviceInfoService {
    transport: Arc<Transport>,
}

impl DeviceInfoService {
    pub async fn read_basic(&self) -> Result<DeviceInfo, Error> {
        // Read from BLE advertisement
    }

    pub async fn read_detailed(&self) -> Result<DeviceInfo, Error> {
        // Read Class 7 strings
    }
}
```
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..constants import ERROR_CODES
from ..exceptions import READ_ERRORS
from ..models import AlarmInfo, DeviceInfo, Statistics
from .base import BaseService

if TYPE_CHECKING:
    from alpha_hwr.core.session import Session
    from alpha_hwr.core.transport import Transport


logger = logging.getLogger(__name__)


class DeviceInfoService(BaseService):
    """
    Service for reading device information and metadata.

    This service provides APIs for accessing device identification,
    version information, and operational statistics.

    Example:
        >>> from alpha_hwr.services import DeviceInfoService  # doctest: +SKIP
        >>>
        >>> # Initialize
        >>> device_info = DeviceInfoService(transport, session)  # doctest: +SKIP
        >>>
        >>> # Read basic info (no connection needed)
        >>> info = await device_info.read_basic()  # doctest: +SKIP
        >>> print(f"Product: {info.product_family}/{info.product_type}")  # doctest: +SKIP
        >>>
        >>> # Read detailed info (requires connection)
        >>> info = await device_info.read_detailed()  # doctest: +SKIP
        >>> print(f"Serial: {info.serial_number}")  # doctest: +SKIP
        >>> print(f"SW Version: {info.software_version}")  # doctest: +SKIP
    """

    def __init__(
        self,
        transport: Transport,
        session: Session,
        address: str | None = None,
        cached_product_info: dict[str, int] | None = None,
    ) -> None:
        """
        Initialize device info service.

        Args:
            transport: Transport layer for BLE communication
            session: Session manager for state tracking
            address: Optional BLE device address for reading advertisement data
            cached_product_info: Optional cached product info from advertisement scan
        """
        super().__init__(transport, session)
        self.address = address
        self.cached_product_info = cached_product_info

    async def read_info(self) -> DeviceInfo | None:
        """
        Read complete device information (combined basic + detailed).

        This is a convenience method that reads both basic info from BLE
        advertisement and detailed info from Class 7 strings.

        Returns:
            DeviceInfo with all available fields, or None if read failed

        Example:
            >>> info = await device_info.read_info()  # doctest: +SKIP
            >>> print(f"Product: {info.product_family}/{info.product_type}")  # doctest: +SKIP
            >>> print(f"Serial: {info.serial_number}")  # doctest: +SKIP
            >>> print(f"SW Version: {info.software_version}")  # doctest: +SKIP
        """
        # Combine basic and detailed info
        info_dict: dict[str, Any] = {}

        # Try to use cached product info first (from pre-connection scan)
        if self.cached_product_info:
            info_dict.update(self.cached_product_info)
        # Otherwise try to read basic info from BLE advertisement (if address available and not connected)
        elif self.address:
            basic_info = await self.read_basic(self.address)
            if basic_info:
                info_dict.update(
                    {
                        "product_family": basic_info.product_family,
                        "product_type": basic_info.product_type,
                        "product_version": basic_info.product_version,
                    }
                )

        # Read detailed info from Class 7 strings
        detailed_info = await self.read_detailed()
        if detailed_info:
            info_dict.update(
                {
                    "serial_number": detailed_info.serial_number,
                    "product_name": detailed_info.product_name,
                    "software_version": detailed_info.software_version,
                    "hardware_version": detailed_info.hardware_version,
                    "ble_version": detailed_info.ble_version,
                }
            )

        # Return combined info if we got any data
        if info_dict:
            return DeviceInfo(**info_dict)

        return None

    async def read_basic(self, address: str) -> DeviceInfo | None:
        """
        Read basic device info from BLE advertisement.

        This method scans for the device and extracts product information
        from the BLE service data. No connection is required.

        Args:
            address: BLE MAC address of the device

        Returns:
            DeviceInfo with product_family, product_type, product_version,
            or None if scan failed

        Example:
            >>> info = await device_info.read_basic("AA:BB:CC:DD:EE:FF")  # doctest: +SKIP
            >>> print(f"Product family: {info.product_family}")  # doctest: +SKIP
            >>> print(f"Product type: {info.product_type}")  # doctest: +SKIP
            >>> print(f"Product version: {info.product_version}")  # doctest: +SKIP

        Implementation Notes:
            - GENI service UUID: 0000fdd0-0000-1000-8000-00805f9b34fb
            - Service data format: `[??][??][??][Family][Type][Version]...`
            - Can be called without being connected
            - Uses BleakScanner to discover devices
        """
        try:
            from bleak import BleakScanner

            logger.debug(f"Scanning for device {address}...")

            # Scan with advertisement data
            devices = await BleakScanner.discover(timeout=5.0, return_adv=True)

            for device, adv in devices.values():
                if str(device.address).lower() == address.lower():
                    logger.debug(f"Found device: {device.name}")

                    # GENI service UUID
                    service_uuid = "0000fdd0-0000-1000-8000-00805f9b34fb"

                    if service_uuid in adv.service_data:
                        data = adv.service_data[service_uuid]
                        logger.debug(f"Service data: {data.hex()}")

                        if len(data) >= 6:
                            return DeviceInfo(
                                product_family=data[3],
                                product_type=data[4],
                                product_version=data[5],
                            )
                    else:
                        logger.debug("No GENI service data in advertisement")

        except READ_ERRORS as e:
            logger.error(f"Failed to read basic device info: {e}")

        return None

    async def read_detailed(self) -> DeviceInfo | None:
        """
        Read detailed device info via Class 7 string parameters.

        This method reads device identification strings including:
        - Serial number
        - Software version
        - Hardware version
        - BLE version

        Requires an active authenticated connection.

        Returns:
            DeviceInfo with all available fields, or None if read failed

        Raises:
            ConnectionError: If not connected or not authenticated

        Example:
            >>> info = await device_info.read_detailed()  # doctest: +SKIP
            >>> print(f"Serial: {info.serial_number}")  # doctest: +SKIP
            >>> print(f"SW Version: {info.software_version}")  # doctest: +SKIP
            >>> print(f"HW Version: {info.hardware_version}")  # doctest: +SKIP

        Implementation Notes:
            - Uses Class 7 ReadString command (0x07, 0x01)
            - String IDs: 9=serial, 50=sw_ver, 52=hw_ver, 58=ble_ver
            - Response format: `[STX][LEN][DST][SRC][0x07][Count][String][CRC]`
              - six header bytes, then the text
            - Strings are UTF-8 encoded, null-terminated
        """
        self.session.ensure_authenticated()

        device_info_dict: dict[str, Any] = {}

        try:
            # ID 9 is the serial number, whole. It used to arrive as
            # "0000479" and have a "1" prepended to make "10000479" - which
            # was right for this unit by luck, since the missing character
            # really was a "1". The string was one short because the Class 7
            # header was read as seven bytes instead of six; with that
            # fixed the pump returns "10000479" itself, and prepending
            # anything would corrupt it.
            serial = await self._read_class7_string(9)
            if serial:
                device_info_dict["serial_number"] = serial

            # ID 1 is the product name. Same off-by-one: it arrived as
            # "LPHA HWR" and was rewritten to "ALPHA HWR" by name.
            product_name = await self._read_class7_string(1)
            if product_name:
                device_info_dict["product_name"] = product_name

            # Read software version (ID 50)
            sw_ver = await self._read_class7_string(50)
            if sw_ver:
                device_info_dict["software_version"] = sw_ver

            # Read hardware version (ID 52)
            hw_ver = await self._read_class7_string(52)
            if hw_ver:
                device_info_dict["hardware_version"] = hw_ver

            # Read BLE version (ID 58)
            ble_ver = await self._read_class7_string(58)
            if ble_ver:
                device_info_dict["ble_version"] = ble_ver

            if device_info_dict:
                return DeviceInfo(**device_info_dict)

        except READ_ERRORS as e:
            logger.error(f"Failed to read detailed device info: {e}")

        return None

    async def read_statistics(self) -> Statistics | None:
        """
        Read device operational statistics.

        Reads statistics from Class 10 Object 93, Sub-ID 1:
        - Total runtime hours
        - Start count

        Note: Energy consumption (kWh) is NOT available on ALPHA HWR.
              Object 77 (cumulative energy) is not implemented.
              Only instantaneous power (W) is available via telemetry.

        Returns:
            Statistics object with available data, or None if read failed

        Example:
            >>> stats = await device_info.read_statistics()  # doctest: +SKIP
            >>> print(f"Runtime: {stats.operating_hours} hours")  # doctest: +SKIP
            >>> print(f"Starts: {stats.start_count}")  # doctest: +SKIP

        Implementation Notes:
            - Object 93, Sub-ID 1 (Type 248: operation_history_pump_obj)
            - Format: `[starts(4)][starts_1h(2)][starts_24h(2)][operating_time(4)]...`
            - Response has 3-byte header [00 00 XX]
            - operating_time is in seconds, convert to hours
        """
        self.session.ensure_authenticated()

        try:
            # Read operation history (Object 93, Sub-ID 1)
            data = await self._read_class10_object(93, 1)

            if (
                data and len(data) >= 15
            ):  # 3 byte header + at least 12 bytes of data
                # Skip 3-byte Class 10 header
                payload = data[3:]

                # Parse structure:
                # starts at offset 0 (4 bytes, uint32)
                import struct

                start_count = struct.unpack(">I", payload[0:4])[0]

                # operating_time at offset 8 (4 bytes, uint32, in seconds)
                op_time_seconds = struct.unpack(">I", payload[8:12])[0]
                operating_hours = op_time_seconds / 3600.0

                logger.debug(
                    f"Statistics: starts={start_count}, hours={operating_hours:.1f}"
                )

                return Statistics(
                    operating_hours=operating_hours,
                    start_count=start_count,
                    energy_kwh=None,  # Not supported on ALPHA HWR
                )
            else:
                logger.warning(
                    f"Statistics data too short: {len(data) if data else 0} bytes"
                )
                return None

        except READ_ERRORS as e:
            logger.error(f"Failed to read statistics: {e}")
            return None

    async def read_alarms(self) -> AlarmInfo | None:
        """
        Read current alarm state.

        Reads active alarms and warnings from Class 10 Object 88:
        - Sub-ID 0: Active alarms
        - Sub-ID 11: Active warnings

        Returns:
            AlarmInfo with active alarm/warning codes, or None if read failed

        Example:
            >>> alarms = await device_info.read_alarms()  # doctest: +SKIP
            >>> if alarms.active_alarms:  # doctest: +SKIP
            ...     print(f"Active alarms: {alarms.active_alarms}")
            >>> if alarms.active_warnings:  # doctest: +SKIP
            ...     print(f"Active warnings: {alarms.active_warnings}")

        Implementation Notes:
            - Object 88, Sub-ID 0: Active alarms (Type 570)
            - Object 88, Sub-ID 11: Active warnings (Type 570)
            - Format: Array of uint16 codes
            - Zero codes indicate "no alarm/warning"
        """
        self.session.ensure_authenticated()

        try:
            # Read active alarms (Object 88, Sub 0)
            alarm_data = await self._read_class10_object(88, 0)

            # Read active warnings (Object 88, Sub 11)
            warning_data = await self._read_class10_object(88, 11)

            # Parse uint16 arrays
            active_alarms = (
                self._parse_uint16_array(alarm_data) if alarm_data else []
            )
            active_warnings = (
                self._parse_uint16_array(warning_data) if warning_data else []
            )

            # Build descriptions from code lookup
            alarm_desc = (
                ", ".join(
                    ERROR_CODES.get(c, f"Unknown ({c})") for c in active_alarms
                )
                if active_alarms
                else None
            )
            warning_desc = (
                ", ".join(
                    ERROR_CODES.get(c, f"Unknown ({c})")
                    for c in active_warnings
                )
                if active_warnings
                else None
            )

            return AlarmInfo(
                active_alarms=active_alarms,
                active_warnings=active_warnings,
                alarm_description=alarm_desc,
                warning_description=warning_desc,
            )

        except READ_ERRORS as e:
            logger.error(f"Failed to read alarms: {e}")

        return None

    # Helper methods

    def _parse_uint16_array(self, data: bytes) -> list[int]:
        """
        Parse array of uint16 values.

        Args:
            data: Raw bytes containing uint16 array

        Returns:
            List of uint16 values (zero codes filtered out)
        """
        codes = []
        for i in range(0, len(data), 2):
            if i + 2 <= len(data):
                code = (data[i] << 8) | data[i + 1]
                if code != 0:
                    codes.append(code)
        return codes
