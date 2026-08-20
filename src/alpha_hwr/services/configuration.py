"""
Configuration Management Service for Grundfos ALPHA HWR pumps.

This module handles backup and restore operations for pump configuration.
Configurations are saved as JSON files for portability and human readability.

Backup includes:
- Device information (serial number, product name, versions)
- Control mode and setpoint
- Schedule enabled status and all entries (all 5 layers)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from alpha_hwr.constants import MODE_NAMES, ControlMode
from alpha_hwr.exceptions import READ_ERRORS
from alpha_hwr.models import ScheduleEntry

if TYPE_CHECKING:
    from alpha_hwr.services.control import ControlService
    from alpha_hwr.services.device_info import DeviceInfoService
    from alpha_hwr.services.schedule import ScheduleService

logger = logging.getLogger(__name__)


class ConfigurationService:
    """
    Manages pump configuration backup and restore.

    Provides JSON-based backup/restore functionality for the complete
    pump configuration including control mode, setpoint, and schedule.

    Example:
        >>> config_service = ConfigurationService(  # doctest: +SKIP
        ...     device_info_service,
        ...     control_service,
        ...     schedule_service
        ... )
        >>>
        >>> # Backup configuration
        >>> success = await config_service.backup("pump_backup.json")  # doctest: +SKIP
        >>> if success:  # doctest: +SKIP
        ...     print("Configuration backed up successfully")
        >>>
        >>> # Restore configuration
        >>> success = await config_service.restore(  # doctest: +SKIP
        ...     "pump_backup.json",
        ...     restore_mode=True,
        ...     restore_schedule=True,
        ...     verify_device=True
        ... )
    """

    BACKUP_VERSION = "1.0"

    def __init__(
        self,
        device_info_service: DeviceInfoService,
        control_service: ControlService,
        schedule_service: ScheduleService,
    ):
        """
        Initialize the configuration service.

        Args:
            device_info_service: Service for reading device information
            control_service: Service for control mode operations
            schedule_service: Service for schedule operations
        """
        self.device_info = device_info_service
        self.control = control_service
        self.schedule = schedule_service

    async def backup(self, filepath: str) -> bool:
        """
        Backup the complete pump configuration to a JSON file.

        Creates a comprehensive backup including:
        - Device information (serial, product name, versions)
        - Control mode and current setpoint
        - Schedule enabled status and all entries

        Args:
            filepath: Path to the output JSON file

        Returns:
            True if successful, False otherwise

        Raises:
            IOError: If file cannot be written

        Example:
            >>> success = await service.backup("pump_backup.json")  # doctest: +SKIP
            >>> if success:  # doctest: +SKIP
            ...     print("Backup saved")

        Implementation Notes:
            JSON structure:
            {
              "version": "1.0",
              "timestamp": "2026-01-30T12:34:56Z",
              "device": {
                "serial_number": "12345678",
                "product_name": "ALPHA HWR 15-60",
                "hardware_version": "1.0",
                "software_version": "2.3"
              },
              "control_mode": {
                "mode_name": "CONSTANT_PRESSURE",
                "setpoint": 4.5,
                "max_setpoint": null,
                "setpoint_unit": "m"
              },
              "schedule": {
                "enabled": true,
                "days": [
                  {
                    "day": "Monday",
                    "begin_hour": 6,
                    "begin_minute": 0,
                    "end_hour": 8,
                    "end_minute": 0,
                    "action": 2,
                    "layer": 0,
                    "enabled": true
                  }
                ]
              }
            }
        """
        logger.info(f"Backing up configuration to {filepath}...")

        try:
            # Initialize backup structure
            backup_data: dict[str, Any] = {
                "version": self.BACKUP_VERSION,
                "timestamp": datetime.now(UTC).isoformat(),
                "device": {},
                "control_mode": {},
                "schedule": {},
            }

            # Get device information
            try:
                device_info = await self.device_info.read_info()
                if device_info:
                    backup_data["device"] = {
                        "serial_number": device_info.serial_number,
                        "product_name": device_info.product_name,
                        "hardware_version": device_info.hardware_version,
                        "software_version": device_info.software_version,
                    }
            except READ_ERRORS as e:
                logger.warning(f"Could not read device info: {e}")

            # Get control mode and setpoint
            try:
                setpoint_info = await self.control.get_mode()

                if setpoint_info:
                    # Convert mode ID to name
                    mode_id = setpoint_info.control_mode
                    try:
                        mode_enum = ControlMode(mode_id)
                        mode_name = MODE_NAMES.get(mode_enum, mode_enum.name)
                    except ValueError:
                        mode_name = f"Unknown ({mode_id})"

                    backup_data["control_mode"] = {
                        "mode_name": mode_name,
                        "setpoint": setpoint_info.setpoint,
                        "min_setpoint": setpoint_info.min_setpoint,
                        "max_setpoint": setpoint_info.max_setpoint,
                        "setpoint_unit": setpoint_info.unit,
                    }
            except READ_ERRORS as e:
                logger.warning(f"Could not read control mode: {e}")

            # Get schedule
            try:
                enabled = await self.schedule.get_state()
                entries = await self.schedule.read_entries()

                backup_data["schedule"] = {
                    "enabled": enabled if enabled is not None else False,
                    "days": [e.to_dict() for e in entries],
                }
            except READ_ERRORS as e:
                logger.warning(f"Could not read schedule: {e}")

            # Write to file
            filepath_obj = Path(filepath)
            filepath_obj.parent.mkdir(parents=True, exist_ok=True)

            await asyncio.to_thread(
                filepath_obj.write_text, json.dumps(backup_data, indent=2)
            )

            logger.info(f"Configuration backed up successfully to {filepath}")
            return True

        except READ_ERRORS:
            logger.exception("Error backing up configuration")
            return False

    async def restore(
        self,
        filepath: str,
        restore_mode: bool = True,
        restore_schedule: bool = True,
        verify_device: bool = True,
    ) -> bool:
        """
        Restore pump configuration from a JSON backup file.

        Restores the pump to a previously saved configuration state.
        Individual restore options can be enabled/disabled.

        Args:
            filepath: Path to the backup JSON file
            restore_mode: Restore control mode and setpoint (default True)
            restore_schedule: Restore schedule configuration (default True)
            verify_device: Verify device serial number matches backup (default True)

        Returns:
            True if successful, False otherwise

        Raises:
            FileNotFoundError: If backup file doesn't exist
            ValueError: If backup version is unsupported
            ConnectionError: If not connected to pump

        Example:
            >>> # Restore everything
            >>> success = await service.restore("pump_backup.json")  # doctest: +SKIP
            >>>
            >>> # Restore only schedule
            >>> success = await service.restore(  # doctest: +SKIP
            ...     "pump_backup.json",
            ...     restore_mode=False,
            ...     verify_device=False
            ... )

        Implementation Notes:
            Restore process:
            1. Read and validate backup file
            2. Verify backup version compatibility
            3. Optionally verify device serial number
            4. Restore control mode and setpoint if requested
            5. Restore schedule entries and enabled state if requested
        """
        logger.info(f"Restoring configuration from {filepath}...")

        try:
            # Read backup file
            filepath_obj = Path(filepath)
            if not filepath_obj.exists():
                logger.error(f"Backup file not found: {filepath}")
                return False

            backup_data = json.loads(
                await asyncio.to_thread(filepath_obj.read_text)
            )

            # Verify backup version
            if backup_data.get("version") != self.BACKUP_VERSION:
                logger.error(
                    f"Unsupported backup version: {backup_data.get('version')}"
                )
                return False

            # Verify device if requested
            if verify_device:
                device_info = await self.device_info.read_info()
                backup_serial = backup_data.get("device", {}).get(
                    "serial_number"
                )

                if (
                    device_info
                    and backup_serial
                    and device_info.serial_number != backup_serial
                ):
                    logger.error(
                        f"Device serial mismatch! "
                        f"Current: {device_info.serial_number}, "
                        f"Backup: {backup_serial}"
                    )
                    return False

            success = True

            # Restore control mode and setpoint
            if restore_mode and "control_mode" in backup_data:
                success &= await self._restore_control_mode(
                    backup_data["control_mode"]
                )

            # Restore schedule
            if restore_schedule and "schedule" in backup_data:
                success &= await self._restore_schedule(backup_data["schedule"])

            if success:
                logger.info("Configuration restored successfully")
            else:
                logger.warning("Configuration restored with errors")

            return success

        except READ_ERRORS:
            logger.exception("Error restoring configuration")
            return False

    async def export_json(self, filepath: str) -> bool:
        """
        Export configuration as JSON (alias for backup).

        This is provided for API consistency with import_json.

        Args:
            filepath: Path to the output JSON file

        Returns:
            True if successful, False otherwise

        Example:
            >>> await service.export_json("config.json")  # doctest: +SKIP
        """
        return await self.backup(filepath)

    async def import_json(
        self,
        filepath: str,
        restore_mode: bool = True,
        restore_schedule: bool = True,
        verify_device: bool = True,
    ) -> bool:
        """
        Import configuration from JSON (alias for restore).

        This is provided for API consistency with export_json.

        Args:
            filepath: Path to the backup JSON file
            restore_mode: Restore control mode and setpoint
            restore_schedule: Restore schedule configuration
            verify_device: Verify device serial number matches

        Returns:
            True if successful, False otherwise

        Example:
            >>> await service.import_json("config.json")  # doctest: +SKIP
        """
        return await self.restore(
            filepath,
            restore_mode=restore_mode,
            restore_schedule=restore_schedule,
            verify_device=verify_device,
        )

    # -------------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------------

    async def _restore_control_mode(self, mode_data: dict[str, Any]) -> bool:
        """Restore control mode and setpoint from backup data."""
        try:
            mode_name = mode_data.get("mode_name")
            setpoint = mode_data.get("setpoint")
            min_setpoint = mode_data.get("min_setpoint")
            max_setpoint = mode_data.get("max_setpoint")

            if not mode_name or setpoint is None:
                logger.warning("Incomplete control mode data in backup")
                return False

            logger.info(
                f"Restoring control mode: {mode_name} (min={min_setpoint}, max={max_setpoint})"
            )

            # Special case for Temperature Range Control (needs two setpoints)
            if mode_name == "TEMPERATURE_RANGE_CONTROL":
                if min_setpoint is not None and max_setpoint is not None:
                    return await self.control.set_temperature_range_control(
                        min_setpoint, max_setpoint
                    )
                else:
                    logger.warning(
                        "Missing min/max setpoints for Temperature Range restore"
                    )
                    return False

            # Map mode name to setter method
            # Only support modes that are currently implemented
            mode_setters = {
                # Standard MODE_NAMES (UPPERCASE)
                "CONSTANT_PRESSURE": self.control.set_constant_pressure,
                "CONSTANT_SPEED": self.control.set_constant_speed,
                "CONSTANT_FLOW": self.control.set_constant_flow,
                # Legacy/Title Case Support
                "Constant Pressure": self.control.set_constant_pressure,
                "Constant Speed": self.control.set_constant_speed,
                "Constant Flow": self.control.set_constant_flow,
            }

            setter = mode_setters.get(mode_name)
            if not setter:
                logger.warning(
                    f"Control mode '{mode_name}' is not yet supported for restore. "
                    f"Supported modes: {', '.join(set(mode_setters.keys()))}"
                )
                return False

            # Call the setter (all current setters take a single setpoint)
            result = await setter(setpoint)

            if not result:
                logger.error(f"Failed to restore control mode: {mode_name}")
                return False

            return True

        except READ_ERRORS as e:
            logger.error(f"Error restoring control mode: {e}")
            return False

    async def _restore_schedule(self, schedule_data: dict[str, Any]) -> bool:
        """Restore schedule entries and enabled state from backup data."""
        try:
            # Restore schedule entries
            if "days" in schedule_data:
                # Group entries by layer
                layers: dict[int, list[ScheduleEntry]] = {}

                for entry_dict in schedule_data["days"]:
                    layer = entry_dict.get("layer", 0)
                    if layer not in layers:
                        layers[layer] = []

                    # Create ScheduleEntry
                    entry = ScheduleEntry(
                        day=entry_dict["day"],
                        begin_hour=entry_dict["begin_hour"],
                        begin_minute=entry_dict["begin_minute"],
                        end_hour=entry_dict["end_hour"],
                        end_minute=entry_dict["end_minute"],
                        layer=layer,
                        action=entry_dict.get("action", 0x02),
                        enabled=entry_dict.get("enabled", True),
                    )
                    layers[layer].append(entry)

                # Write each layer
                for layer, entries in layers.items():
                    logger.info(
                        f"Restoring {len(entries)} entries to layer {layer}"
                    )
                    if not await self.schedule.write_entries(
                        entries, layer=layer
                    ):
                        logger.error(
                            f"Failed to restore schedule layer {layer}"
                        )
                        return False

            # Restore schedule enabled status
            if "enabled" in schedule_data:
                enabled = schedule_data["enabled"]
                logger.info(f"Restoring schedule enabled status: {enabled}")

                if enabled:
                    success = await self.schedule.enable()
                else:
                    success = await self.schedule.disable()

                if not success:
                    logger.error("Failed to restore schedule enabled status")
                    return False

            return True

        except READ_ERRORS as e:
            logger.error(f"Error restoring schedule: {e}")
            return False
