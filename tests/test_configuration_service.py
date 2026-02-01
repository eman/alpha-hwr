"""
Tests for ConfigurationService.

Tests backup/restore functionality for pump configuration.
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from alpha_hwr.constants import ControlMode
from alpha_hwr.models import DeviceInfo, ScheduleEntry, SetpointInfo


@pytest.fixture
def mock_device_info_service():
    """Mock DeviceInfoService for testing."""
    service = Mock()
    service.read_info = AsyncMock(
        return_value=DeviceInfo(
            serial_number="12345678",
            product_name="ALPHA HWR 15-60",
            hardware_version="1.0",
            software_version="2.3",
        )
    )
    return service


@pytest.fixture
def mock_control_service():
    """Mock ControlService for testing."""
    service = Mock()
    service.get_mode = AsyncMock(
        return_value=SetpointInfo(
            control_mode=ControlMode.CONSTANT_PRESSURE,
            operation_mode=0,
            setpoint=4.5 * 9806.65,  # Convert meters to Pascals
            max_setpoint=None,
            unit="m",
        )
    )
    service.set_mode = AsyncMock(return_value=True)
    service.set_constant_pressure = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_schedule_service():
    """Mock ScheduleService for testing."""
    service = Mock()
    service.get_state = AsyncMock(return_value=True)
    service.read_entries = AsyncMock(
        return_value=[
            ScheduleEntry(
                day="Monday",
                begin_hour=6,
                begin_minute=0,
                end_hour=8,
                end_minute=0,
                action=2,
                layer=0,
                enabled=True,
            ),
            ScheduleEntry(
                day="Tuesday",
                begin_hour=18,
                begin_minute=30,
                end_hour=22,
                end_minute=0,
                action=1,
                layer=1,
                enabled=True,
            ),
        ]
    )
    service.write_entries = AsyncMock(return_value=True)
    service.enable = AsyncMock(return_value=True)
    service.disable = AsyncMock(return_value=True)
    return service


@pytest.fixture
def config_service(
    mock_device_info_service, mock_control_service, mock_schedule_service
):
    """Create ConfigurationService with mocked dependencies."""
    from alpha_hwr.services.configuration import ConfigurationService

    return ConfigurationService(
        mock_device_info_service, mock_control_service, mock_schedule_service
    )


class TestBackup:
    """Tests for backup() method."""

    @pytest.mark.asyncio
    async def test_backup_success(self, config_service, tmp_path):
        """Test successful backup to file."""
        backup_file = tmp_path / "test_backup.json"

        result = await config_service.backup(str(backup_file))

        assert result is True
        assert backup_file.exists()

        # Verify backup content
        with open(backup_file) as f:
            data = json.load(f)

        assert data["version"] == "1.0"
        assert "timestamp" in data
        assert data["device"]["serial_number"] == "12345678"
        assert data["device"]["product_name"] == "ALPHA HWR 15-60"
        assert data["control_mode"]["mode_name"] == "CONSTANT_PRESSURE"
        # Setpoint is stored in raw Pascals (4.5m * 9806.65 Pa/m)
        assert data["control_mode"]["setpoint"] == pytest.approx(
            4.5 * 9806.65, abs=1.0
        )
        assert data["schedule"]["enabled"] is True
        assert len(data["schedule"]["days"]) == 2

    @pytest.mark.asyncio
    async def test_backup_creates_directory(self, config_service, tmp_path):
        """Test backup creates parent directories if needed."""
        backup_file = tmp_path / "nested" / "dirs" / "backup.json"

        result = await config_service.backup(str(backup_file))

        assert result is True
        assert backup_file.exists()
        assert backup_file.parent.exists()

    @pytest.mark.asyncio
    async def test_backup_device_info_failure(self, config_service, tmp_path):
        """Test backup continues when device info read fails."""
        backup_file = tmp_path / "backup.json"

        # Make device info fail
        config_service.device_info.read_info = AsyncMock(
            side_effect=Exception("Device read error")
        )

        result = await config_service.backup(str(backup_file))

        # Should still succeed with empty device data
        assert result is True
        assert backup_file.exists()

        with open(backup_file) as f:
            data = json.load(f)

        assert data["device"] == {}

    @pytest.mark.asyncio
    async def test_backup_control_mode_failure(self, config_service, tmp_path):
        """Test backup continues when control mode read fails."""
        backup_file = tmp_path / "backup.json"

        # Make control service fail
        config_service.control.get_mode = AsyncMock(
            side_effect=Exception("Control read error")
        )

        result = await config_service.backup(str(backup_file))

        assert result is True

        with open(backup_file) as f:
            data = json.load(f)

        assert data["control_mode"] == {}

    @pytest.mark.asyncio
    async def test_backup_schedule_failure(self, config_service, tmp_path):
        """Test backup continues when schedule read fails."""
        backup_file = tmp_path / "backup.json"

        # Make schedule service fail
        config_service.schedule.get_state = AsyncMock(
            side_effect=Exception("Schedule read error")
        )

        result = await config_service.backup(str(backup_file))

        assert result is True

        with open(backup_file) as f:
            data = json.load(f)

        assert data["schedule"] == {}

    @pytest.mark.asyncio
    async def test_backup_invalid_path(self, config_service):
        """Test backup with invalid file path."""
        # Use a path that cannot be written (e.g., directory as file)
        result = await config_service.backup("/dev/null/invalid/path.json")

        assert result is False


class TestRestore:
    """Tests for restore() method."""

    @pytest.mark.asyncio
    async def test_restore_success(self, config_service, tmp_path):
        """Test successful restore from backup file."""
        # Create a backup file first
        backup_file = tmp_path / "backup.json"
        await config_service.backup(str(backup_file))

        # Now restore it
        result = await config_service.restore(
            str(backup_file),
            restore_mode=True,
            restore_schedule=True,
            verify_device=False,
        )

        assert result is True
        # Verify it called set_constant_pressure (not set_mode)
        config_service.control.set_constant_pressure.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_only_mode(self, config_service, tmp_path):
        """Test restore with only control mode."""
        backup_file = tmp_path / "backup.json"
        await config_service.backup(str(backup_file))

        result = await config_service.restore(
            str(backup_file),
            restore_mode=True,
            restore_schedule=False,
            verify_device=False,
        )

        assert result is True
        config_service.control.set_constant_pressure.assert_called_once()
        config_service.schedule.write_entries.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_only_schedule(self, config_service, tmp_path):
        """Test restore with only schedule."""
        backup_file = tmp_path / "backup.json"
        await config_service.backup(str(backup_file))

        result = await config_service.restore(
            str(backup_file),
            restore_mode=False,
            restore_schedule=True,
            verify_device=False,
        )

        assert result is True
        config_service.control.set_constant_pressure.assert_not_called()
        # write_entries is called once per layer (2 layers in our fixture)
        assert config_service.schedule.write_entries.call_count == 2

    @pytest.mark.asyncio
    async def test_restore_file_not_found(self, config_service):
        """Test restore with non-existent file."""
        result = await config_service.restore(
            "nonexistent.json",
            restore_mode=True,
            restore_schedule=True,
            verify_device=False,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_restore_invalid_json(self, config_service, tmp_path):
        """Test restore with invalid JSON file."""
        backup_file = tmp_path / "invalid.json"
        backup_file.write_text("not valid json{")

        result = await config_service.restore(
            str(backup_file),
            restore_mode=True,
            restore_schedule=True,
            verify_device=False,
        )

        assert result is False


class TestExportImport:
    """Tests for export_json() and import_json() methods."""

    @pytest.mark.asyncio
    async def test_export_json(self, config_service, tmp_path):
        """Test export_json is alias for backup."""
        export_file = tmp_path / "export.json"

        result = await config_service.export_json(str(export_file))

        assert result is True
        assert export_file.exists()

    @pytest.mark.asyncio
    async def test_import_json(self, config_service, tmp_path):
        """Test import_json is alias for restore."""
        # Create export first
        export_file = tmp_path / "export.json"
        await config_service.export_json(str(export_file))

        # Import it
        result = await config_service.import_json(
            str(export_file),
            restore_mode=True,
            restore_schedule=True,
            verify_device=False,
        )

        assert result is True


class TestConfigurationServiceIntegration:
    """Integration tests for ConfigurationService."""

    @pytest.mark.asyncio
    async def test_backup_restore_roundtrip(self, config_service, tmp_path):
        """Test complete backup and restore cycle."""
        backup_file = tmp_path / "roundtrip.json"

        # Backup
        backup_result = await config_service.backup(str(backup_file))
        assert backup_result is True

        # Restore
        restore_result = await config_service.restore(
            str(backup_file),
            restore_mode=True,
            restore_schedule=True,
            verify_device=False,
        )
        assert restore_result is True

        # Verify calls
        assert config_service.control.set_constant_pressure.called
        assert config_service.schedule.write_entries.called

    @pytest.mark.asyncio
    async def test_multiple_backups_same_file(self, config_service, tmp_path):
        """Test overwriting backup file multiple times."""
        backup_file = tmp_path / "backup.json"

        # Create multiple backups to same file
        result1 = await config_service.backup(str(backup_file))
        result2 = await config_service.backup(str(backup_file))
        result3 = await config_service.backup(str(backup_file))

        assert result1 is True
        assert result2 is True
        assert result3 is True
        assert backup_file.exists()

        # Verify last backup is valid
        with open(backup_file) as f:
            data = json.load(f)

        assert data["version"] == "1.0"
