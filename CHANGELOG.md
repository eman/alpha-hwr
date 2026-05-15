# Changelog


## [Unreleased]


## [0.6.0] - 2026-05-15

### Fixed

- **Authentication extension packet ordering**: `send_extension_packets()` was
  sending EXTEND_1 and EXTEND_2 concurrently (via `asyncio.TaskGroup`) with the
  wrong submission order. The correct sequence is EXTEND_1 then EXTEND_2 with a
  50ms gap. Parallel or reversed delivery caused premature disconnection (#24).
- **`SetpointInfo.control_mode` type**: Field was typed as bare `int`, causing
  `AttributeError` on `.name` access. A `field_validator` now coerces known
  values to `ControlMode`; unknown values remain as `int`.
- **Double Pa→m conversion**: `ControlService.get_mode()` already converted
  pressure setpoints from Pascals to metres, but `get_display_value()` and
  `get_limits_display()` divided by 9806.65 a second time. Both model methods
  now return the stored value directly for pressure modes.
- **Disconnection guard in `read_once()`**: Added `transport.is_connected()`
  checks before the flow/pressure and temperature queries. A mid-sequence
  disconnect now returns partial telemetry instead of raising a `BleakError`.

### Changed

- **Minimum Bleak version bumped to 3.0.0** (previously `>=0.19.0`). Bleak 3.0
  removed the `adapter=` keyword argument; the library now uses the Bleak 3.x
  `bluez={"adapter": ...}` form on Linux and ignores the argument on other
  platforms. Users pinned to Bleak 0.x–2.x must upgrade.

## [0.5.0] - 2026-02-21

### Fixed

- **Missing `PROPORTIONAL_PRESSURE` in `_MODE_BYTE_MAP`**: Added mode value `1` → byte `0x01`, preventing a `KeyError` when starting or stopping the pump in proportional pressure mode.
- **Alarm/warning descriptions not populated**: `read_alarms()` now resolves each active alarm and warning code against `ERROR_CODES`, populating `alarm_description` and `warning_description` as comma-separated human-readable strings. Unknown codes fall back to `"Unknown (<code>)"`.

### Changed

- **CLI alarm panel**: The alarm status panel now lists every active alarm and warning code with its description rather than showing only a single code.

### Tests

- Extended `test_read_alarms` to assert `alarm_description` and `warning_description` are correctly populated.
- Added `test_read_alarms_unknown_code_fallback` to verify the `"Unknown (<code>)"` fallback for codes not present in `ERROR_CODES`.

## [0.4.0] - 2026-02-14

### Fixed

- **Protocol documentation errors in `04_set_mode.md`**:
  - Corrected float encoding example: `0x46E5B000` is 29400.0 Pa (3.0 m), not 14710.0 Pa (1.5 m). Updated to correct hex `46 65 D7 E6`.
  - Fixed Step 1 packet length byte: `0x14` (20), was incorrectly `0x12` (18).
  - Fixed Step 2 packet length byte: `0x0C` (12), was incorrectly `0x10` (16).
  - Fixed Step 2 OpSpec byte: `0x88`, was incorrectly `0x84`.
  - Aligned DHW Cycle Time suffix to match code: `38 C6 76 EF` (was `38 C6 70 00`).
- **`set_clock()` completely broken**: Rewrote to use standard Class 10 SET via `build_data_object_set(0x5E00, 0x6401, data)` with Type 322 payload. The old implementation used a non-standard frame format missing ServiceID/Source bytes, which the pump silently rejected. Updated module docstring with correct TypeScript and Rust reference implementations.
- **`ControlService._current_mode` not synced from pump**: `get_mode()` now updates `_current_mode` from the actual pump state, so `start()`/`stop()` send the correct mode byte.
- **Missing `PROPORTIONAL_PRESSURE` in `_MODE_SUFFIX_MAP`**: Added mode `0x01` with suffix `45 65 70 00`, preventing silent command rejection when starting/stopping in proportional pressure mode.
- **Dead code in `ControlService._send_with_retry`**: Removed unreachable `logger.debug()` after `return False`.
- **`build_write_request` CRC scope**: CRC now excludes the start byte (`packet[1:]`), consistent with all other frame builders.
- **OpSpec overflow in `build_data_object_set`**: Added guard that raises `ValueError` when payload exceeds 6-bit OpSpec maximum (63). Callers with large payloads must use `override_op`.
- **Test vector comment**: Fixed "little-endian" to "big-endian" for ObjID `0x005D` in `frame_parser.py`.
- **`TelemetryObject` tuple order**: Changed from `(SubID, ObjID)` to `(ObjID, SubID)` to match the decoder match pattern in `TelemetryDecoder.decode()` and `FrameParser.is_telemetry_frame()`.
- **MockPump `_build_ack_response` length byte**: Fixed LEN from `0x06` to `0x04` so the Transport's packet assembly logic doesn't hang waiting for 2 extra bytes that never arrive. Also fixed `_build_error_response` and `_build_class2_response` length calculations.
- **MockPump `_handle_set_clock`**: Updated to handle new Class 10 SET format (was using old non-standard format).
- **Test performance: 5-second BLE scan in every mock test**: Patched `_scan_advertisement_data` in all test fixtures to skip the real `BleakScanner.discover(timeout=5.0)` call. Integration tests dropped from 144s to 35s.

### Deprecated

- **`EventLogService.get_cycle_timestamps()`**: Use `HistoryService.get_cycle_timestamps()` instead. This method violated the service layer architecture by creating a `HistoryService` internally.

### Changed

- **Style**: Added `from __future__ import annotations` to `utils.py`, `constants.py`, `models.py`. Replaced `Optional` with `| None` in `utils.py`.

### Added

- **Refactored Control Modes and Setpoints**:
  - Implementation of the 5 primary ALPHA HWR control modes using Class 10 (Object 0x0601) for improved reliability.
  - Added support for **AUTOADAPT toggle** in Temperature Range Control (Mode 27).
  - New CLI command `set-proportional` for proportional pressure mode.
  - Enhanced CLI `set-mode` with aliases and better help text.
- **Full implementation of Mode 25 (DHW_ON_OFF_CONTROL / Cycle Time Control)**:
  - Added support for reading and writing cycle time parameters (on/off minutes) to the library.
  - Added CLI commands: `alpha-hwr control set-cycle-time` and `alpha-hwr control get-cycle-time`.
  - Added comprehensive integration tests using `MockPump`.
  - Updated `MockPump` to simulate Mode 25 protocol behavior.

### Changed

- **Test Infrastructure and Dependencies**:
  - Refactored `pyproject.toml` to use a dedicated `test` optional dependency group.
  - Updated GitHub Actions CI to install test extras and ensure all required plugins are present.
  - Improved `tests/conftest.py` to explicitly load `pytest-benchmark`, ensuring fixture availability during parallel execution.
  - Unified `_send_configuration_commit` implementation in `BaseService` for all service modules.

### Fixed

- **Start/Stop Commands**: Fixed start and stop commands silently failing.
  The control payload now uses the correct mode-specific suffix bytes
  instead of encoding `0.0` (which the pump firmware rejected). The CLI
  also reads the pump's current control mode before sending start/stop to
  avoid accidentally switching modes.
- **Control Mode Setpoints**: Fixed floating-point precision issues in integration tests by using `pytest.approx`.
- **MockPump Reliability**: Fixed missing logger definitions and improved OpSpec 0xB3 ID parsing.
- **CI Test Failures**: Resolved "fixture not found" errors by properly managing benchmark plugin loading.

### Documentation

- Documentation site version now sourced from `pyproject.toml` and auto-
  deployed via GitHub Actions to keep https://eman.github.io/alpha-hwr up
  to date.

## [Unreleased] - 2026-02-01

### Added

- **BLE connection to Grundfos ALPHA HWR pumps**
- **Telemetry reading** (Flow, Head, Power, Temperature, Voltage/Current, Speed)
- **Passive monitoring mode** with continuous data stream
- **CLI interface** for monitoring and control
- **AsyncIO-based architecture** using `bleak`
- **Type-safe API** with Pydantic models
- **Cross-platform device addressing** (macOS UUID / Linux+Windows MAC)

#### Service Enhancements

- **Power-On Time History**
  - Added power-on time trend data to HistoryService (Object 53, SubID 454)
  - Extended TrendDataCollection model with `power_on_time_series` field
  - Updated history CLI to display power-on time trends in hours
- **Event Log Service - Complete Protocol Decoding**
  - Fully decoded EventLogMetadata structure (SubID 10199, 7 bytes)
  - CLI commands: `alpha-hwr events list`, `alpha-hwr events show INDEX`, `alpha-hwr events metadata`
- **History Service - CLI Implementation**
  - New CLI commands for historical/trend data access
  - `alpha-hwr history trends [--detailed]` - Display flow/head/temperature trends
  - `alpha-hwr history timestamps [--count 10|100]` - Show cycle timestamps
- **Schedule Management**
  - Read/write weekly schedules from all 5 layers (SubIDs 1000-1004)
  - Enable/disable global schedule with `set_schedule_enabled()`
  - CLI commands: `alpha-hwr schedule [--enable|--disable|--set-entry|--clear-day|--clear-layer]`
  - Export/import schedules as JSON for backup/restore
- **Configuration Backup and Restore**
  - Save/Restore pump configuration including schedules, modes, and setpoints to JSON
  - CLI commands: `alpha-hwr config backup` and `alpha-hwr config restore`

### Changed

- **Major Architectural Refactor**
  - **Complete codebase restructure**: Moved from a monolithic client to a modular service-oriented architecture.
  - **New `core` layer**: Handles connection, authentication, session state, and transport independently.
  - **New `protocol` layer**: Separated frame building, parsing, and codec logic. Added support for Class 3 and Class 10 GENI protocols.
  - **New `services` layer**: Logic split into dedicated services (Telemetry, Control, Schedule, etc.).
  - **New `client` facade**: `AlphaHWRClient` delegates to specialized services.
  - **New `cli` structure**: CLI commands organized by domain using Typer.
- **Control Service - Enhanced Safety and Reliability**
  - Migrated primary control modes (Constant Pressure, Speed, Flow, Proportional Pressure) from Class 3 to **Class 10 (Object 0x0601)** for better hardware compatibility.
  - Added setpoint validation to all control mode setters
  - Improved error messages for out-of-range setpoints
  - Now uses `transport.query()` for reliable request/response transactions

### Fixed

- **Profile Parser**: Resolved MyPy type-checking errors and improved XML parsing robustness by adding null checks for the root element in `profile_parser.py`.
- **Device Statistics Bug**: Fixed statistics returning None after BaseService refactoring.
- **Schedule Write Operations**: Fixed to use correct OpSpec 0xB3 format discovered through protocol analysis.
- **BLE Packet Splitting**: Fixed packet splitting logic to handle 3+ chunks for large data writes.
- **Control Mode Reading**: Fixed incorrect byte offset in `get_control_mode()`.
