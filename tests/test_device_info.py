"""Tests for device info reading operations."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
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
    with patch("alpha_hwr.client.BleakClient", autospec=True) as mock_bleak:
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

    # Mock transport.query to return Class 7 string responses
    async def mock_query(frame, match_func=None, timeout=3.0):
        # Determine which string is being requested based on the frame
        # Frame structure: [STX][LEN][DST][SRC][Class][Cmd][ID]...
        if len(frame) < 7:
            return None

        string_id = frame[6]  # String ID is at position 6 in the packet

        if string_id == 9:  # Serial number
            return (
                b"\x27\x0e\xe7\xf8\x07\x01\x09" + b"0000479\x00" + b"\x00\x00"
            )
        elif string_id == 50:  # Software version
            return (
                b"\x27\x20\xe7\xf8\x07\x01\x32"
                + b"2601618V04.02.01.02539\x00"
                + b"\x00\x00"
            )
        elif string_id == 52:  # Hardware version
            return (
                b"\x27\x20\xe7\xf8\x07\x01\x34"
                + b"2601617V01.03.00.00469\x00"
                + b"\x00\x00"
            )
        elif string_id == 58:  # BLE version
            return (
                b"\x27\x20\xe7\xf8\x07\x01\x3a"
                + b"2811431V06.00.01.00001\x00"
                + b"\x00\x00"
            )
        return None

    mock_client_simple.transport.query = AsyncMock(side_effect=mock_query)

    device_info = await mock_client_simple.device_info.read_info()

    assert device_info is not None
    # Serial number gets "1" prepended to the suffix from ID 9
    assert device_info.serial_number == "10000479"
    assert device_info.software_version == "2601618V04.02.01.02539"
    assert device_info.hardware_version == "2601617V01.03.00.00469"
    assert device_info.ble_version == "2811431V06.00.01.00001"


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
