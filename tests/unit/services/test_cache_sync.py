"""
Tests for cache synchronisation and the readiness gate.

The cache exists so that a write carrying fields the caller did not set can
preserve them rather than invent them. These pin down when it is trusted,
when it is dropped, and that one mode's setpoint can never be read as
another's.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alpha_hwr.constants import ControlMode
from alpha_hwr.models import SetpointInfo
from alpha_hwr.services.control import ControlService


def info(
    mode: ControlMode = ControlMode.CONSTANT_SPEED,
    setpoint: float = 1650.0,
    running: bool = True,
) -> SetpointInfo:
    return SetpointInfo(
        control_mode=mode,
        operation_mode=0,
        setpoint=setpoint,
        is_remote=False,
        is_running=running,
    )


@pytest.fixture
def control() -> ControlService:
    service = ControlService(MagicMock(), MagicMock())
    service.get_mode = AsyncMock(return_value=info())  # type: ignore[method-assign]
    service.get_temperature_range = AsyncMock(  # type: ignore[method-assign]
        return_value=(35.0, 38.9, True)
    )
    service.get_cycle_time_config = AsyncMock(return_value=(5, 15))  # type: ignore[method-assign]
    return service


@pytest.mark.asyncio
async def test_a_fresh_service_is_not_trusted(control: ControlService) -> None:
    assert not control.is_cache_valid


@pytest.mark.asyncio
async def test_sync_reads_the_pump_into_the_cache(
    control: ControlService,
) -> None:
    assert await control.sync_cache() is True

    assert control.is_cache_valid
    assert control.cached_setpoint(ControlMode.CONSTANT_SPEED) == 1650.0


@pytest.mark.asyncio
async def test_an_unreadable_control_state_leaves_the_cache_invalid(
    control: ControlService,
) -> None:
    control.get_mode = AsyncMock(return_value=None)  # type: ignore[method-assign]

    assert await control.sync_cache() is False
    assert not control.is_cache_valid


@pytest.mark.asyncio
async def test_an_unreadable_temperature_range_leaves_the_cache_invalid(
    control: ControlService,
) -> None:
    """A range write has to echo the pump's own bounds back."""
    control.get_temperature_range = AsyncMock(return_value=None)  # type: ignore[method-assign]

    assert await control.sync_cache() is False
    assert not control.is_cache_valid


@pytest.mark.asyncio
async def test_an_unreadable_cycle_config_does_not_block_readiness(
    control: ControlService,
) -> None:
    """
    Requiring it would let one short Object 91 payload wedge the client
    permanently: nothing displays it, and every write would be refused.
    """
    control.get_cycle_time_config = AsyncMock(return_value=None)  # type: ignore[method-assign]

    assert await control.sync_cache() is True
    assert control.is_cache_valid


@pytest.mark.asyncio
async def test_setpoints_are_kept_per_mode(control: ControlService) -> None:
    """
    One shared slot leaks a value across modes under different units - a
    4.0 m pressure setpoint resent as a 4.0 RPM speed request.
    """
    control.get_mode = AsyncMock(return_value=info(setpoint=1650.0))  # type: ignore[method-assign]
    await control.sync_cache()

    control.get_mode = AsyncMock(  # type: ignore[method-assign]
        return_value=info(mode=ControlMode.CONSTANT_PRESSURE, setpoint=4.0)
    )
    await control.sync_cache()

    assert control.cached_setpoint(ControlMode.CONSTANT_SPEED) == 1650.0
    assert control.cached_setpoint(ControlMode.CONSTANT_PRESSURE) == 4.0


@pytest.mark.asyncio
async def test_invalidate_drops_everything(control: ControlService) -> None:
    """
    Including the mode. A command issued on one connection must not be
    treated as confirmed by a reading taken on the next.
    """
    await control.sync_cache()
    assert control.is_cache_valid

    control.invalidate_cache()

    assert not control.is_cache_valid
    assert control.cached_setpoint(ControlMode.CONSTANT_SPEED) is None
