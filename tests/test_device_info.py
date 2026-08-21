"""Tests for device info reading operations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wire import frame

from alpha_hwr.client import AlphaHWRClient


# Note: client fixture is now provided by conftest.py as mock_client_simple
@pytest.mark.asyncio
async def test_read_device_info_from_advertisement():
    """Test reading device info from BLE advertisement data."""
    # Mock BleakScanner.discover directly
    with patch("bleak.BleakScanner.discover") as mock_discover:
        # Create mock device and advertisement
        mock_device = MagicMock()
        mock_device.address = "AA:BB:CC:DD:EE:FF"

        mock_adv = MagicMock()
        # Service data with product info at bytes 3, 4, 5
        # Format: [header bytes...] [product_family] [product_type] [product_version]
        mock_adv.service_data = {
            "0000fe5d-0000-1000-8000-00805f9b34fb": bytes(
                [0x00, 0x00, 0x00, 52, 7, 2]
            )
        }

        # Mock discover to return a dict mapping address to (device, adv) tuple
        mock_discover.return_value = {
            "AA:BB:CC:DD:EE:FF": (mock_device, mock_adv)
        }

        # Create client and read device info without connecting
        client = AlphaHWRClient("AA:BB:CC:DD:EE:FF")

        # The device_info service is not available before connection,
        # so we need to access the internal method or handle differently
        # For now, this test validates the BLE advertisement parsing logic
        # which happens during client initialization

        # Mock the cached product info that would be set during scan
        client._cached_product_info = {
            "product_family": 52,
            "product_type": 7,
            "product_version": 2,
        }

    # After connection, device_info service will use cached data
    with (
        patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak,
        patch(
            "alpha_hwr.client.AlphaHWRClient._scan_advertisement_data",
            new_callable=AsyncMock,
        ),
    ):
        mock_instance = AsyncMock()
        mock_instance.is_connected = True
        mock_bleak.return_value = mock_instance

        await client.connect()
        assert client.device_info is not None
        device_info = await client.device_info.read_info()

        assert device_info is not None
        assert device_info.product_family == 52  # ALPHA
        assert device_info.product_type == 7  # HWR
        assert device_info.product_version == 2


@pytest.mark.asyncio
async def test_read_device_info_with_class7_strings(mock_client_simple):
    """Test reading device info with Class 7 strings."""

    # Class 7 replies as an ALPHA HWR actually sends them, recorded
    # 2026-08-20. The strings this fixture used to carry were the
    # *truncated* ones - "0000479" and "2601618V04.02.01.02539" - because
    # they were copied out of this client's own output while it was
    # reading from offset 7 and dropping the first character. So the
    # fixture agreed with the bug, and the "1" the serial assertion
    # expected was the character the reader had thrown away.
    STRINGS = {
        1: "ALPHA HWR",
        9: "10000479",
        50: "92601618V04.02.01.02539",
        52: "92601617V01.03.00.00469",
        58: "92811431V06.00.01.00001",
    }

    async def mock_query(request, match_func=None, timeout=3.0):
        # Request: [STX][LEN][DST][SRC][0x07][head][string_id]
        if len(request) < 7:
            return None
        value = STRINGS.get(request[6])
        if value is None:
            return None
        return frame(0x07, value.encode() + b"\x00")

    async def mock_send_command(request, command, timeout=3.0):
        return await mock_query(request)

    mock_client_simple.transport.query = AsyncMock(side_effect=mock_query)
    mock_client_simple.transport.send_command = AsyncMock(
        side_effect=mock_send_command
    )

    device_info = await mock_client_simple.device_info.read_info()

    assert device_info is not None
    # The serial arrives whole; nothing is prepended to it.
    assert device_info.serial_number == "10000479"
    assert device_info.software_version == "92601618V04.02.01.02539"
    assert device_info.hardware_version == "92601617V01.03.00.00469"
    assert device_info.ble_version == "92811431V06.00.01.00001"


@pytest.mark.asyncio
async def test_read_device_info_uses_cached_product_data(mock_client_simple):
    """Test that device info uses cached product data from advertisement."""

    # Set cached product info (normally set during BLE scan)
    mock_client_simple._cached_product_info = {
        "product_family": 52,
        "product_type": 7,
        "product_version": 2,
    }
    # Also update the service's cached_product_info since service was already initialized
    mock_client_simple.device_info.cached_product_info = (
        mock_client_simple._cached_product_info
    )

    # Mock minimal Class 7 responses
    async def mock_query(frame, match_func=None, timeout=3.0):
        string_id = frame[6] if len(frame) > 6 else 0
        if string_id == 9:  # Serial number
            return (
                b"\x27\x0e\xe7\xf8\x07\x01\x09" + b"0000479\x00" + b"\x00\x00"
            )
        return None

    mock_client_simple.transport.query = AsyncMock(side_effect=mock_query)

    device_info = await mock_client_simple.device_info.read_info()

    assert device_info is not None
    # Should use cached product info
    assert device_info.product_family == 52
    assert device_info.product_type == 7
    assert device_info.product_version == 2
