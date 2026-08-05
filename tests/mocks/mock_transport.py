"""
Mock BLE transport for testing.

This module provides a transport adapter that connects the AlphaHWRClient
to a MockPump without requiring actual BLE hardware.
"""

import asyncio
from collections.abc import Callable

from .mock_pump import MockPump


class MockTransport:
    """
    Mock transport that bridges client and mock pump.

    This adapter makes a MockPump behave like a real BLE transport,
    allowing full end-to-end testing without hardware.

    Example:
        >>> pump = MockPump()
        >>> transport = MockTransport(pump)
        >>>
        >>> # Use with client
        >>> client = AlphaHWRClient("MOCK")
        >>> client.transport = transport
        >>> await client.connect()
    """

    def __init__(self, pump: MockPump):
        """
        Initialize mock transport.

        Args:
            pump: MockPump instance to use as backend
        """
        self.pump = pump
        self._notification_callback: Callable[[bytes], None] | None = None
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self._streaming = False

    async def write(self, data: bytes) -> None:
        """
        Write command to pump.

        Args:
            data: Command bytes to send
        """
        if not self.pump.state.connected:
            raise ConnectionError("Not connected to pump")

        # Send to pump and get response
        response = await self.pump.send_command(data)

        # Queue response for reading
        await self._response_queue.put(response)

        # Also trigger notification callback if set
        if self._notification_callback:
            self._notification_callback(response)

    async def read_response(self, timeout: float = 2.0) -> bytes:
        """
        Read response from pump.

        Args:
            timeout: Timeout in seconds

        Returns:
            Response bytes

        Raises:
            TimeoutError: If no response within timeout
        """
        try:
            response = await asyncio.wait_for(
                self._response_queue.get(), timeout=timeout
            )
            return response
        except TimeoutError:
            raise TimeoutError(f"No response within {timeout}s")

    async def send_with_response(
        self, data: bytes, timeout: float = 2.0
    ) -> bytes:
        """
        Send command and wait for response.

        Args:
            data: Command bytes
            timeout: Response timeout

        Returns:
            Response bytes
        """
        await self.write(data)
        return await self.read_response(timeout)

    async def query(
        self,
        frame: bytes,
        match_func: Callable[[bytes], bool] | None = None,
        timeout: float = 3.0,
    ) -> bytes:
        """
        Send query and wait for matching response.

        Args:
            frame: Command frame
            match_func: Optional function to validate response
            timeout: Response timeout

        Returns:
            Matching response bytes
        """
        response = await self.send_with_response(frame, timeout)

        if match_func and not match_func(response):
            raise ValueError("Response did not match criteria")

        return response

    def set_notification_callback(
        self, callback: Callable[[bytes], None]
    ) -> None:
        """
        Set callback for notifications.

        Args:
            callback: Function to call when notifications arrive
        """
        self._notification_callback = callback
        self.pump.set_notification_callback(callback)

    async def start_notifications(self) -> None:
        """Start notification stream from pump."""
        if not self._streaming:
            self._streaming = True
            asyncio.create_task(self._notification_loop())

    async def stop_notifications(self) -> None:
        """Stop notification stream."""
        self._streaming = False

    async def _notification_loop(self) -> None:
        """Background task that generates periodic notifications."""
        while self._streaming and self.pump.state.connected:
            if self._notification_callback:
                # Generate motor state notification
                motor_data = self.pump._build_motor_state_response()
                self._notification_callback(motor_data)

                await asyncio.sleep(0.01)

                # Generate flow/pressure notification
                flow_data = self.pump._build_flow_pressure_response()
                self._notification_callback(flow_data)

                await asyncio.sleep(0.01)


class MockBleakClient:
    """
    Mock BleakClient for complete BLE stack simulation.

    This provides a drop-in replacement for bleak.BleakClient,
    allowing tests to run without patching.

    Example:
        >>> # In test
        >>> with patch('alpha_hwr.client.BleakClient', MockBleakClient):
        >>>     client = AlphaHWRClient("MOCK")
        >>>     await client.connect()
    """

    def __init__(
        self,
        address: str,
        adapter: str | None = None,
        disconnected_callback: Callable[[object], None] | None = None,
        **kwargs: object,
    ):
        """
        Initialize mock Bleak client.

        Args:
            address: Device address (can be "MOCK" for testing)
            adapter: BLE adapter (ignored in mock)
            disconnected_callback: Fired on disconnect, like bleak's.
            **kwargs: Backend options (e.g. ``bluez=``), ignored in mock.
        """
        self.address = address
        self.adapter = adapter
        self.pump = MockPump()
        self._connected = False
        self._notify_callback: Callable | None = None
        self._notify_task: asyncio.Task | None = None
        self._disconnected_callback = disconnected_callback

    async def connect(self, timeout: float = 60.0) -> bool:
        """
        Connect to mock pump.

        Args:
            timeout: Connection timeout (ignored in mock)
        """
        await self.pump.connect()
        self._connected = True
        return True

    async def disconnect(self) -> bool:
        """Disconnect from mock pump."""
        was_connected = self._connected
        self._connected = False

        # Cancel notification task if running
        if self._notify_task and not self._notify_task.done():
            self._notify_task.cancel()
            try:
                await self._notify_task
            except asyncio.CancelledError:
                pass

        await self.pump.disconnect()

        # Bleak fires this on every drop, deliberate or not.
        if was_connected and self._disconnected_callback:
            self._disconnected_callback(self)
        return True

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    async def write_gatt_char(
        self, char_uuid: str, data: bytes, response: bool = False
    ) -> None:
        """
        Write to GATT characteristic.

        Args:
            char_uuid: Characteristic UUID
            data: Data to write
            response: Whether to wait for BLE write ACK (not GENI response)
        """
        if not self._connected:
            raise ConnectionError("Not connected")

        # Send to pump
        pump_response = await self.pump.send_command(data)

        # Trigger notification callback if set
        # Note: This simulates GENI protocol where responses always come via notifications,
        # regardless of BLE write ACK setting
        if self._notify_callback:
            # Call with (characteristic, data) signature - callback is sync, not async
            self._notify_callback(char_uuid, pump_response)

    async def start_notify(self, char_uuid: str, callback: Callable) -> None:
        """
        Start notifications on characteristic.

        Args:
            char_uuid: Characteristic UUID
            callback: Callback function (characteristic, data)
        """
        self._notify_callback = callback
        # Note: We do NOT start a background task here anymore.
        # Tests that need streaming should rely on polling or explicitly
        # trigger notifications from the MockPump.

    async def stop_notify(self, char_uuid: str) -> None:
        """
        Stop notifications.

        Args:
            char_uuid: Characteristic UUID
        """
        self._notify_callback = None


def create_mock_client_with_pump() -> tuple:
    """
    Create a client with mock pump backend.

    Convenience function for tests.

    Returns:
        Tuple of (AlphaHWRClient, MockPump)

    Example:
        >>> client, pump = create_mock_client_with_pump()
        >>> await client.connect()
        >>> await client.control.start()
        >>> assert pump.state.running
    """
    from alpha_hwr.client import AlphaHWRClient

    pump = MockPump()
    client = AlphaHWRClient("MOCK")

    # Replace transport with mock
    # Note: This requires client to be flexible about transport injection
    # or we need to patch during connect()

    return client, pump
