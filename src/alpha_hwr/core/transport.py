"""
BLE Transport layer for GENI protocol communication.

This module handles low-level BLE packet transport including:
- Notification handling and routing
- Request/response transactions with locking
- Response queue management
- Keep-alive operations

The transport layer sits between the BLE client (bleak) and the
protocol layer, providing a clean abstraction for sending/receiving
GENI protocol packets.
"""

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ..constants import GENI_CHAR_UUID
from ..exceptions import READ_ERRORS
from ..protocol.matcher import Command as MatcherCommand
from ..protocol.matcher import matches as matcher_matches

logger = logging.getLogger(__name__)

#: Largest payload the pump accepts in a single GATT write. Longer GENI
#: frames are split across this many bytes at a time; the pump reassembles
#: them from the length field in byte 1.
BLE_MTU_LIMIT = 20

#: Gap between consecutive BLE writes, whether they are chunks of one frame
#: or separate commands. The pump drops or ignores traffic that arrives
#: faster than this.
SEND_PACING = 0.05


class Transport:
    """
    BLE transport for GENI protocol packets.

    Manages low-level BLE communication including notification handling,
    transaction locking, and response queuing. Provides a clean interface
    for higher-level protocol operations.

    Architecture
    ------------
    ```
    ┌─────────────────────────────────┐
    │   Protocol Layer / Services     │
    │  (sends/receives GENI packets)  │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────┐
    │       Transport Layer           │
    │  - Transaction locking          │
    │  - Notification routing         │
    │  - Response queuing             │
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────┐
    │      BleakClient (bleak)        │
    │  - BLE GATT operations          │
    │  - Connection management        │
    └─────────────────────────────────┘
    ```

    Transaction Locking
    -------------------
    GENI protocol requires sequential command execution. The transport
    ensures only one command is in-flight at a time using an async lock.

    This prevents:
    - Response confusion (which response belongs to which request)
    - Command queue overflow on pump
    - Race conditions in state updates

    Response Handling
    -----------------
    BLE notifications arrive asynchronously. The transport queues them
    for processing:

    1. Notification arrives via BLE callback
    2. Transport adds to response queue
    3. Protocol layer retrieves from queue
    4. Custom handlers can intercept notifications

    Attributes
    ----------
    client : BleakClient
        Connected BLE client
    transaction_lock : asyncio.Lock
        Ensures sequential command execution
    response_queue : asyncio.Queue
        Queue of received notifications

    Examples
    --------
    >>> from bleak import BleakClient
    >>> client = BleakClient("device_address")
    >>> await client.connect()
    >>>
    >>> transport = Transport(client)
    >>> await transport.start_notifications(my_handler)
    >>>
    >>> # Send a packet with transaction lock
    >>> async with transport.transaction():
    ...     await transport.write(packet_bytes)
    ...     response = await transport.wait_for_response(timeout=3.0)

    Notes for Reimplementation
    --------------------------
    Key concepts to preserve:

    1. **Transaction Lock**: Use mutex/semaphore to serialize commands
    2. **Response Queue**: Use thread-safe queue for notifications
    3. **Notification Handler**: BLE callback pushes to queue
    4. **Timeout Handling**: All operations should timeout eventually
    5. **Keep-Alive**: Periodic packet to maintain connection
    """

    def __init__(self, client: BleakClient):
        """
        Initialize transport with BLE client.

        Parameters
        ----------
        client : BleakClient
            Connected bleak BLE client
        """
        self.client = client

        # Transaction management
        self._transaction_lock = asyncio.Lock()

        # Response handling
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._response_buffer = bytearray()

        # Custom notification handlers (for telemetry streaming)
        self._custom_handlers: list[Callable[[bytes], None]] = []

        # Callbacks fired when the link drops, from bleak's own
        # disconnected_callback rather than from a failed read. Until this
        # existed, a drop was only noticed the next time something tried to
        # talk to the pump.
        self._disconnect_handlers: list[Callable[[], None]] = []

        # Notification state tracking
        self._notifications_started = False

        # Keep-alive task
        self._keep_alive_task: asyncio.Task | None = None

        # Send pacing: event-loop timestamp of the last BLE write, used to
        # keep at least SEND_PACING between every write on the link -
        # between chunks of one frame and between separate commands alike.
        self._last_write: float | None = None

        logger.debug("Transport initialized")

    async def _pace(self) -> None:
        """Wait out the remainder of the inter-write gap, if any."""
        if self._last_write is None:
            return
        elapsed = asyncio.get_event_loop().time() - self._last_write
        if elapsed < SEND_PACING:
            await asyncio.sleep(SEND_PACING - elapsed)

    async def start_notifications(
        self, handler: Callable[[bytes], None] | None = None
    ) -> None:
        """
        Start BLE notifications on GENI characteristic.

        Registers the internal notification handler which queues all
        incoming packets. Optional custom handler is called after queuing.

        Parameters
        ----------
        handler : Callable[[bytes], None] | None
            Optional custom handler called for each notification.
            Signature: handler(data)

        Examples
        --------
        >>> async def my_handler(data):
        ...     print(f"Received {len(data)} bytes")
        >>> await transport.start_notifications(my_handler)

        Notes
        -----
        - Handler is called from BLE thread, keep it fast
        - Don't block in handler - queue work if needed
        - Exceptions in handler are logged but don't break notifications
        - Can be called multiple times to register additional handlers
        """
        if handler:
            self._custom_handlers.append(handler)
            logger.debug("Custom notification handler registered")

        # Only start notifications once
        if not self._notifications_started:
            await self.client.start_notify(
                GENI_CHAR_UUID, self._notification_callback
            )
            self._notifications_started = True
            logger.info(f"Notifications started on {GENI_CHAR_UUID}")
        else:
            logger.debug("Notifications already started, handler added to list")

    async def stop_notifications(self) -> None:
        """Stop BLE notifications."""
        try:
            if self._notifications_started:
                await self.client.stop_notify(GENI_CHAR_UUID)
                self._notifications_started = False
                logger.info("Notifications stopped")
        except READ_ERRORS as e:
            logger.debug(f"Error stopping notifications: {e}")

    def _notification_callback(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """
        Internal BLE notification callback.

        Called by bleak when notification arrives. Handles packet fragmentation,
        queues complete packets, and calls custom handlers.

        Parameters
        ----------
        characteristic : BleakGATTCharacteristic
            BLE characteristic that sent the notification
        data : bytearray
            Raw notification data (GENI packet fragment or complete packet)

        Notes
        -----
        This runs in BLE event loop context. Keep processing minimal.

        GENI packets can be fragmented by BLE MTU limits (20 bytes).
        We accumulate fragments until we have a complete packet:
        - If data[0] is 0x24 or 0x27 (frame start), start new packet
        - Otherwise, append to current buffer
        - Check if packet complete: len(buffer) >= buffer[1] + 4
        - Only queue complete packets
        """
        logger.debug(
            f"BLE notification received: {len(data)} bytes - {data.hex()}"
        )

        # Handle packet fragmentation
        # Frame start bytes: 0x24 (response) or 0x27 (request/echo)
        if len(data) > 0 and data[0] in (0x24, 0x27):
            # New packet starting
            self._response_buffer = bytearray(data)
        else:
            # Continuation of existing packet
            self._response_buffer.extend(data)

        # Check if we have a complete packet
        if len(self._response_buffer) >= 2:
            expected_len = (
                self._response_buffer[1] + 4
            )  # Length field + start + len + CRC(2)
            if len(self._response_buffer) >= expected_len:
                # Packet complete!
                full_packet = bytes(self._response_buffer)
                logger.debug(f"Complete packet assembled: {full_packet.hex()}")

                # Queue for protocol layer processing
                try:
                    self._response_queue.put_nowait(full_packet)
                except asyncio.QueueFull:
                    logger.warning("Response queue full, dropping packet")

                # Call custom handlers (e.g., for telemetry updates)
                for handler in self._custom_handlers:
                    try:
                        handler(full_packet)
                    except Exception as e:  # noqa: BLE001
                        # Caller-supplied handler: isolate it so one bad
                        # handler cannot kill the notification callback.
                        logger.error(f"Error in custom handler: {e}")

                # Clear buffer for next packet
                self._response_buffer.clear()
            else:
                logger.debug(
                    f"Partial packet: have {len(self._response_buffer)}, need {expected_len}"
                )

        # Safety: Clear buffer if it grows too large (corrupted data)
        if len(self._response_buffer) > 256:
            logger.warning("Response buffer overflow, clearing")
            self._response_buffer.clear()

    async def write(self, data: bytes, response: bool = False) -> None:
        """
        Write data to GENI characteristic.

        Parameters
        ----------
        data : bytes
            GENI protocol packet to send
        response : bool, default=False
            Whether to wait for BLE write response.
            False is faster but less reliable.

        Raises
        ------
        Exception
            If BLE write fails

        Notes
        -----
        Packets exceeding the 20-byte BLE MTU are split into as many
        chunks as it takes, paced ``SEND_PACING`` apart. An earlier
        revision split into exactly two chunks, which silently truncated
        anything over 40 bytes - including the 59-byte schedule-layer
        write, whose second chunk still exceeded the MTU.

        Examples
        --------
        >>> packet = protocol.build_command(...)
        >>> await transport.write(packet)
        """
        chunks = [
            data[i : i + BLE_MTU_LIMIT]
            for i in range(0, len(data), BLE_MTU_LIMIT)
        ] or [data]

        for chunk in chunks:
            await self._pace()
            await self.client.write_gatt_char(
                GENI_CHAR_UUID, chunk, response=response
            )
            self._last_write = asyncio.get_event_loop().time()

        if len(chunks) > 1:
            sizes = " + ".join(str(len(c)) for c in chunks)
            logger.debug(
                f"Wrote {len(data)} bytes as {len(chunks)} chunks "
                f"({sizes}, response={response})"
            )
        else:
            logger.debug(f"Wrote {len(data)} bytes (response={response})")

    async def read_response(self, timeout: float = 3.0) -> bytes | None:
        """
        Read next response from queue.

        Waits for a notification to arrive and returns it.

        Parameters
        ----------
        timeout : float, default=3.0
            Maximum seconds to wait for response

        Returns
        -------
        bytes | None
            Response packet, or None if timeout

        Examples
        --------
        >>> await transport.write(request_packet)
        >>> response = await transport.read_response(timeout=5.0)
        >>> if response:
        ...     data = protocol.parse(response)
        """
        try:
            response = await asyncio.wait_for(
                self._response_queue.get(), timeout=timeout
            )
            logger.debug(f"Read response: {len(response)} bytes")
            return response
        except TimeoutError:
            logger.debug(f"Response timeout after {timeout}s")
            return None

    def transaction(self) -> asyncio.Lock:
        """
        Get transaction lock for sequential command execution.

        Use as async context manager to ensure commands are sent one at a time.

        Returns
        -------
        asyncio.Lock
            Transaction lock

        Examples
        --------
        >>> async with transport.transaction():
        ...     await transport.write(command1)
        ...     response1 = await transport.read_response()
        ...     # Next command waits for this to complete

        Notes
        -----
        Without this lock, concurrent commands can:
        - Confuse response matching
        - Overflow pump command queue
        - Cause undefined behavior
        """
        return self._transaction_lock

    async def send_with_response(
        self, packet: bytes, timeout: float = 3.0
    ) -> bytes | None:
        """
        Send packet and wait for response (atomic transaction).

        Convenience method that combines write + read_response with
        transaction lock.

        Parameters
        ----------
        packet : bytes
            GENI packet to send
        timeout : float, default=3.0
            Response timeout in seconds

        Returns
        -------
        bytes | None
            Response packet, or None if timeout

        Examples
        --------
        >>> command = protocol.build_read_request(register)
        >>> response = await transport.send_with_response(command)
        >>> if response:
        ...     value = protocol.parse_response(response)
        """
        async with self._transaction_lock:
            await self.write(packet, response=False)
            return await self.read_response(timeout=timeout)

    async def query(
        self,
        packet: bytes,
        timeout: float = 3.0,
        match_func: Callable[[bytes], bool] | None = None,
    ) -> bytes | None:
        """
        Send packet and wait for matching response (atomic transaction).

        Similar to send_with_response() but with optional response filtering.
        Useful when telemetry stream notifications might interfere with
        request/response transactions.

        Parameters
        ----------
        packet : bytes
            GENI packet to send
        timeout : float, default=3.0
            Response timeout in seconds
        match_func : callable[[bytes], bool] | None
            Optional filter function. If provided, only responses where
            match_func(response) returns True are returned. Non-matching
            responses are discarded.

        Returns
        -------
        bytes | None
            Response packet, or None if timeout

        Examples
        --------
        >>> # Filter out telemetry stream notifications
        >>> def not_telemetry(data):
        ...     return not (len(data) > 5 and data[4] == 0x0A and data[5] == 0x0E)
        >>> response = await transport.query(request, match_func=not_telemetry)
        """
        async with self._transaction_lock:
            # Drain the queue first to avoid stale responses
            self.clear_response_queue()

            await self.write(packet, response=False)
            logger.debug(f"Query sent: {packet.hex()}")

            # If no filter, just read once
            if match_func is None:
                return await self.read_response(timeout=timeout)

            # With filter, keep reading until match or timeout
            start_time = asyncio.get_event_loop().time()
            remaining = timeout

            while remaining > 0:
                response = await self.read_response(timeout=remaining)
                if response is None:
                    logger.debug("Query timeout - no response received")
                    return None

                logger.debug(f"Query response candidate: {response.hex()}")

                # Check if response matches filter
                if match_func(response):
                    logger.debug("Query response MATCHED filter")
                    return response

                logger.debug("Query response REJECTED by filter")
                # Update remaining timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = timeout - elapsed

            logger.debug("Query timeout waiting for matching response")
            return None

    async def send_command(
        self,
        packet: bytes,
        command: MatcherCommand,
        timeout: float = 3.0,
    ) -> bytes | None:
        """
        Send a frame and wait for the reply that answers it.

        The counterpart to :func:`~alpha_hwr.protocol.matcher.matches`:
        this owns the serialization and the timeout, the matcher owns the
        decision about which reply belongs to which command. Prefer it
        over :meth:`query` with a hand-rolled predicate - the pump's
        matching quirks are firmware behaviour, and every caller open-coding
        them separately is how they drift apart.

        Parameters
        ----------
        packet : bytes
            Complete GENI frame, CRC included.
        command : protocol.Command
            What reply to accept.
        timeout : float, default=3.0
            Seconds to wait.

        Returns
        -------
        bytes | None
            The matching frame, or None if none arrived in time. A None
            here is not necessarily a fault: some writes are committed by
            the pump only after the response window has closed, which is
            what ``command.quiet_timeout`` marks.
        """
        response = await self.query(
            packet,
            timeout=timeout,
            match_func=lambda p: matcher_matches(command, p),
        )

        if response is None:
            label = command.description or "command"
            if command.quiet_timeout:
                logger.debug(f"No response to {label} (expected)")
            else:
                logger.warning(f"No response to {label} within {timeout}s")

        return response

    async def send_wake_burst(
        self,
        repeats: int = 3,
        packet_delay: float = 0.1,
        wake_delay: float = 0.3,
    ) -> None:
        """
        Send a wake-up burst to rouse a sleeping GENI controller.

        Some GENI controllers enter a low-power sleep state between
        operations (e.g. right after the authentication handshake, or
        after the connection has been idle). A read issued while the
        controller is asleep goes unanswered, and on some platforms a
        second read attempt shortly after can even trip a full BLE
        disconnect. Sending a short burst of keep-alive packets first
        wakes the controller so the actual read gets a response.

        Parameters
        ----------
        repeats : int, default=3
            Number of keep-alive packets to send.
        packet_delay : float, default=0.1
            Delay between each keep-alive packet.
        wake_delay : float, default=0.3
            Delay after the burst to allow the controller to wake up
            before issuing the real request.

        Notes
        -----
        Holds ``_transaction_lock`` for the whole burst, like every other
        multi-packet operation on this transport. Without it a burst can
        interleave with an in-flight ``query()``, and the replies it draws
        out land in that query's response queue and confuse its matching.
        Callers must therefore not already hold the lock.

        See docs/protocol/ble_architecture.md ("Keep-Alive Burst") for the
        protocol rationale behind this sequence.
        """
        from ..protocol.frame_builder import FrameBuilder

        keep_alive_packet = FrameBuilder.build_command_info(0x02, 0x01)

        async with self._transaction_lock:
            for _ in range(repeats):
                await self.write(keep_alive_packet, response=False)
                await asyncio.sleep(packet_delay)

            await asyncio.sleep(wake_delay)

        logger.debug("Wake burst sent")

    async def start_keep_alive(self, interval: float = 30.0) -> None:
        """
        Start keep-alive task.

        Sends periodic packets to prevent connection timeout.
        Some BLE stacks disconnect after ~60s of inactivity.

        Parameters
        ----------
        interval : float, default=30.0
            Seconds between keep-alive packets

        Notes
        -----
        Keep-alive is a simple telemetry read request.
        Pump always responds, keeping connection active.
        """
        if self._keep_alive_task and not self._keep_alive_task.done():
            logger.debug("Keep-alive already running")
            return

        self._keep_alive_task = asyncio.create_task(
            self._keep_alive_loop(interval)
        )
        logger.info(f"Keep-alive started (interval={interval}s)")

    async def stop_keep_alive(self) -> None:
        """Stop keep-alive task."""
        if self._keep_alive_task and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                pass
            logger.info("Keep-alive stopped")

    async def _keep_alive_loop(self, interval: float) -> None:
        """
        Keep-alive background task.

        Periodically sends a simple read request to keep connection alive.
        """
        from ..protocol.frame_builder import FrameBuilder

        # Simple read request for keep-alive (reading a dummy register)
        keep_alive_packet = FrameBuilder.build_command_info(0x02, 0x01)

        while True:
            try:
                await asyncio.sleep(interval)
                async with self._transaction_lock:
                    await self.write(keep_alive_packet, response=False)
                    logger.debug("Keep-alive sent")
            except asyncio.CancelledError:
                break
            except READ_ERRORS as e:
                logger.error(f"Keep-alive error: {e}")

    def clear_response_queue(self) -> None:
        """
        Clear all pending responses from queue.

        Useful when starting fresh or after errors.
        """
        count = 0
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        if count > 0:
            logger.debug(f"Cleared {count} pending responses")

    def is_connected(self) -> bool:
        """
        Check if BLE client is connected.

        Returns
        -------
        bool
            True if connected
        """
        return self.client.is_connected

    async def disconnect(self) -> None:
        """
        Disconnect BLE client.

        Stops keep-alive and notifications before disconnecting.
        """
        await self.stop_keep_alive()
        await self.stop_notifications()

        if self.client.is_connected:
            await self.client.disconnect()
            logger.info("Transport disconnected")

    async def on_disconnected(self) -> None:
        """Alias for disconnect() for consistency with Session."""
        await self.disconnect()

    def add_disconnect_handler(self, handler: Callable[[], None]) -> None:
        """
        Register a callback fired when the BLE link drops.

        Handlers run from bleak's own ``disconnected_callback``, so a drop
        is observed as it happens rather than the next time something tries
        to read. Handlers must be synchronous and cheap; schedule anything
        slower onto the loop yourself.
        """
        self._disconnect_handlers.append(handler)

    def notify_disconnected(self) -> None:
        """
        Run the registered disconnect handlers.

        Ordering matters for anything that settles pending work: handlers
        run before the queued state is torn down, so a waiter always gets
        its result rather than being dropped silently.
        """
        logger.info("BLE link dropped")
        self._last_write = None
        for handler in self._disconnect_handlers:
            try:
                handler()
            except Exception as e:  # noqa: BLE001
                # A handler is caller-supplied; one bad handler must not
                # stop the others from learning about the disconnect.
                logger.error(f"Error in disconnect handler: {e}")


# ==========================================================================
# REFERENCE IMPLEMENTATION NOTES
# ==========================================================================
"""
Transport Layer Implementation Guide
=====================================

For implementing transport in other languages:

1. Core Components
   ----------------
   - BLE Client: Platform-specific BLE library (bleak, CoreBluetooth, etc.)
   - Transaction Lock: Mutex/semaphore for sequential operations
   - Response Queue: Thread-safe queue for notifications
   - Notification Handler: BLE callback function

2. Minimal Implementation (Pseudocode)
   ------------------------------------
   ```
   class Transport:
       def __init__(ble_client):
           self.ble = ble_client
           self.lock = Mutex()
           self.queue = ThreadSafeQueue()
           
       def notification_callback(data):
           self.queue.put(data)
           
       async def write(packet):
           await self.ble.write(GENI_UUID, packet)
           
       async def read_response(timeout):
           return await self.queue.get(timeout)
           
       async def send_with_response(packet, timeout):
           with self.lock:
               await self.write(packet)
               return await self.read_response(timeout)
   ```

3. Transaction Locking
   --------------------
   Critical for GENI protocol. Without locking:
   - Response A might match Command B
   - Commands might execute out of order
   - Pump command queue might overflow
   
   Implementation:
   ```
   mutex = create_mutex()
   
   async def send_command(packet):
       await mutex.acquire()
       try:
           await write(packet)
           response = await read_response()
           return response
       finally:
           mutex.release()
   ```

4. Notification Queue
   -------------------
   BLE notifications arrive in callback context (different thread).
   Must safely pass to application thread:
   
   ```
   queue = ThreadSafeQueue(maxsize=100)
   
   def ble_callback(data):
       try:
           queue.put_nowait(data)
       except QueueFull:
           # Log warning, drop packet
           pass
   ```

5. Keep-Alive (Optional but Recommended)
   ---------------------------------------
   Prevents connection timeout on some platforms:
   
   ```
   every 30 seconds:
       send_simple_read_request()
   ```

6. Error Handling
   ---------------
   - Write failures: May indicate disconnection
   - Read timeouts: Command may have failed
   - Queue overflow: Processing too slow, need larger queue
   
7. Testing
   --------
   Test cases to implement:
   - Sequential commands work correctly
   - Concurrent commands are serialized
   - Response timeout works
   - Queue doesn't overflow under load
   - Keep-alive maintains connection

8. Platform-Specific Notes
   ------------------------
   - iOS/macOS: CoreBluetooth, need to handle background modes
   - Android: Android BLE API, need GATT callbacks
   - Linux: BlueZ D-Bus API via bleak or similar
   - Windows: Windows BLE API via bleak
   - ESP32: ESP-IDF BLE, need FreeRTOS queues
"""
