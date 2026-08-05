# Implementation Checklist

Use this checklist to track your implementation progress. Features are organized by priority and difficulty.

## Phase 1: Core Foundation (REQUIRED)

### BLE Transport
- [ ] Connect to pump via BLE
- [ ] Discover GENI service (`0000fdd0-0000-1000-8000-00805f9b34fb`)
- [ ] Get the GENI characteristic (`859cffd1-036e-432a-aa28-1a0085b87ba9`) — there is only one, for both directions
- [ ] Subscribe to notifications on it
- [ ] Send packets on it, split into 20-byte chunks
- [ ] Bond/pair — an unbonded idle connection is dropped at ~1.8 s
- [ ] Disconnect gracefully

### Authentication
- [ ] Send 3x Legacy Magic packets
  - Packet: `27 07 E7 F8 02 03 94 95 96 EB 47`
- [ ] Send 5x Class 10 Unlock packets
  - Packet: `27 07 E7 F8 0A 03 56 00 06 C5 5A`
- [ ] Send Extend 1 packet
  - Packet: `27 05 E7 F8 05 C1 4B C3 82`
- [ ] Send Extend 2 packet
  - Packet: `27 05 E7 F8 0B C1 0F D0 C3`
- [ ] Observe the inter-stage delays: 50 ms between packets, 100 ms after
      stage 1, 200 ms after stage 2, 500 ms before the first command
- [ ] Verify pump accepts commands after authentication
  - There is **no ack** — sending the sequence without error is not proof

### Session Management
- [ ] Track connection state
- [ ] Track authentication state
- [ ] Implement state guards (ensure_connected, ensure_authenticated)
- [ ] Handle disconnection
- [ ] Handle timeouts

## Phase 2: Protocol Layer (REQUIRED)

### Codec (Encoding/Decoding)
- [ ] Encode IEEE 754 big-endian float
- [ ] Decode IEEE 754 big-endian float
- [ ] Encode uint16 big-endian
- [ ] Decode uint16 big-endian
- [ ] Encode uint32 big-endian
- [ ] Decode uint32 big-endian
- [ ] Calculate CRC-16/CCITT (0x1021, init 0xFFFF, final XOR 0xFFFF)
- [ ] Validate CRC on received packets

### Frame Builder
- [ ] Build INFO command (Class 2/3)
- [ ] Build INFO command (Class 10)
- [ ] Build SET command (Class 10)
- [ ] Build READ command (Class 10)
- [ ] Add CRC to frames — the **same** CRC for reads and writes
- [ ] Validate frame length
- [ ] Reproduce the four handshake constants from their APDUs — if your
      builder is right, they fall out, and a mismatch localises the bug

### Frame Parser
- [ ] Parse start byte (0x27 or 0x24)
- [ ] Extract length field
- [ ] Extract service ID (0xE7)
- [ ] Extract source (0xF8)
- [ ] Read byte 5 of a **response** as a payload length, not a type code
- [ ] Match replies by their identifier pair at bytes 6-9
  - [ ] Accept the two identifiers **swapped** — the pump is inconsistent
  - [ ] Treat a zero identifier as a real value, not a wildcard
  - [ ] Fall back to a class match for objects nobody has measured
- [ ] Validate CRC
- [ ] Handle invalid frames

## Phase 3: Telemetry (REQUIRED)

### Basic Telemetry
- [ ] Read motor state (Sub 0x45, Obj 0x57)
  - [ ] Grid voltage
  - [ ] Current
  - [ ] DC power
  - [ ] Speed (RPM)
  - [ ] Converter temperature
- [ ] Read flow/pressure (Sub 0x122, Obj 0x5D)
  - [ ] Flow rate (m³/h)
  - [ ] Head (m)
  - [ ] Inlet pressure (bar)
  - [ ] Outlet pressure (bar)
- [ ] Read pump state (Sub 0x122, Obj 0x93)
  - [ ] Run state (stopped/running)
  - [ ] Control mode
  - [ ] Operating hours

### Advanced Telemetry (Optional)
- [ ] Read temperature sensor (Sub 0x122, Obj 0x94)
- [ ] Read energy data (Sub 0x118, Obj 0x99)
- [ ] Read vibration data (Sub 0x45, Obj 0xC2)
- [ ] Read extended statistics

## Phase 4: Control Operations (REQUIRED)

### Basic Control

Three separate objects. Routing everything through one is the single most
consequential mistake a port can make here.

- [ ] Start pump — **Class 3**, `27 05 E7 F8 03 81 06 E5 87`
- [ ] Stop pump — **Class 3**, `27 05 E7 F8 03 81 05 D5 E4`
  - [ ] Nine bytes, no room for a mode or setpoint. That is the point.
- [ ] Set control mode — Object 86 **Sub 10** (`0x0A01`), with
      `operation_mode = NoCmd (0x06)` and setpoint `7F FF FF FF`
  - [ ] Send **no** configuration commit after a mode change
- [ ] Read state — Object 86 **Sub 7**, never Sub 6
  - [ ] Sub 6 is the request object; its `control_source` reads 0 always

### Setpoints
- [ ] Set setpoint — Object 86 Sub 6 (fused: run state + mode + setpoint)
  - [ ] Send `7F FF FF FF` where you are not asserting a setpoint
  - [ ] **Never** send `45 65 70 00` — that is 3671.0, the pump's max speed
- [ ] Convert metres to Pascals (× 9806.65)
- [ ] Convert flow setpoints to **SI m³/s** (÷ 3600) — telemetry flow is m³/h
- [ ] Send the configuration commit afterwards
  - [ ] Built from the pump's **current** Object 84 Sub 1 overview
  - [ ] Skip the commit entirely if that read fails

### Verified writes
- [ ] Serialize writes — one at a time, no overlap
- [ ] Read the value back after every write
- [ ] Report clamping as a **success** with the stored value
  - [ ] 600 RPM stores 1650; 4400 stores 3671
- [ ] Distinguish "your request was bad" from "the pump refused"
- [ ] Cache the pump's state on connect, and refuse writes until it is valid
  - [ ] Several writes carry fields the caller did not set; guessing them
        zeroes a schedule or resets an autoadapt flag, silently

## Phase 5: Device Information (REQUIRED)

### Basic Device Info
- [ ] Read firmware version
- [ ] Read serial number
- [ ] Read model name
- [ ] Read manufacture date

### Statistics
- [ ] Read operating hours
- [ ] Read start count
- [ ] Read energy consumption
- [ ] Read total flow

### Alarms
- [ ] Read alarm register
- [ ] Parse alarm bits
- [ ] Map alarm codes to descriptions

## Phase 6: Schedule Management (OPTIONAL)

### Schedule Operations
- [ ] Read current schedule (Object 84, Sub 1000 + layer)
- [ ] Parse schedule entries — 7 days × 6 bytes, hour and minute as plain
      bytes (**not** minutes-since-midnight)
- [ ] Write a layer **whole** — 42 bytes, read-edit-write for one day
  - [ ] Split the 59-byte frame into **three** chunks, not two
- [ ] Enable / disable the schedule
- [ ] Detect the stalled state: schedule enabled + pump stopped never runs
      and reports no fault
- [ ] Order flag writes so you never pass through it, even transiently
- [ ] Validate time format (HH:MM) and day of week

### Single Events (optional)
- [ ] Read slots (Object 84, Sub 900+)
- [ ] Take the slot count from the pump, not from the sub-id range
- [ ] Encode timestamps as **local Unix time** — the wall clock stamped as
      UTC. Encoding real UTC round-trips byte-identically, so verification
      cannot catch it; check against a clock and a running motor.
- [ ] Vacation = a `Stop` single event (action `0x01`; `0x02` is Run)

## Phase 7: Configuration (OPTIONAL)

### Backup/Restore
- [ ] Read all configuration values
- [ ] Serialize to JSON/format
- [ ] Write to file
- [ ] Read from file
- [ ] Deserialize configuration
- [ ] Write configuration to pump
- [ ] Verify configuration after write

### Settings
- [ ] Read pump settings
- [ ] Update individual settings
- [ ] Validate settings ranges
- [ ] Factory reset (use with caution!)

## Phase 8: Error Handling (REQUIRED)

### Connection Errors
- [ ] Handle BLE connection failure
- [ ] Handle authentication failure
- [ ] Handle disconnection during operation
- [ ] Implement reconnection logic
- [ ] Timeout handling

### Protocol Errors
- [ ] Handle invalid CRC
- [ ] Handle malformed packets
- [ ] Handle unexpected responses
- [ ] Handle NACK responses

### Application Errors
- [ ] Validate user inputs
- [ ] Provide clear error messages
- [ ] Log errors for debugging
- [ ] Graceful degradation

## Phase 9: Testing (REQUIRED)

### Unit Tests
- [ ] Test codec encode/decode
- [ ] Test CRC calculation
- [ ] Test frame building
- [ ] Test frame parsing
- [ ] Test telemetry decoding

### Integration Tests
- [ ] Test full authentication sequence
- [ ] Test telemetry reading
- [ ] Test control commands
- [ ] Test schedule operations
- [ ] Test error scenarios

### Validation Tests
- [ ] Verify test vectors
- [ ] Test with real pump
- [ ] Cross-platform testing
- [ ] Performance testing

## Phase 10: Documentation (RECOMMENDED)

### Code Documentation
- [ ] Document all public APIs
- [ ] Add usage examples
- [ ] Document error conditions
- [ ] Add inline comments for complex logic

### User Documentation
- [ ] Getting started guide
- [ ] API reference
- [ ] Examples/tutorials
- [ ] Troubleshooting guide

## Phase 11: Packaging (RECOMMENDED)

### Build & Distribution
- [ ] Package for distribution
- [ ] Version management
- [ ] Dependency management
- [ ] CI/CD pipeline
- [ ] Release process

### Quality Assurance
- [ ] Code linting
- [ ] Type checking
- [ ] Security audit
- [ ] Performance profiling

## Success Criteria

Your implementation is considered **minimal** when:
- [x] Can connect and authenticate
- [x] Can read basic telemetry (flow, pressure, speed)
- [x] Can start/stop pump
- [x] Can set control modes
- [x] Handles errors gracefully

Your implementation is considered **complete** when:
- [x] All required features implemented
- [x] Unit tests pass
- [x] Integration tests pass
- [x] Test vectors validated
- [x] Documentation complete

Your implementation is considered **production-ready** when:
- [x] Error handling complete
- [x] Performance optimized
- [x] Security reviewed
- [x] Cross-platform tested
- [x] User feedback incorporated

## Language-Specific Considerations

### Python
- Use `bleak` for BLE
- Use `asyncio` for async operations
- Use `struct` for binary packing
- Type hints with `typing`

### JavaScript/TypeScript
- Use Web Bluetooth API or `noble`
- Use Promises/async-await
- Use DataView for binary handling
- TypeScript for type safety

### Rust
- Use `btleplug` for BLE
- Use `tokio` for async
- Use `byteorder` for endianness
- Leverage type system for safety

### C/C++
- Platform-specific BLE libraries
- Manual memory management
- Use standard network byte order functions
- Consider using smart pointers

### Go
- Use `tinygo-org/bluetooth` or `paypal/gatt`
- Use goroutines for concurrency
- Use `encoding/binary` for byte order
- Error handling via return values

## Progress Tracking

Track your progress by marking items as you complete them:

- **Phase 1-2**: Core & Protocol (2-3 days)
- **Phase 3-5**: Telemetry & Control (3-4 days)
- **Phase 6-7**: Advanced Features (2-3 days)
- **Phase 8-9**: Error Handling & Testing (2-3 days)
- **Phase 10-11**: Documentation & Packaging (1-2 days)

**Total estimated time**: 2-3 weeks for full implementation

## Next Steps

1. Start with Phase 1 (Core Foundation)
2. Use [test_vectors.md](test_vectors.md) to validate each phase
3. Refer to [common_pitfalls.md](common_pitfalls.md) when stuck
4. Review [architecture.md](architecture.md) for design guidance
5. Follow [layer_by_layer.md](layer_by_layer.md) for detailed steps
