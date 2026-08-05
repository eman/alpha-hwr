"""
Unit tests for how _read_class10_object() reports a lost BLE link.

A dropped connection must surface as ConnectionError rather than None:
returning None makes a disconnect indistinguishable from "the pump has no
data for this object", which is what produced the misleading
"Setpoint data too short or missing" errors. The link can drop in two
ways - the read simply goes unanswered, or the transport itself raises -
and both are covered here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from alpha_hwr.core.session import Session
from alpha_hwr.core.transport import Transport
from alpha_hwr.exceptions import ConnectionError
from alpha_hwr.services.base import BaseService


def _make_service(
    *, query: AsyncMock, connected: bool
) -> tuple[BaseService, MagicMock]:
    transport = MagicMock(spec=Transport)
    transport.send_command = query
    transport.send_wake_burst = AsyncMock()
    transport.is_connected = MagicMock(return_value=connected)

    session = MagicMock(spec=Session)
    session.is_connected = MagicMock(return_value=True)

    return BaseService(transport, session), transport


@pytest.mark.asyncio
async def test_unanswered_read_while_disconnected_raises() -> None:
    """No response + link down is reported as a disconnect."""
    service, _ = _make_service(
        query=AsyncMock(return_value=None), connected=False
    )

    with pytest.raises(ConnectionError, match="disconnected from BLE"):
        await service._read_class10_object(86, 6)


@pytest.mark.asyncio
async def test_transport_error_while_disconnected_raises() -> None:
    """A transport error on a dropped link is a disconnect, not 'no data'."""
    service, _ = _make_service(
        query=AsyncMock(side_effect=BleakError("device disconnected")),
        connected=False,
    )

    with pytest.raises(ConnectionError, match="disconnected from BLE"):
        await service._read_class10_object(86, 6)


@pytest.mark.asyncio
async def test_transport_error_while_connected_returns_none() -> None:
    """A transport hiccup on a live link still degrades to 'no data'."""
    service, _ = _make_service(
        query=AsyncMock(side_effect=BleakError("write failed")),
        connected=True,
    )

    assert await service._read_class10_object(86, 6) is None


@pytest.mark.asyncio
async def test_unanswered_read_while_connected_returns_none() -> None:
    """An unanswered read on a live link means the object has no data."""
    service, _ = _make_service(
        query=AsyncMock(return_value=None), connected=True
    )

    assert await service._read_class10_object(86, 6) is None
