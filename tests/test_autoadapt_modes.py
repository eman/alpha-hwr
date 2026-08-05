"""
Tests for AutoAdapt mode control methods.

This module tests the AutoAdapt mode setters including:
- Generic AutoAdapt (Mode 5)
- AutoAdapt Radiator (Mode 13)
- AutoAdapt Underfloor (Mode 14)
- AutoAdapt Combined (Mode 15)
"""

from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError

# Note: mock_client fixture is now provided by conftest.py as mock_client_simple


@pytest.mark.asyncio
async def test_set_autoadapt_mode5(mock_client_simple):
    """
    Generic AutoAdapt has no wire byte, so asking for it is an error.

    It used to fall through to the mode map's default - Constant Speed -
    and report success, so the pump ended up in a different mode from the
    one requested with nothing to indicate it.
    """
    with pytest.raises(ValueError, match="mode 5 is not supported"):
        await mock_client_simple.control.set_autoadapt(1.5)


@pytest.mark.asyncio
async def test_set_autoadapt_validation_failure(mock_client_simple):
    """Test AutoAdapt with validation failure (out of range value)."""
    # Try setting a value outside the valid range (0.5-10.0 m)
    result = await mock_client_simple.control.set_autoadapt(15.0)

    # Should fail validation and return False
    assert result is False


@pytest.mark.asyncio
async def test_set_autoadapt_mode_switch_failure(mock_client_simple):
    """
    The unsupported-mode error is raised before any transport work.

    It is a property of the request, not of the link, so it does not
    depend on the transport failing - and it must not be reported as a
    transport failure either.
    """
    mock_client_simple.transport.query = AsyncMock(
        side_effect=BleakError("Transport error")
    )
    mock_client_simple.transport.send_with_response = AsyncMock(
        side_effect=BleakError("Transport error")
    )

    with pytest.raises(ValueError, match="mode 5 is not supported"):
        await mock_client_simple.control.set_autoadapt(1.5)


@pytest.mark.asyncio
async def test_set_autoadapt_radiator(mock_client_simple):
    """Test AutoAdapt Radiator mode (Mode 13) setter."""
    result = await mock_client_simple.control.set_autoadapt_radiator(3.0)

    # Should have made transport calls
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count > 0
    assert result is True


@pytest.mark.asyncio
async def test_set_autoadapt_underfloor(mock_client_simple):
    """Test AutoAdapt Underfloor mode (Mode 14) setter."""
    result = await mock_client_simple.control.set_autoadapt_underfloor(2.5)

    # Should have made transport calls
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count > 0
    assert result is True


@pytest.mark.asyncio
async def test_set_autoadapt_combined(mock_client_simple):
    """Test AutoAdapt Combined mode (Mode 15) setter."""
    result = await mock_client_simple.control.set_autoadapt_combined(3.5)

    # Should have made transport calls
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count > 0
    assert result is True


@pytest.mark.asyncio
async def test_autoadapt_unit_conversion(mock_client_simple):
    """The addressable AutoAdapt variants accept meters as input."""
    result = await mock_client_simple.control.set_autoadapt_radiator(1.0)

    assert result is True
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count > 0
