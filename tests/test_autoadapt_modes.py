"""
Tests for AutoAdapt mode control methods.

This module tests the AutoAdapt mode setters including:
- Generic AutoAdapt (Mode 5)
- AutoAdapt Radiator (Mode 13)
- AutoAdapt Underfloor (Mode 14)
- AutoAdapt Combined (Mode 15)
"""

import pytest
from unittest.mock import AsyncMock

# Note: mock_client fixture is now provided by conftest.py as mock_client_simple


@pytest.mark.asyncio
async def test_set_autoadapt_mode5(mock_client_simple):
    """Test generic AutoAdapt mode (Mode 5) setter."""
    # Test successful call
    result = await mock_client_simple.control.set_autoadapt(1.5)

    # Should have made transport calls
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count > 0
    assert result is True


@pytest.mark.asyncio
async def test_set_autoadapt_validation_failure(mock_client_simple):
    """Test AutoAdapt with validation failure (out of range value)."""
    # Try setting a value outside the valid range (0.5-10.0 m)
    result = await mock_client_simple.control.set_autoadapt(15.0)

    # Should fail validation and return False
    assert result is False


@pytest.mark.asyncio
async def test_set_autoadapt_mode_switch_failure(mock_client_simple):
    """Test AutoAdapt when transport fails."""
    # Mock transport failure
    mock_client_simple.transport.query = AsyncMock(
        side_effect=Exception("Transport error")
    )
    mock_client_simple.transport.send_with_response = AsyncMock(
        side_effect=Exception("Transport error")
    )

    result = await mock_client_simple.control.set_autoadapt(1.5)

    # Should fail
    assert result is False


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
    """Test that AutoAdapt methods accept meters as input."""
    # Test with 1.0 meter (should be accepted - valid range is 0.5-10.0m)
    result = await mock_client_simple.control.set_autoadapt(1.0)

    # Should succeed
    assert result is True

    # Should have made transport calls
    call_count = (
        mock_client_simple.transport.query.call_count
        + mock_client_simple.transport.send_with_response.call_count
        + mock_client_simple.transport.write.call_count
    )
    assert call_count > 0
