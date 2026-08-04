from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from alpha_hwr.client import AlphaHWRClient


def _overview_frame(*, enabled: bool) -> bytes:
    """Build a schedule-overview response (Object 84, Sub 1).

    Byte 17 of the frame is the enabled flag the service verifies
    against after a write.
    """
    return bytes(
        [
            0x27,
            0x11,
            0xF8,
            0xE7,
            0x0A,
            0x43,
            0x54,
            0x00,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,  # Header
            0x00,
            0x00,
            0x00,
            0x00,  # Capabilities
            0x01 if enabled else 0x00,  # Enabled flag
            0x00,  # DefaultAction
            0x00,
            0x00,
            0x00,
            0x00,  # BaseSetpoint
            0x00,
            0x00,
        ]
    )


class TestScheduleProtocol:
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
    async def test_get_schedule_enabled(self, client):
        """Verify get_schedule_enabled calls work correctly"""
        # Mock response: Full GENI frame with enabled flag
        # Frame structure: [STX][LEN][DST][SRC][Class][OpSpec][ObjH][ObjL][SubH][SubL][DATA...][CRC_H][CRC_L]
        # _read_class10_object extracts bytes 10:-2 as payload
        # For Object 84, Sub 1, we need the enabled byte at position 7 in the payload
        # Payload needs: [Header(3)][Capabilities(4)][Enabled(1)][DefaultAction(1)][BaseSetpoint(4)] = 13 bytes
        frame_enabled = bytearray(
            [
                0x27,  # STX
                0x11,  # LEN = 1 (DST) + 1 (SRC) + 1 (Class) + 1 (OpSpec) + 1 (ObjH) + 1 (ObjL) + 1 (SubH) + 1 (SubL) + 13 (DATA) = 21 bytes
                0xF8,  # DST
                0xE7,  # SRC
                0x0A,  # Class 10
                0x43,  # OpSpec (response)
                0x54,  # Object 84
                0x00,
                0x00,
                0x01,  # Sub-ID = 1 (3 bytes: ObjL, SubH, SubL)
                # DATA (13 bytes total): [Header(3)][Capabilities(4)][Enabled(1)][DefaultAction(1)][BaseSetpoint(4)]
                0x00,
                0x00,
                0x00,  # Header (3 bytes)
                0x00,
                0x00,
                0x00,
                0x00,  # Capabilities (4 bytes)
                0x01,  # Enabled flag at byte 7 of payload
                0x00,  # DefaultAction
                0x00,
                0x00,
                0x00,
                0x00,  # BaseSetpoint (4 bytes)
                0x00,
                0x00,  # CRC
            ]
        )
        client.transport.query = AsyncMock(return_value=bytes(frame_enabled))

        result = await client.schedule.get_state()
        assert result is True

        # Test disabled
        frame_disabled = bytearray(
            [
                0x27,
                0x11,
                0xF8,
                0xE7,
                0x0A,
                0x43,
                0x54,
                0x00,
                0x00,
                0x01,
                0x00,
                0x00,
                0x00,  # Header
                0x00,
                0x00,
                0x00,
                0x00,  # Capabilities
                0x00,  # Enabled flag = 0x00 (disabled)
                0x00,  # DefaultAction
                0x00,
                0x00,
                0x00,
                0x00,  # BaseSetpoint
                0x00,
                0x00,
            ]
        )
        client.transport.query = AsyncMock(return_value=bytes(frame_disabled))
        result = await client.schedule.get_state()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_schedule_parsing(self, client):
        """Verify get_schedule parses the raw bytes correctly"""

        # Mock multiple query responses for different sub-IDs
        def query_side_effect(*args, **kwargs):
            # Build frame for schedule data (Object 84, Sub 1000)
            # Payload: [Header: 00 00 2A] + [7 days * 6 bytes each] = 45 bytes
            # Frame: [STX][LEN][DST][SRC][Class][OpSpec][ObjH][ObjL][SubH][SubL][PAYLOAD][CRC]
            # LEN = DST + SRC + Class + OpSpec + ObjH + ObjL + SubH + SubL + payload + CRC = 1+1+1+1+1+1+1+1+45+2 = 55
            frame = bytearray(
                [
                    0x27,  # STX
                    0x37,  # LEN = 55 (0x37)
                    0xF8,
                    0xE7,  # DST, SRC
                    0x0A,
                    0x43,  # Class, OpSpec
                    0x00,
                    0x54,  # Object 84 (2 bytes: ObjH, ObjL)
                    0x03,
                    0xE8,  # Sub-ID = 1000 (2 bytes: SubH, SubL)
                    # Payload (45 bytes): Header + schedule entries
                    0x00,
                    0x00,
                    0x2A,  # Header
                    # Monday: Enabled, Run, 06:00 - 09:00
                    0x01,
                    0x02,
                    0x06,
                    0x00,
                    0x09,
                    0x00,
                    # Other days: Disabled
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Tuesday
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Wednesday
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Thursday
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Friday
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Saturday
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Sunday
                    0x00,
                    0x00,  # CRC
                ]
            )
            return bytes(frame)

        client.transport.query = AsyncMock(side_effect=query_side_effect)

        # Read only layer 0 to test parsing logic
        entries = await client.schedule.read_entries(layer=0)

        assert entries is not None

        # New format returns ONLY active entries
        # We expect exactly 1 entry (Monday)
        assert len(entries) == 1

        # Check Monday
        mon_entry = entries[0]
        assert mon_entry.day == "Monday"
        assert mon_entry.enabled is True
        assert mon_entry.action == 2  # Run
        assert mon_entry.begin_time == "06:00"
        assert mon_entry.end_time == "09:00"

    @pytest.mark.asyncio
    async def test_get_schedule_short_data(self, client):
        """Verify handling of incomplete data"""

        # Return a short frame (only header, no schedule data)
        frame = bytearray(
            [
                0x27,
                0x0C,
                0xF8,
                0xE7,
                0x0A,
                0x43,
                0x54,
                0x03,
                0xE8,
                0x00,
                0x00,
                0x2A,  # Just header
                0x00,
                0x00,
            ]
        )
        client.transport.query = AsyncMock(return_value=bytes(frame))

        # If all layers fail/short, it returns empty list, not None
        entries = await client.schedule.read_entries()
        assert entries is not None
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_set_schedule_enabled_implemented(self, client):
        """Test that set_schedule_enabled (enable/disable) works"""
        # Mock responses: first the read, then the write confirmation
        responses = [
            # Read current overview (Object 84, Sub 1)
            bytes(
                [
                    0x27,
                    0x11,
                    0xF8,
                    0xE7,
                    0x0A,
                    0x43,
                    0x54,
                    0x00,
                    0x00,
                    0x01,
                    0x00,
                    0x00,
                    0x00,  # Header
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Capabilities
                    0x00,  # Currently disabled
                    0x00,  # DefaultAction
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # BaseSetpoint
                    0x00,
                    0x00,
                ]
            ),
            # Write response (success)
            bytes([0x27, 0x06, 0xF8, 0xE7, 0x0A, 0x83, 0x00, 0x00]),
            # Verification read-back: now enabled
            _overview_frame(enabled=True),
        ]
        client.transport.query = AsyncMock(side_effect=responses)

        # Test enable
        result = await client.schedule.enable()
        assert result is True

        # Test disable - reset responses
        responses = [
            # Read current overview (enabled)
            bytes(
                [
                    0x27,
                    0x11,
                    0xF8,
                    0xE7,
                    0x0A,
                    0x43,
                    0x54,
                    0x00,
                    0x00,
                    0x01,
                    0x00,
                    0x00,
                    0x00,  # Header
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # Capabilities
                    0x01,  # Currently enabled
                    0x00,  # DefaultAction
                    0x00,
                    0x00,
                    0x00,
                    0x00,  # BaseSetpoint
                    0x00,
                    0x00,
                ]
            ),
            # Write response (success)
            bytes([0x27, 0x06, 0xF8, 0xE7, 0x0A, 0x83, 0x00, 0x00]),
            # Verification read-back: now disabled
            _overview_frame(enabled=False),
        ]
        client.transport.query = AsyncMock(side_effect=responses)

        result = await client.schedule.disable()
        assert result is True
