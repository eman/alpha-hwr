"""
Integration test for full backup and restore cycle.
Simulates a complete workflow using mocks to ensure all components are wired correctly.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
import json
import tempfile
import os
from alpha_hwr.client import AlphaHWRClient
from alpha_hwr.models import DeviceInfo, SetpointInfo, ScheduleEntry
from alpha_hwr.constants import ControlMode


@pytest_asyncio.fixture
async def client():
    """Reusable connected client with mocked transport."""
    with (
        patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak,
        patch(
            "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
            new_callable=AsyncMock,
        ),
    ):
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        mock_instance.start_notify = AsyncMock()
        mock_instance.write_gatt_char = AsyncMock()
        mock_instance.is_connected = True
        mock_bleak.return_value = mock_instance

        client = AlphaHWRClient("AA:BB:CC:DD:EE:FF")
        await client.connect()

        # Mock transport methods
        assert client.transport is not None
        client.transport.query = AsyncMock(return_value=b"\x00" * 7)
        client.transport.write = AsyncMock()

        yield client
        await client.disconnect()

    @patch("alpha_hwr.client.AlphaHWRClient._read_class10_subid")
    @patch("alpha_hwr.client.AlphaHWRClient._query")
    @patch("alpha_hwr.client.AlphaHWRClient._send_command")
    def test_full_cycle(self, mock_send, mock_query, mock_read):
        """
        Test a full backup and restore cycle.
        1. Setup mock data representing a configured pump.
        2. Perform Backup to a JSON file.
        3. Verify JSON content.
        4. Perform Restore from that JSON file.
        5. Verify all Set commands were sent to restore the state.
        """

        # --- SETUP MOCK DATA ---


@pytest.mark.asyncio
async def test_full_cycle(client):
    """
    Test a full backup and restore cycle.
    1. Setup mock data representing a configured pump.
    2. Perform Backup to a JSON file.
    3. Verify JSON content.
    4. Perform Restore from that JSON file.
    5. Verify all Set commands were sent to restore the state.
    """

    # --- SETUP MOCK DATA ---

    # Patch the new API methods
    with (
        patch.object(
            client.device_info, "read_info", new_callable=AsyncMock
        ) as mock_read_info,
        patch.object(
            client.control, "get_mode", new_callable=AsyncMock
        ) as mock_get_mode,
        patch.object(
            client.schedule, "read_entries", new_callable=AsyncMock
        ) as mock_get_schedule,
        patch.object(
            client.control, "set_constant_pressure", new_callable=AsyncMock
        ) as mock_set_cp,
        patch.object(
            client.schedule, "write_entries", new_callable=AsyncMock
        ) as mock_set_schedule,
        patch.object(
            client.schedule, "enable", new_callable=AsyncMock
        ) as mock_enable_schedule,
        patch.object(
            client.schedule, "get_state", new_callable=AsyncMock
        ) as mock_get_enabled,
    ):
        # Configure Mock Returns for BACKUP

        mock_read_info.return_value = DeviceInfo(
            serial_number="TEST1234",
            product_name="ALPHA HWR",
            hardware_version="1.0",
            software_version="2.0",
        )

        # get_mode() returns a SetpointInfo object
        mock_get_mode.return_value = SetpointInfo(
            control_mode=ControlMode.CONSTANT_PRESSURE,
            operation_mode=0,
            setpoint=30000.0,  # Pascals (~3m)
            unit="m",  # Derived
        )

        mock_get_schedule.return_value = [
            ScheduleEntry(
                day="Monday",
                enabled=True,
                action=2,
                begin_hour=6,
                begin_minute=30,
                end_hour=9,
                end_minute=0,
                layer=0,
            ),
            ScheduleEntry(
                day="Tuesday",
                enabled=True,
                action=2,
                begin_hour=17,
                begin_minute=0,
                end_hour=22,
                end_minute=0,
                layer=0,
            ),
        ]

        mock_get_enabled.return_value = True

        # --- EXECUTE BACKUP ---

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            backup_path = f.name

        try:
            print(f"Backing up to {backup_path}...")
            success = await client.config.backup(backup_path)
            assert success, "Backup failed"

            # --- VERIFY BACKUP CONTENT ---

            with open(backup_path, "r") as f:
                data = json.load(f)

            print("Backup data:", json.dumps(data, indent=2))

            assert data["version"] == "1.0"
            assert data["device"]["serial_number"] == "TEST1234"
            assert data["control_mode"]["mode_name"] == "CONSTANT_PRESSURE"
            assert data["control_mode"]["setpoint"] == 30000.0

            assert data["schedule"]["enabled"] is True
            assert len(data["schedule"]["days"]) == 2

            # --- EXECUTE RESTORE ---

            # Setup mocks for restore
            mock_set_cp.return_value = True
            mock_set_schedule.return_value = True
            mock_enable_schedule.return_value = True

            print(f"Restoring from {backup_path}...")
            success = await client.config.restore(backup_path)
            assert success, "Restore failed"

            # --- VERIFY RESTORE CALLS ---

            # 1. Verify Mode Restore
            # Should call set_constant_pressure with the raw value (30000.0)
            mock_set_cp.assert_called_once_with(30000.0)

            # 2. Verify Schedule Restore
            mock_set_schedule.assert_called_once()
            call_args = mock_set_schedule.call_args
            entries = call_args[0][0]
            # Check if layer is passed as positional or kwarg
            if "layer" in call_args[1]:
                layer = call_args[1]["layer"]
            else:
                layer = call_args[0][1] if len(call_args[0]) > 1 else 0

            assert layer == 0
            assert len(entries) == 2

            # Check Entry 1
            e1 = entries[0]
            assert e1.day == "Monday"
            assert e1.begin_hour == 6
            assert e1.begin_minute == 30

            # Check Entry 2
            e2 = entries[1]
            assert e2.day == "Tuesday"
            assert e2.begin_hour == 17

            # 3. Verify Schedule Enable
            mock_enable_schedule.assert_called_once()

        finally:
            if os.path.exists(backup_path):
                os.unlink(backup_path)
