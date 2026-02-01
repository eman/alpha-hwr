# Client API

The `AlphaHWRClient` is the main entry point for interacting with the pump. In the new modular architecture, it acts as a facade and coordinator for specialized services.

```python
from alpha_hwr.client import AlphaHWRClient
```

## Constructor

```python
client = AlphaHWRClient(address: str | None = None, adapter: str | None = None)
```

* **address**: The Bluetooth address (MAC or UUID) of the pump. If `None`, it attempts to load from configuration.
* **adapter**: (Optional) The Bluetooth adapter interface to use (e.g., `hci0`).

## Services

Most functionality is delegated to specialized services, accessible via properties on the client instance:

| Property | Service | Purpose |
| :--- | :--- | :--- |
| `client.telemetry` | `TelemetryService` | Real-time and snapshot telemetry |
| `client.control` | `ControlService` | Start/stop, mode switching, setpoints |
| `client.device_info` | `DeviceInfoService` | Serial, firmware, model, statistics |
| `client.schedule` | `ScheduleService` | Weekly schedule management (5 layers) |
| `client.history` | `HistoryService` | Historical trends (100 cycles) |
| `client.events` | `EventLogService` | Pump event log (20 entries) |
| `client.clock` | `TimeService` | Real-time clock management |
| `client.config` | `ConfigurationService` | Backup and restore operations |

---

## Connection Management

### `connect`

```python
async def connect(timeout: float = 60.0) -> None
```

Establishes the BLE connection and subscribes to the GENI characteristic notifications.

* **timeout**: Connection timeout in seconds.
* *Raises*: `ConnectionError` if failed.

### `disconnect`

```python
async def disconnect() -> None
```

Closes the BLE connection.

### `authenticate`

```python
async def authenticate(fast_mode: bool = False) -> bool
```

Performs the application-layer handshake ("Magic Packet" sequence) required to unlock control commands and high-frequency telemetry.

* **fast_mode**: If `True`, uses a shorter authentication sequence (3x Legacy, 5x Class 10 Unlock, Extensions). Default is `False`.
* **Critical**: Must be called after `connect()` for the pump to accept commands.
* *Returns*: `True` if handshake packets were sent.

---

## High-Level Convenience Methods

While services are the preferred way to access functionality, the client provides high-level convenience methods for common operations.

### Control

- `await client.start_pump(mode=None)` -> Starts the pump.
- `await client.stop_pump()` -> Stops the pump.
- `await client.set_constant_pressure(value_m)` -> Sets constant pressure.
- `await client.set_constant_speed(value_rpm)` -> Sets constant speed.

### Telemetry

- `client.get_telemetry()` -> Returns current `TelemetryData` snapshot.
- `await client.read_telemetry()` -> Explicitly polls for a new telemetry snapshot.

### Device Information

- `await client.read_device_info(connect=True)` -> Returns `DeviceInfo` object.
- `await client.read_statistics()` -> Returns `Statistics` object.

---

## Context Manager Support

The client supports the async context manager protocol for automatic connection/disconnection.

```python
async with AlphaHWRClient(address="...") as client:
    await client.authenticate(fast_mode=True)
    
    # Access services directly
    data = await client.telemetry.read_once()
    print(f"Flow: {data.flow_m3h} m3/h")
    
    # Use high-level methods
    await client.start_pump()

# Automatically disconnects here
```
