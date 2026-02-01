# Protocol Architecture

This document visualizes the ALPHA HWR protocol architecture and data flows.

For detailed BLE layer information, see [BLE Architecture](ble_architecture.md).

## 1. System Overview

The system follows a layered architecture pattern, separating concerns from low-level transport to high-level business logic.

```mermaid
graph TD
    A[Application/CLI] --> B[Client Facade]
    B --> C[Services Layer]
    C --> D[Protocol Layer]
    D --> E[Transport Layer]
    E --> F[Core Layer]
    F --> G[BLE Stack]
    G --> H[Pump Hardware]
```

## 2. Authentication Sequence

The authentication process is a strict sequence of "magic packets" required to unlock the pump's capabilities.

```mermaid
sequenceDiagram
    participant App
    participant Auth
    participant Transport
    participant Pump
    
    App->>Auth: authenticate()
    Auth->>Transport: send(LEGACY_MAGIC) x3
    Transport->>Pump: BLE write
    Auth->>Transport: send(CLASS10_UNLOCK) x5
    Transport->>Pump: BLE write
    Auth->>Transport: send(EXTEND_1)
    Auth->>Transport: send(EXTEND_2)
    Transport->>Pump: BLE write
    Pump-->>Transport: ACK
    Auth-->>App: Success
```

## 3. Telemetry Reading Flow

Telemetry data flows from the pump's notification characteristic, through the transport layer, parsed by the protocol layer, and consumed by the telemetry service.

```mermaid
sequenceDiagram
    participant App
    participant Telemetry
    participant Protocol
    participant Transport
    participant Pump
    
    App->>Telemetry: read_once()
    Telemetry->>Protocol: build_info_command(0x0A, 0x45, 0x57)
    Protocol->>Transport: send(packet)
    Transport->>Pump: BLE write
    Pump-->>Transport: Response
    Transport-->>Protocol: raw_data
    Protocol->>Protocol: parse_frame(raw_data)
    Protocol->>Protocol: decode_telemetry(frame)
    Protocol-->>Telemetry: TelemetryData
    Telemetry-->>App: TelemetryData
```

## 4. Control Mode Setting Flow

Setting a control mode (e.g., Constant Pressure) involves converting units, encoding the command, and ensuring reliable delivery via transaction locking.

```mermaid
sequenceDiagram
    participant App
    participant Control
    participant Protocol
    participant Transport
    participant Pump
    
    App->>Control: set_mode("constant_pressure", 1.5)
    Control->>Control: validate_setpoint(1.5)
    Control->>Protocol: encode_float_be(14710.0)
    Protocol->>Protocol: build_set_command(0x5600, 0x0601, data)
    Protocol->>Transport: send(packet)
    Transport->>Pump: BLE write
    Pump-->>Transport: ACK
    Transport-->>Control: Success
    Control-->>App: True
```

## 5. Session State Machine

The connection session is managed by a state machine to ensure operations are only performed when the connection is in the correct state.

```mermaid
stateDiagram-v2
    [*] --> DISCONNECTED
    DISCONNECTED --> CONNECTED: connect()
    CONNECTED --> AUTHENTICATING: authenticate()
    AUTHENTICATING --> AUTHENTICATED: success
    AUTHENTICATING --> ERROR: failure
    AUTHENTICATED --> CONNECTED: timeout
    CONNECTED --> DISCONNECTED: disconnect()
    ERROR --> DISCONNECTED: reset
```

## 6. Layer Responsibilities

| Layer | Responsibility | Key Components |
| :--- | :--- | :--- |
| **Application** | User Interface | CLI, Scripts |
| **Client** | Unified API | `AlphaHWRClient` |
| **Services** | Business Logic | `TelemetryService`, `ControlService` |
| **Protocol** | Encoding/Decoding | `FrameBuilder`, `FrameParser`, `Codec` |
| **Transport** | BLE Communication | `Transport`, `Bleak` |
| **Core** | Session/Auth | `Session`, `Authentication` |
