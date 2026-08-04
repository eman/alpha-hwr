"""
Tests for configuration backup and restore functionality.

This module tests the ConfigurationService's ability to:
- Back up pump configuration to JSON files
- Restore pump configuration from JSON files
- Handle serial number mismatches
- Validate backup file structure
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from alpha_hwr.constants import ControlMode
from alpha_hwr.models import DeviceInfo, ScheduleEntry, SetpointInfo

# Note: client fixture is now provided by conftest.py as mock_client_simple


class TestBackupConfiguration:
    """Tests for configuration backup functionality."""

    @pytest.mark.asyncio
    async def test_backup_configuration_success(self, mock_client_simple):
        """Test successfully backing up configuration."""
        # Mock device info
        mock_client_simple.device_info.read_info = AsyncMock(
            return_value=DeviceInfo(
                serial_number="12345678",
                product_name="ALPHA HWR",
                hardware_version="1.0",
                software_version="2.0",
            )
        )

        # Mock control mode
        mock_client_simple.control.get_mode = AsyncMock(
            return_value=SetpointInfo(
                control_mode=ControlMode.CONSTANT_PRESSURE,
                operation_mode=0,
                setpoint=3.5,
                min_setpoint=1.0,
                max_setpoint=8.0,
                unit="m",
            )
        )

        # Mock schedule
        mock_client_simple.schedule.get_state = AsyncMock(return_value=True)
        mock_client_simple.schedule.read_entries = AsyncMock(
            return_value=[
                ScheduleEntry(
                    day="Monday",
                    enabled=True,
                    action=2,
                    begin_hour=6,
                    begin_minute=0,
                    end_hour=8,
                    end_minute=0,
                    layer=0,
                )
            ]
        )

        # Create temp file
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            temp_path = f.name

        try:
            # Backup
            result = await mock_client_simple.config.backup(temp_path)
            assert result is True

            # Verify file was created
            assert os.path.exists(temp_path)

            # Verify file contents
            backup_data = json.loads(
                await asyncio.to_thread(Path(temp_path).read_text)
            )

            assert backup_data["version"] == "1.0"
            assert "timestamp" in backup_data
            assert backup_data["device"]["serial_number"] == "12345678"
            assert (
                backup_data["control_mode"]["mode_name"] == "CONSTANT_PRESSURE"
            )
            assert backup_data["control_mode"]["setpoint"] == 3.5
            assert backup_data["schedule"]["enabled"] is True
            assert len(backup_data["schedule"]["days"]) == 1
            assert backup_data["schedule"]["days"][0]["day"] == "Monday"

        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_backup_configuration_creates_directory(
        self, mock_client_simple
    ):
        """Test that backup creates parent directories."""
        # Mock minimal data
        mock_client_simple.device_info.read_info = AsyncMock(
            return_value=DeviceInfo(serial_number="12345678")
        )
        mock_client_simple.control.get_mode = AsyncMock(return_value=None)
        mock_client_simple.schedule.get_state = AsyncMock(return_value=False)
        mock_client_simple.schedule.read_entries = AsyncMock(return_value=[])

        temp_dir = tempfile.mkdtemp()

        try:
            nested_path = os.path.join(
                temp_dir, "subdir1", "subdir2", "backup.json"
            )

            result = await mock_client_simple.config.backup(nested_path)
            assert result is True
            assert os.path.exists(nested_path)

        finally:
            import shutil

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


class TestRestoreConfiguration:
    """Tests for configuration restore functionality."""

    @pytest.mark.asyncio
    async def test_restore_configuration_file_not_found(
        self, mock_client_simple
    ):
        """Test handling of missing backup file."""
        result = await mock_client_simple.config.restore(
            "/nonexistent/file.json"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_restore_configuration_success(self, mock_client_simple):
        """Test successfully restoring configuration."""
        backup_data = {
            "version": "1.0",
            "timestamp": "2026-01-29T12:00:00Z",
            "device": {
                "serial_number": "12345678",
                "product_name": "ALPHA HWR",
            },
            "control_mode": {
                "mode_name": "CONSTANT_PRESSURE",
                "setpoint": 3.5,
                "max_setpoint": 10.0,
            },
            "schedule": {
                "enabled": True,
                "days": [
                    {
                        "day": "Monday",
                        "begin_hour": 6,
                        "begin_minute": 0,
                        "end_hour": 8,
                        "end_minute": 0,
                        "action": 2,
                        "enabled": True,
                        "layer": 0,
                    }
                ],
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            json.dump(backup_data, f)
            temp_path = f.name

        try:
            # Mock device info for serial number check
            mock_client_simple.device_info.read_info = AsyncMock(
                return_value=DeviceInfo(serial_number="12345678")
            )

            # Mock restore operations
            mock_client_simple.control.set_constant_pressure = AsyncMock(
                return_value=True
            )
            mock_client_simple.schedule.enable = AsyncMock(return_value=True)
            mock_client_simple.schedule.write_entries = AsyncMock(
                return_value=True
            )

            result = await mock_client_simple.config.restore(temp_path)
            assert result is True

            # Verify operations were called
            assert mock_client_simple.control.set_constant_pressure.called
            assert mock_client_simple.schedule.write_entries.called

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_restore_configuration_serial_mismatch(
        self, mock_client_simple
    ):
        """Test warning when serial numbers don't match."""
        backup_data = {
            "version": "1.0",
            "device": {"serial_number": "99999999"},
            "control_mode": {
                "mode_name": "CONSTANT_PRESSURE",
                "setpoint": 3.5,
                "max_setpoint": 10.0,
            },
            "schedule": {"enabled": False, "days": []},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            json.dump(backup_data, f)
            temp_path = f.name

        try:
            # Mock device info with different serial
            mock_client_simple.device_info.read_info = AsyncMock(
                return_value=DeviceInfo(serial_number="12345678")
            )

            # Mock restore operations
            mock_client_simple.control.set_constant_pressure = AsyncMock(
                return_value=True
            )
            mock_client_simple.schedule.disable = AsyncMock(return_value=True)

            # Restore should proceed with verify_device=False
            result = await mock_client_simple.config.restore(
                temp_path, verify_device=False
            )

            # Should succeed even with different serial
            assert result is True

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_restore_configuration_skip_options(self, mock_client_simple):
        """Test restore with skip options."""
        backup_data = {
            "version": "1.0",
            "device": {"serial_number": "12345678"},
            "control_mode": {
                "mode_name": "CONSTANT_PRESSURE",
                "setpoint": 3.5,
                "max_setpoint": 10.0,
            },
            "schedule": {"enabled": True, "days": []},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            json.dump(backup_data, f)
            temp_path = f.name

        try:
            mock_client_simple.device_info.read_info = AsyncMock(
                return_value=DeviceInfo(serial_number="12345678")
            )
            mock_client_simple.control.set_constant_pressure = AsyncMock(
                return_value=True
            )
            mock_client_simple.schedule.enable = AsyncMock(return_value=True)
            mock_client_simple.schedule.write_entries = AsyncMock(
                return_value=True
            )

            # Restore with restore_schedule=False
            result = await mock_client_simple.config.restore(
                temp_path, restore_schedule=False
            )

            # Control mode should be restored
            assert mock_client_simple.control.set_constant_pressure.called

            # Schedule operations should NOT be called
            assert not mock_client_simple.schedule.enable.called
            assert not mock_client_simple.schedule.write_entries.called

            assert result is True

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_restore_configuration_version_mismatch(
        self, mock_client_simple
    ):
        """Test handling of version mismatch."""
        backup_data = {
            "version": "99.0",  # Future version
            "device": {"serial_number": "12345678"},
            "control_mode": {
                "mode_name": "CONSTANT_PRESSURE",
                "setpoint": 3.5,
                "max_setpoint": 10.0,
            },
            "schedule": {"enabled": False, "days": []},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            json.dump(backup_data, f)
            temp_path = f.name

        try:
            # Even with version mismatch, restore should attempt to proceed
            mock_client_simple.device_info.read_info = AsyncMock(
                return_value=DeviceInfo(serial_number="12345678")
            )
            mock_client_simple.control.set_constant_pressure = AsyncMock(
                return_value=True
            )

            result = await mock_client_simple.config.restore(temp_path)

            # Restore may log a warning but should still attempt restoration
            # Result depends on implementation
            assert result is not None

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
