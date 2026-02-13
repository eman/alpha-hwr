# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
