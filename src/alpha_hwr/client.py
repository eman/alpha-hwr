"""
Grundfos ALPHA HWR Client - Unified API for pump interaction.

This is the main entry point for the library, providing a clean, service-oriented
API for interacting with Grundfos ALPHA HWR pumps via Bluetooth Low Energy.

Architecture:
-------------
The client is a thin facade over specialized service modules:
- Core: Transport, Session, Authentication (connection and auth management)
- Services: Telemetry, Control, Schedule, DeviceInfo, Configuration
- Protocol: Frame building/parsing, telemetry decoding (used by services)

This design separates concerns and makes the codebase easily portable to
other languages (TypeScript, Rust, C, etc.).

Example Usage:
--------------
```python
import asyncio
from alpha_hwr import AlphaHWRClient

async def main():
    # Connect and authenticate
    async with AlphaHWRClient("DEVICE_ADDRESS") as client:
        # Read telemetry
        data = await client.telemetry.read_once()
        print(f"Flow: {data.flow_m3h} m³/h")

        # Control pump
        await client.control.start()
        await client.control.set_constant_pressure(1.5)

        # Manage schedule
        await client.schedule.enable()
        entries = await client.schedule.read_entries()

        # Backup configuration
        await client.config.backup("pump_backup.json")

asyncio.run(main())
```

Cross-Language Implementation Notes:
------------------------------------
TypeScript:
  class AlphaHWRClient {
    public telemetry: TelemetryService;
    public control: ControlService;
    public schedule: ScheduleService;
    public deviceInfo: DeviceInfoService;
    public config: ConfigurationService;

    async connect(): Promise<void> { }
    async disconnect(): Promise<void> { }
  }

Rust:
  pub struct AlphaHWRClient {
    telemetry: TelemetryService,
    control: ControlService,
    schedule: ScheduleService,
    device_info: DeviceInfoService,
    config: ConfigurationService,
  }

  impl AlphaHWRClient {
    pub async fn connect(&self) -> Result<()> { }
    pub async fn disconnect(&self) -> Result<()> { }
  }

C:
  typedef struct {
    TelemetryService* telemetry;
    ControlService* control;
    ScheduleService* schedule;
    DeviceInfoService* device_info;
    ConfigurationService* config;
  } AlphaHWRClient;

  int alpha_hwr_connect(AlphaHWRClient* client);
  int alpha_hwr_disconnect(AlphaHWRClient* client);
"""

from __future__ import annotations

import inspect
import logging
import sys
from importlib.metadata import version as _pkg_version
from types import TracebackType
from typing import Self

from bleak import BleakClient, BleakScanner

from .config import get_settings
from .constants import GENI_SERVICE_UUID
from .core.authentication import AuthenticationHandler
from .core.session import Session, SessionState
from .core.transport import Transport
from .exceptions import ConnectionError
from .models import DeviceInfo
from .services import (
    ConfigurationService,
    ControlService,
    DeviceInfoService,
    EventLogService,
    HistoryService,
    ScheduleService,
    TelemetryService,
    TimeService,
)

logger = logging.getLogger(__name__)


def _make_bleak_client(address: str, adapter: str | None) -> BleakClient:
    """Construct a BleakClient compatible with both Bleak 2.x and 3.x.

    The ``adapter`` keyword argument was deprecated in Bleak 3.0. On Linux
    (BlueZ) the replacement is the ``bluez`` argument; on other platforms the
    adapter concept does not apply and the argument is omitted.

    Args:
        address: BLE device address.
        adapter: Optional BlueZ adapter name (e.g. ``"hci1"``). Linux only.

    Returns:
        Configured BleakClient instance.
    """
    if not adapter:
        return BleakClient(address)

    try:
        bleak_major = int(_pkg_version("bleak").split(".")[0])
    except Exception:
        # importlib.metadata may lack dist info for editable/vendored installs.
        # Fall back to inspecting the BleakClient signature at runtime.
        sig = inspect.signature(BleakClient.__init__)
        bleak_major = 3 if "bluez" in sig.parameters else 0

    if bleak_major >= 3:
        if sys.platform.startswith("linux"):
            return BleakClient(address, bluez={"adapter": adapter})
        # adapter is a BlueZ-only concept; ignore on other platforms
        return BleakClient(address)

    return BleakClient(address, adapter=adapter)


class AlphaHWRClient:
    """
    Main client for Grundfos ALPHA HWR pump interaction.

    Provides a unified API for all pump operations through specialized services.
    Manages BLE connection, authentication, and service lifecycle.

    Services:
        telemetry: Read sensor data (flow, pressure, power, temperature)
        control: Start/stop pump, set modes and setpoints
        schedule: Manage weekly pump schedules
        device_info: Read device identification and statistics
        config: Backup and restore pump configuration
        time: Read and synchronize pump real-time clock
        history: Read historical trend data (flow, head, temperature)
        event_log: Read pump event log entries and metadata

    Attributes:
        address: BLE device address (UUID on macOS, MAC on Linux/Windows)
        adapter: Optional BLE adapter identifier
        session: Session manager (tracks authentication state)
        transport: BLE transport layer
        auth: Authentication handler

    Example:
        >>> async with AlphaHWRClient("DEVICE_ADDRESS") as client:
        ...     # Telemetry
        ...     data = await client.telemetry.read_once()
        ...     print(f"Flow: {data.flow_m3h} m³/h")
        ...
        ...     # Control
        ...     await client.control.start()
        ...     await client.control.set_constant_pressure(1.5)
        ...
        ...     # Schedule
        ...     await client.schedule.enable()
        ...
        ...     # Backup
        ...     await client.config.backup("pump.json")

    Implementation Notes:
        The client is a thin orchestration layer. All business logic lives in
        the service modules. This makes the code:
        - Easier to understand (single responsibility per service)
        - Easier to test (mock services independently)
        - Easier to port (services are self-contained)
    """

    def __init__(
        self,
        address: str | None = None,
        adapter: str | None = None,
        auto_authenticate: bool = True,
    ):
        """
        Initialize the ALPHA HWR client.

        Args:
            address: BLE device address (UUID on macOS, MAC on Linux/Windows).
                     If None, reads from ALPHA_HWR_DEVICE_ADDRESS env variable.
            adapter: Optional BLE adapter identifier (platform-specific)
            auto_authenticate: Automatically authenticate after connection (default True)

        Example:
            >>> # Use address from environment
            >>> client = AlphaHWRClient()
            >>>
            >>> # Use specific address
            >>> client = AlphaHWRClient("A1B2C3D4-E5F6-7890-1234-567890ABCDEF")
            >>>
            >>> # Specify adapter (Linux)
            >>> client = AlphaHWRClient(address="00:11:22:33:44:55", adapter="hci1")
        """
        settings = get_settings()
        self.address: str | None = address or settings.device_address
        self.adapter: str | None = adapter or settings.adapter
        self.auto_authenticate = auto_authenticate

        # Core components
        self._bleak_client: BleakClient | None = None
        self.transport: Transport | None = None
        self.session: Session | None = None
        self.auth: AuthenticationHandler | None = None

        # Cache for BLE advertisement data (read before connection)
        self._cached_product_info: dict[str, int] | None = None

        # Services (initialized after connection)
        self.telemetry: TelemetryService | None = None
        self.control: ControlService | None = None
        self.schedule: ScheduleService | None = None
        self.device_info: DeviceInfoService | None = None
        self.config: ConfigurationService | None = None
        self.time: TimeService | None = None
        self.history: HistoryService | None = None
        self.event_log: EventLogService | None = None

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to the pump."""
        return (
            self._bleak_client is not None and self._bleak_client.is_connected
        )

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated with the pump."""
        return (
            self.session is not None
            and self.session.state == SessionState.AUTHENTICATED
        )

    async def connect(
        self, timeout: float = 60.0, fast_mode: bool = False
    ) -> None:
        """
        Connect to the pump via BLE.

        Establishes BLE connection, initializes transport layer, and sets up
        all service modules. If auto_authenticate is enabled, also performs
        authentication handshake.

        If no address is configured, automatically attempts to discover
        a nearby ALPHA HWR pump.

        Args:
            timeout: Connection timeout in seconds (default 60s)
            fast_mode: If True, skips authentication delays (for testing)

        Raises:
            ConnectionError: If connection fails or no device found during discovery
            ValueError: If discovery fails

        Example:
            >>> # Connect to specific address
            >>> client = AlphaHWRClient("DEVICE_ADDRESS")
            >>> await client.connect()
            >>>
            >>> # Connect using automatic discovery
            >>> client = AlphaHWRClient()
            >>> await client.connect()

        Implementation Notes:
            Connection sequence:
            1. Resolve address (discovery if needed)
            2. Scan for advertisement data before connecting
            3. Create BleakClient with device address
            ...
        """
        # Automatic Discovery if no address provided
        if not self.address:
            logger.info(
                "No device address configured. Attempting automatic discovery..."
            )
            discovered = await self.discover(timeout=10.0)
            if not discovered:
                raise ConnectionError(
                    "No ALPHA HWR pumps found during automatic discovery."
                )

            self.address = discovered[0].address
            logger.info(
                f"Discovered and selected pump: {discovered[0].name} ({self.address})"
            )

        try:
            logger.info(f"Connecting to {self.address} (timeout={timeout}s)...")

            # Scan for advertisement data before connecting (can't scan while connected)
            await self._scan_advertisement_data()

            # Create BLE client
            if self.address is None:
                raise ValueError("BLE device address is not set")
            self._bleak_client = _make_bleak_client(self.address, self.adapter)

            # Connect to device
            await self._bleak_client.connect(timeout=timeout)
            logger.info("BLE connection established")

            # Initialize core components
            self.transport = Transport(self._bleak_client)
            self.session = Session()
            self.session.on_connected()  # Mark session as connected
            self.auth = AuthenticationHandler(self._bleak_client)

            # Start BLE notifications
            await self.transport.start_notifications()
            logger.info("BLE notifications started")

            # Initialize services
            self._initialize_services()
            logger.info("Services initialized")

            # Register telemetry notification handler
            if self.telemetry:
                telemetry_service = self.telemetry  # Capture for closure

                def telemetry_handler(data: bytes) -> None:
                    """Forward notifications to telemetry service."""
                    try:
                        logger.debug(
                            f"Telemetry handler called with {len(data)} bytes: {data.hex()}"
                        )
                        telemetry_service.update_from_notification(data)
                        logger.debug("Telemetry updated successfully")
                    except Exception as e:
                        logger.error(
                            f"Telemetry notification handler error: {e}",
                            exc_info=True,
                        )

                await self.transport.start_notifications(telemetry_handler)
                logger.info("Telemetry notification handler registered")

            # Auto-authenticate if enabled
            if self.auto_authenticate:
                await self.authenticate(fast_mode=fast_mode)

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self._cleanup()
            raise ConnectionError(f"Failed to connect to {self.address}: {e}")

    async def disconnect(self) -> None:
        """
        Disconnect from the pump.

        Cleanly shuts down all services, stops BLE notifications, and
        disconnects from the device.

        Example:
            >>> await client.disconnect()
            >>> print(f"Connected: {client.is_connected}")  # False

        Implementation Notes:
            Disconnect sequence:
            1. Stop BLE notifications
            2. Clear service references
            3. Disconnect BLE client
            4. Reset all state

            Safe to call multiple times (idempotent).
        """
        logger.info("Disconnecting from pump...")
        await self._cleanup()
        logger.info("Disconnected")

    async def authenticate(self, fast_mode: bool = False) -> bool:
        """
        Authenticate with the pump.

        Performs the authentication handshake to enable control operations.
        Read-only operations (telemetry, device info) don't require authentication,
        but control operations (start, stop, mode changes) do.

        Args:
            fast_mode: If True, skips delays for testing purposes.

        Returns:
            True if authentication successful, False otherwise

        Example:
            >>> success = await client.authenticate()
            >>> if success:
            ...     print("Authenticated successfully")
            ...     await client.control.start()
        """
        if not self.auth or not self.session:
            logger.error(
                "Authentication handler not initialized. Call connect() first."
            )
            return False

        try:
            logger.info("Starting authentication handshake...")
            self.session.on_authenticating()  # Mark session as authenticating
            success = await self.auth.authenticate(fast_mode=fast_mode)

            if success:
                self.session.on_authenticated()  # Mark session as authenticated
                logger.info("Authentication successful")
            else:
                self.session.on_error("Authentication failed")
                logger.warning("Authentication failed")

            return success

        except Exception as e:
            self.session.on_error(f"Authentication error: {e}")
            logger.error(f"Authentication error: {e}")
            return False

    async def pair_device(self) -> bool:
        """
        Pair and authenticate with the pump (CLI compatibility alias).

        This is an alias for authenticate() for backward compatibility with CLI code.

        Returns:
            True if authentication successful, False otherwise
        """
        return await self.authenticate()

    @classmethod
    async def discover(
        cls, timeout: float = 10.0, service_uuid: str = GENI_SERVICE_UUID
    ) -> list[DeviceInfo]:
        """
        Discover ALPHA HWR pumps nearby.

        Scans for BLE devices advertising the Grundfos GENI service.
        Returns basic device information extracted from BLE advertisements.

        Args:
            timeout: Scan duration in seconds (default 10s)
            service_uuid: Service UUID to filter (default Grundfos GENI)

        Returns:
            List of DeviceInfo objects for discovered pumps

        Example:
            >>> devices = await AlphaHWRClient.discover()
            >>> for device in devices:
            ...     print(f"Found: {device.product_name} at {device.address}")
            >>>
            >>> # Connect to first device
            >>> if devices:
            ...     client = AlphaHWRClient(devices[0].address)
            ...     await client.connect()

        Implementation Notes:
            Discovery uses BLE advertisement scanning. Device info is extracted
            from manufacturer data in the advertisement packet without connecting.

            TypeScript:
              static async discover(timeout: number = 10000): Promise<DeviceInfo[]> {
                const scanner = new BleakScanner();
                const devices = await scanner.discover(timeout, GENI_SERVICE_UUID);
                return devices.map(parseDeviceInfo);
              }

            Rust:
              pub async fn discover(timeout: Duration) -> Result<Vec<DeviceInfo>> {
                let scanner = BleakScanner::new();
                let devices = scanner.discover(timeout, GENI_SERVICE_UUID).await?;
                Ok(devices.into_iter().map(parse_device_info).collect())
              }
        """
        logger.info(f"Scanning for ALPHA HWR pumps (timeout={timeout}s)...")

        devices: list[DeviceInfo] = []

        try:
            # Broad scan without UUID filter first to see what's out there
            scanner = BleakScanner()
            discovered = await scanner.discover(
                timeout=timeout, return_adv=True
            )

            logger.debug(
                f"Scan complete. Found {len(discovered)} total BLE devices."
            )

            for address, (device, adv) in discovered.items():
                uuids = [s.lower() for s in adv.service_uuids]
                name = device.name or ""

                logger.debug(
                    f"Checking device: {name} ({address}) - UUIDs: {uuids}"
                )

                # Matches if:
                # 1. Has correct Service UUID (fdd0)
                # 2. Has Grundfos Company ID in service data (fe5d)
                is_geni = "0000fdd0-0000-1000-8000-00805f9b34fb" in uuids
                is_grundfos = (
                    "0000fe5d-0000-1000-8000-00805f9b34fb" in adv.service_data
                )

                if is_geni or is_grundfos:
                    logger.info(
                        f"MATCHED ALPHA HWR: {name} ({address}) [Service={is_geni}, Data={is_grundfos}]"
                    )
                    # Extract device info from advertisement
                    info = DeviceInfo(
                        address=device.address,
                        name=device.name or "Unknown",
                        product_name="ALPHA HWR",
                    )
                    devices.append(info)

        except Exception as e:
            logger.error(f"Discovery failed: {e}")

        logger.info(f"Found {len(devices)} ALPHA HWR pump(s)")
        return devices

    # -------------------------------------------------------------------------
    # Context manager support
    # -------------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        """Async context manager entry - connects to pump."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit - disconnects from pump."""
        await self.disconnect()

    # -------------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------------

    def _initialize_services(self) -> None:
        """Initialize all service modules with core components."""
        if not self.transport or not self.session:
            raise RuntimeError(
                "Transport and session must be initialized first"
            )

        # Initialize services
        self.telemetry = TelemetryService(self.transport, self.session)
        self.schedule = ScheduleService(self.session, self.transport)
        self.control = ControlService(
            self.transport, self.session, self.schedule
        )
        self.device_info = DeviceInfoService(
            self.transport,
            self.session,
            self.address,
            self._cached_product_info,
        )
        self.time = TimeService(self.transport, self.session)
        self.history = HistoryService(self.transport, self.session)
        self.event_log = EventLogService(self.transport, self.session)

        # Configuration service depends on other services
        self.config = ConfigurationService(
            self.device_info, self.control, self.schedule
        )

    async def _scan_advertisement_data(self) -> None:
        """
        Scan for device and cache BLE advertisement data.

        This must be done before connecting since scanning is not possible
        while connected. Stores product_family, product_type, product_version
        in cache for later retrieval by DeviceInfoService.
        """
        try:
            from bleak import BleakScanner

            logger.debug(
                f"Scanning for device {self.address} to read advertisement data..."
            )
            devices = await BleakScanner.discover(timeout=5.0, return_adv=True)

            for device, adv in devices.values():
                if str(device.address).upper() == str(self.address).upper():
                    logger.debug(f"Found device: {device.name}")

                    # Look for product info in service data (uses company UUID fe5d)
                    company_uuid = "0000fe5d-0000-1000-8000-00805f9b34fb"

                    if company_uuid in adv.service_data:
                        data = adv.service_data[company_uuid]
                        logger.debug(f"Service data: {data.hex()}")

                        if len(data) >= 6:
                            self._cached_product_info = {
                                "product_family": data[3],
                                "product_type": data[4],
                                "product_version": data[5],
                            }
                            logger.debug(
                                f"Cached product info: {self._cached_product_info}"
                            )
                            return
                    else:
                        logger.debug("No GENI service data in advertisement")
                        return

            logger.debug("Device not found in scan results")

        except Exception as e:
            logger.debug(f"Failed to scan for advertisement data: {e}")
            # Don't fail connection if we can't get advertisement data

    async def _cleanup(self) -> None:
        """Clean up all resources and reset state."""
        # Stop notifications
        if self.transport:
            try:
                await self.transport.on_disconnected()
            except Exception as e:
                logger.debug(f"Error during transport cleanup: {e}")

        # Update session state
        if self.session:
            try:
                self.session.on_disconnected()
            except Exception as e:
                logger.debug(f"Error during session cleanup: {e}")

        # Disconnect BLE if still connected (should be handled by transport)
        if (
            self._bleak_client
            and self._bleak_client.is_connected
            and (not self.transport or not self.transport.is_connected())
        ):
            try:
                await self._bleak_client.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting BLE: {e}")

        # Clear service references
        self.telemetry = None
        self.control = None
        self.schedule = None
        self.device_info = None
        self.config = None
        self.time = None
        self.history = None
        self.event_log = None
        self._bleak_client = None


# -------------------------------------------------------------------------
# Module-level convenience functions
# -------------------------------------------------------------------------


async def discover_devices(timeout: float = 10.0) -> list[str]:
    """
    Discover Grundfos ALPHA HWR pumps nearby.

    Convenience function that scans for BLE devices advertising the
    Grundfos GENI service and returns their addresses.

    Args:
        timeout: Scan duration in seconds (default 10s)

    Returns:
        List of device addresses (UUIDs on macOS, MACs on Linux/Windows)

    Example:
        >>> devices = await discover_devices()
        >>> print(f"Found {len(devices)} device(s)")
        >>> for address in devices:
        ...     print(f"  {address}")
        >>>
        >>> # Connect to first device
        >>> if devices:
        ...     client = AlphaHWRClient(devices[0])
        ...     await client.connect()

    Note:
        For more detailed device information, use AlphaHWRClient.discover()
        which returns DeviceInfo objects with product name, etc.
    """
    from bleak import BleakScanner

    logger.info(f"Scanning for devices (timeout={timeout}s)...")

    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    found: list[str] = []

    for device, adv in devices.values():
        if GENI_SERVICE_UUID.lower() in [u.lower() for u in adv.service_uuids]:
            found.append(device.address)
            logger.info(f"Found device: {device.address}")

    logger.info(f"Found {len(found)} Grundfos device(s)")
    return found
