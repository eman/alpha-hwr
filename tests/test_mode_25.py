import pytest
from alpha_hwr.constants import ControlMode


@pytest.mark.asyncio
async def test_cycle_time_control_full_cycle(mock_client_with_pump):
    """Test setting and getting cycle time configuration."""
    client = mock_client_with_pump

    # 1. Switch to Mode 25 and set cycle times
    on_min = 7
    off_min = 22

    success = await client.control.set_cycle_time_control(on_min, off_min)
    assert success is True

    # 2. Verify mode changed
    status = await client.control.get_mode()
    assert status.control_mode == ControlMode.DHW_ON_OFF_CONTROL

    # 3. Read back cycle times
    config = await client.control.get_cycle_time_config()
    assert config is not None
    read_on, read_off = config
    assert read_on == on_min
    assert read_off == off_min


@pytest.mark.asyncio
async def test_cycle_time_validation(mock_client_with_pump):
    """Test validation of cycle time parameters."""
    client = mock_client_with_pump

    # Invalid ON time (0)
    success = await client.control.set_cycle_time_control(0, 15)
    assert success is False

    # Invalid OFF time (61)
    success = await client.control.set_cycle_time_control(5, 61)
    assert success is False
