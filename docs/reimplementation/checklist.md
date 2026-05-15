# Implementation Checklist

Use this checklist to track your implementation progress. Features are organized by priority and difficulty.

## Phase 1: Core Foundation (REQUIRED)

### BLE Transport
- [ ] Connect to pump via BLE
- [ ] Discover GENI service (`0000fdd0-0000-1000-8000-00805f9b34fb`)
- [ ] Get TX characteristic (`0000fdd1-...`)
- [ ] Get RX characteristic (`0000fdd2-...`)
- [ ] Subscribe to notifications on RX
- [ ] Send packets via TX
- [ ] Disconnect gracefully

### Authentication
- [ ] Send 3x Legacy Magic packets
  - Packet: `27 07 E7 F8 02 03 94 95 96 EB 47`
- [ ] Send 5x Class 10 Unlock packets
  - Packet: `27 07 E7 F8 0A 03 56 00 06 C5 5A`
- [ ] Send Extend 1 packet
  - Packet: `27 05 E7 F8 0B C1 0F D0 C3`
- [ ] Send Extend 2 packet
  - Packet: `27 05 E7 F8 05 C1 4B C3 82`
- [ ] Verify pump accepts commands after authentication

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
- [ ] Calculate CRC-16/MODBUS
- [ ] Validate CRC on received packets

### Frame Builder
- [ ] Build INFO command (Class 2/3)
- [ ] Build INFO command (Class 10)
- [ ] Build SET command (Class 10)
- [ ] Build READ command (Class 10)
- [ ] Build WRITE command (Class 10)
- [ ] Add CRC to frames
- [ ] Validate frame length

### Frame Parser
- [ ] Parse start byte (0x27 or 0x24)
- [ ] Extract length field
- [ ] Extract service ID (0xE7)
- [ ] Extract source (0xF8)
- [ ] Extract APDU (class, op-spec, data)
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
- [ ] Start pump (Sub 0x5600, Obj 0x603, value=1)
- [ ] Stop pump (Sub 0x5600, Obj 0x603, value=0)
- [ ] Read current mode/setpoint (Sub 0x5600, Obj 0x006)

### Control Modes
- [ ] Set constant pressure mode
  - [ ] Convert meters to Pascals
  - [ ] Validate range (0.5-10.0m)
  - [ ] Send SET command
- [ ] Set differential pressure mode
  - [ ] Convert meters to Pascals
  - [ ] Validate range
  - [ ] Send SET command
- [ ] Set constant flow mode (if supported)
  - [ ] Convert m³/h to appropriate units
  - [ ] Validate range
  - [ ] Send SET command
- [ ] Set proportional pressure mode
  - [ ] Validate range (0.0-1.0)
  - [ ] Send SET command

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
- [ ] Read current schedule
- [ ] Parse schedule entries
- [ ] Add schedule entry (day, start, end)
- [ ] Remove schedule entry
- [ ] Clear all schedules
- [ ] Enable schedule mode
- [ ] Disable schedule mode
- [ ] Validate time format (HH:MM)
- [ ] Validate day of week

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
