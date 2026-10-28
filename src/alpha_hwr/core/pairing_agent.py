"""
BlueZ pairing agent support for Linux.

``bleak``'s ``BleakClient.pair()`` calls BlueZ's ``Device1.Pair()`` D-Bus
method directly, but does not register a pairing agent. BlueZ requires an
``org.bluez.Agent1`` object to be registered (and set as the default agent)
before it will complete *any* pairing, even "Just Works" pairing that
requires no user interaction. Without one, ``pair()`` fails with::

    org.bluez.Error.AuthenticationFailed: Authentication Failed

Tools like ``bluetoothctl`` register a default agent automatically on
startup, which is why pairing manually via ``bluetoothctl`` works while
calling ``bleak``'s ``pair()`` directly does not.

This module registers a minimal "NoInputNoOutput" agent for the duration of
a pairing operation, which auto-accepts confirmation/authorization requests.
This matches the pump's documented "Just Works" pairing model (see
``docs/protocol/connection.md``).

The agent has to be up **before the link opens**, not just around
``pair()``. The pump starts the pairing: in pairing mode it sends a
security request as soon as it is connected, and BlueZ answers that through
the default agent too.

Note: unlike most modules in this codebase, this file does not use
``from __future__ import annotations``. dbus_fast's ``@method()`` decorator
reads literal annotation values (D-Bus type markers such as ``DBusStr``,
``DBusUInt32``) at class-definition time to build each method's D-Bus
signature; stringified annotations would prevent it from doing so.

Notes for Reimplementation
---------------------------
Any BlueZ D-Bus client library can implement this the same way:

1. Export an object implementing the ``org.bluez.Agent1`` interface
   (``Release``, ``Cancel``, ``RequestConfirmation``,
   ``RequestAuthorization``, ``AuthorizeService`` are enough for
   "Just Works" devices).
2. Call ``org.bluez.AgentManager1.RegisterAgent(path, "NoInputNoOutput")``
   on ``/org/bluez``.
3. Call ``org.bluez.AgentManager1.RequestDefaultAgent(path)``.
4. Connect, then perform the pairing operation.
5. Call ``org.bluez.AgentManager1.UnregisterAgent(path)`` and unexport the
   object.
"""

import asyncio
import logging
import sys
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

AGENT_PATH = "/org/alpha_hwr/agent"
AGENT_CAPABILITY = "NoInputNoOutput"
BLUEZ_SERVICE = "org.bluez"
BLUEZ_ROOT_PATH = "/org/bluez"

#: One agent at a time. They share AGENT_PATH on bleak's one bus, so a
#: second concurrent export fails - and its cleanup would tear down the
#: first one's agent in the middle of a pairing.
#:
#: One lock per event loop, not one per process: an asyncio.Lock binds to
#: the loop it is first contended on, and a later ``asyncio.run()`` that
#: contends it again raises "bound to a different event loop".
_agent_locks: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Lock
] = weakref.WeakKeyDictionary()


def _agent_lock() -> asyncio.Lock:
    """The lock serializing agents on the running loop."""
    loop = asyncio.get_running_loop()
    lock = _agent_locks.get(loop)
    if lock is None:
        lock = _agent_locks[loop] = asyncio.Lock()
    return lock


def _device_suffix(address: str) -> str:
    """``AA:BB:...`` -> ``dev_AA_BB_...``, how BlueZ names a device path."""
    return "dev_" + address.upper().replace(":", "_")


@asynccontextmanager
async def bluez_pairing_agent(
    address: str | None = None,
) -> AsyncIterator[None]:
    """
    Register a temporary BlueZ pairing agent for "Just Works" bonding.

    The agent becomes the host's *default*, so while it is up it hears
    every pairing and authorization request on the system, not only the
    pump's. Given ``address``, it accepts requests for that device and
    rejects the rest with ``org.bluez.Error.Rejected``; without one it
    accepts them all, so callers should pass it.

    Concurrent uses are serialized: they share one D-Bus object path.

    Registers a "NoInputNoOutput" ``org.bluez.Agent1`` object as the BlueZ
    default agent for the duration of the context, then unregisters it on
    exit. This lets BlueZ answer the pump's security request, and lets
    ``BleakClient.pair()`` complete instead of failing with
    ``org.bluez.Error.AuthenticationFailed``. Enter it before connecting.

    This is a no-op on non-Linux platforms (bleak's ``pair()`` is not
    available there anyway) and degrades gracefully if the BlueZ D-Bus
    internals it depends on are unavailable.

    Yields:
        None

    Example:
        >>> async with bluez_pairing_agent():  # doctest: +SKIP
        ...     await bleak_client.pair()
    """
    if not sys.platform.startswith("linux"):
        yield
        return

    try:
        from bleak.backends.bluezdbus.manager import get_global_bluez_manager
        from dbus_fast.annotations import DBusObjectPath, DBusStr, DBusUInt32
        from dbus_fast.errors import DBusError
        from dbus_fast.service import ServiceInterface, method
    except ImportError:
        logger.debug(
            "dbus_fast/bleak BlueZ backend unavailable; skipping pairing "
            "agent registration"
        )
        yield
        return

    wanted = _device_suffix(address) if address else None

    def _check(device: str) -> None:
        """Refuse a request for any device but the one being paired."""
        if wanted is not None and not str(device).endswith(wanted):
            logger.debug("Rejecting pairing request for %s", device)
            raise DBusError(
                "org.bluez.Error.Rejected", "not the device being paired"
            )

    class _NoInputNoOutputAgent(ServiceInterface):
        """Minimal org.bluez.Agent1 implementation for Just Works pairing."""

        def __init__(self) -> None:
            super().__init__("org.bluez.Agent1")

        @method()
        def Release(self) -> None:
            """Called when the agent is unregistered."""

        @method()
        def Cancel(self) -> None:
            """Called when a pairing request is cancelled."""

        @method()
        def RequestConfirmation(
            self, device: DBusObjectPath, passkey: DBusUInt32
        ) -> None:
            """Accept "Just Works" confirmation for the device being paired."""
            _check(device)
            logger.debug("Auto-confirming pairing for device %s", device)

        @method()
        def RequestAuthorization(self, device: DBusObjectPath) -> None:
            """Accept authorization for the device being paired."""
            _check(device)
            logger.debug("Auto-authorizing device %s", device)

        @method()
        def AuthorizeService(
            self, device: DBusObjectPath, uuid: DBusStr
        ) -> None:
            """Accept service authorization for the device being paired."""
            _check(device)
            logger.debug(
                "Auto-authorizing service %s for device %s", uuid, device
            )

    manager = await get_global_bluez_manager()
    # dbus_fast's MessageBus is intentionally reused here (rather than opening
    # a second D-Bus connection) via bleak's internal manager. `_bus` is a
    # private attribute of BlueZManager but is the only way to access the
    # already-connected system bus that bleak itself uses.
    bus = manager._bus

    if bus is None:
        logger.debug("BlueZ D-Bus connection unavailable; skipping agent")
        yield
        return

    agent = _NoInputNoOutputAgent()
    async with _agent_lock():
        exported = False
        registered = False
        try:
            bus.export(AGENT_PATH, agent)
            exported = True

            introspection = await bus.introspect(BLUEZ_SERVICE, BLUEZ_ROOT_PATH)
            proxy = bus.get_proxy_object(
                BLUEZ_SERVICE, BLUEZ_ROOT_PATH, introspection
            )
            agent_manager = proxy.get_interface("org.bluez.AgentManager1")

            # dbus_fast dynamically creates call_<method> methods on the
            # proxy interface at runtime based on introspection data, so
            # these are not visible to static type checkers.
            await agent_manager.call_register_agent(  # type: ignore[attr-defined]
                AGENT_PATH, AGENT_CAPABILITY
            )
            registered = True
            await agent_manager.call_request_default_agent(  # type: ignore[attr-defined]
                AGENT_PATH
            )
            logger.debug(
                "Registered temporary BlueZ pairing agent at %s", AGENT_PATH
            )

            yield

        finally:
            if registered:
                try:
                    await agent_manager.call_unregister_agent(  # type: ignore[attr-defined]
                        AGENT_PATH
                    )
                except Exception as e:  # noqa: BLE001 - best-effort cleanup
                    logger.debug(
                        "Failed to unregister BlueZ pairing agent: %s", e
                    )
            # Only what this context exported: an export that failed may
            # mean the path belongs to someone else.
            if exported:
                try:
                    bus.unexport(AGENT_PATH)
                except Exception as e:  # noqa: BLE001 - best-effort cleanup
                    logger.debug(
                        "Failed to unexport BlueZ pairing agent: %s", e
                    )
