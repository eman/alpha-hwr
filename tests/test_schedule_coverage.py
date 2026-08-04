from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from bleak.exc import BleakError

from alpha_hwr.client import AlphaHWRClient


class TestScheduleCoverage:
    @pytest_asyncio.fixture
    async def client(self):
        with (
            patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak,
            patch(
                "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
                new_callable=AsyncMock,
            ),
        ):
            # Set up mock BleakClient instance
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock()
            mock_instance.disconnect = AsyncMock()
            mock_instance.start_notify = AsyncMock()
            mock_instance.write_gatt_char = AsyncMock()
            mock_instance.is_connected = True
            mock_bleak.return_value = mock_instance

            # Create client and connect (initializes all components)
            client = AlphaHWRClient("00:00:00:00:00:00")
            await client.connect()

            # Mock the transport's methods to avoid real BLE calls
            assert client.transport is not None
            client.transport.write = AsyncMock()
            client.transport.read_response = AsyncMock(return_value=b"\x00" * 7)
            client.transport.send_with_response = AsyncMock(
                return_value=b"\x00" * 7
            )
            client.transport.query = AsyncMock(return_value=b"\x00" * 7)

            yield client

            # Cleanup
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_get_schedule_enabled_short_data(self, client):
        """Test getting schedule enabled with data that is too short"""
        # Return 5 bytes (needs > 7) produces log warning
        client.transport.query = AsyncMock(
            return_value=bytes([0x01, 0x02, 0x03, 0x04, 0x05])
        )

        result = await client.schedule.get_state()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_schedule_enabled_exception(self, client):
        """Test exception handling in get_schedule_enabled"""
        client.transport.query = AsyncMock(
            side_effect=BleakError("Read failed")
        )

        result = await client.schedule.get_state()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_schedule_layer_exception(self, client):
        """Test exception handling for a specific layer read in get_schedule"""

        def query_side_effect(*args, **kwargs):
            # Create a minimal GENI frame response
            # For schedule reads, we need proper frame structure
            # Return None to simulate read failure
            return None

        client.transport.query = AsyncMock(side_effect=query_side_effect)

        # Should return empty list on failure
        entries = await client.schedule.read_entries()
        assert entries is not None
        assert len(entries) == 0
