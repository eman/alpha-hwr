# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Major Architectural Refactor**
  - **Complete codebase restructure**: Moved from a monolithic client to a modular service-oriented architecture.
  - **New `core` layer**: Handles connection, authentication (`core/authentication.py`), session state (`core/session.py`), and transport (`core/transport.py`) independently.
  - **New `protocol` layer**: Separated frame building (`protocol/frame_builder.py`), parsing (`protocol/frame_parser.py`), and codec logic (`protocol/codec.py`). Added explicit support for both Class 3 (legacy) and Class 10 (modern) GENI protocols.
  - **New `services` layer**: Logic split into dedicated services: `TelemetryService`, `ControlService`, `ScheduleService`, `TimeService`, `HistoryService`, `EventLogService`, `DeviceInfoService`, `ConfigurationService`.
  - **New `client` facade**: `AlphaHWRClient` is now a thin facade that delegates to these specialized services, ensuring a cleaner API surface.
  - **New `cli` structure**: CLI commands now organized by domain (`cli/commands/`) using Typer.
  - **Documentation Overhaul**: Created `docs/reimplementation/` guide for porting the library, `docs/protocol/` for deep technical specs, and updated all user guides to reflect the new architecture. Added detailed packet trace analysis and architecture diagrams.
  - **Mock Pump Improvements**: Updated `MockPump` to support all protocol features including Class 7 strings, event logs, statistics, and complex schedule management, ensuring high-fidelity testing without hardware.

### Added

#### Service Enhancements (Latest)

- **Power-On Time History**
  - Added power-on time trend data to HistoryService (Object 53, SubID 454)
  - Extended TrendDataCollection model with `power_on_time_series` field
  - Updated history CLI to display power-on time trends in hours
  - CLI command: `alpha-hwr history trends` now includes power-on time data

- **BaseService Refactoring**
  - Created shared BaseService class to eliminate ~200 lines of duplicate code per service
  - All 8 services now inherit from BaseService
  - Shared helpers: `_read_class10_object()`, `_read_class7_string()`, `_build_geni_packet()`
  - Fixed critical bug in device statistics (incorrect offset after refactoring)

- **Event Log Service - Complete Protocol Decoding**
  - Fully decoded EventLogMetadata structure (SubID 10199, 7 bytes)
  - Metadata fields: cycle counter (uint16), available entries (uint16), max buffer size (uint16), reserved byte
  - Created analysis tools to correlate metadata with event entries
  - Updated protocol documentation with complete metadata structure
  - CLI commands: `alpha-hwr events list`, `alpha-hwr events show INDEX`, `alpha-hwr events metadata`

- **History Service - CLI Implementation**
  - New CLI commands for historical/trend data access
  - `alpha-hwr history trends [--detailed]` - Display flow/head/temperature trends
  - `alpha-hwr history timestamps [--count 10|100]` - Show cycle timestamps
  - Rich formatting with color-coded tables and panels
  - Supports both 10-cycle and 100-cycle historical data

### Changed

- **Control Service - Enhanced Safety and Reliability**
  - Added setpoint validation to all control mode setters
  - Pressure modes: validated 0.5-10.0m range
  - Speed mode: validated 500-4500 RPM range
  - Flow mode: validated 0.1-10.0 m³/h range
  - Improved error messages for out-of-range setpoints
  - Updated `_send_with_retry()` with proper response matching
  - Now uses `transport.query()` for reliable request/response transactions
  - Supports both acknowledged and fire-and-forget control commands

### Fixed

- **Device Statistics Bug**
  - Fixed statistics returning None after BaseService refactoring
  - Issue was incorrect data offset calculation in `_read_class10_object()`
  - All CLI commands now working correctly: `alpha-hwr device stats`

#### Phase 3: Advanced Control Investigation (Complete)

- **Comprehensive Control Mode Testing**
  - Systematically tested all 23 remaining control modes on ALPHA HWR hardware
  - Created automated investigation tool (`probe_all_modes.py`) with SubID discovery and mode switching tests
  - Result: 100% of remaining modes confirmed as NOT SUPPORTED by ALPHA HWR hardware
  - ALPHA HWR supports only 8 out of 32 GENI protocol control modes (25%)
  
- **Mode Investigation Findings**
  - Created comprehensive control mode support matrix in `docs/protocol/control_modes.md`
  - Documented why each unsupported mode is not available (sensor requirements, application mismatch)
  - All unsupported modes lack SubID configuration in Object 86
  - Unsupported modes fall into categories: chemical dosing, level control, specialized sensors, industrial applications
  
- **Phase 3 Strategy Documentation**
  - Created `docs/protocol/phase3_strategy.md` with investigation methodology
  - Categorized modes into 4 tiers by likelihood of support
  - Decision tree for implementation vs. documentation-only
  - Risk mitigation and time estimation (completed in under 1 hour)

- **Unsupported Modes (24 total):**
  - **Sensor Requirements:** Modes 11, 12, 26 (differential pressure/temperature sensors not present)
  - **Chemical Dosing:** Modes 16-19 (pools/industrial applications)
  - **Level Control:** Modes 9, 22 (tank/sump applications)
  - **Specialized:** Modes 7, 10, 20, 21, 23-25, 27-30, 128 (industrial/special applications)

#### Phase 4: Diagnostics & CEOPS Investigation (Complete)

**Result: 0% of planned features available**

- **Comprehensive Object Scanning**
  - Created automated scanner (`probe_phase4_objects.py`) to test Objects 93-106
  - Tested 14 objects for CEOPS/diagnostics/events/historical data capabilities
  - Scanned 9 SubIDs per object (0, 1, 2, 3, 4, 5, 10, 100, 1000)
  - Result: 0 objects available (0/14 objects, 0/126 SubID requests successful)
  - Created `docs/protocol/phase4_strategy.md` with investigation methodology
  - Created `docs/protocol/phase4_results.md` with comprehensive findings (400+ lines)
  
- **CEOPS Features: NOT AVAILABLE**
  - Object 94 (ceops_config): No data - no pump role selection capability
  - Object 95 (pump_role): No data - no multi-pump role assignment
  - Object 96 (pump_coordination): No data - no pump cycling/load balancing
  - Object 97 (air_venting_config): No data - no System Air Venting (Mode 128) configuration
  - Conclusion: ALPHA HWR is single-pump only, no multi-pump coordination hardware
  
- **Diagnostic Features: NOT AVAILABLE**
  - Object 98 (motor_diagnostics): No data - no motor health metrics
  - Object 99 (sensor_diagnostics): No data - no sensor validation
  - Object 100 (communication_diagnostics): No data - no BLE quality metrics
  - Object 101 (system_diagnostics): No data - no self-test routines
  - Conclusion: Only basic telemetry available (already implemented in Phase 0)
  
- **Event System: NOT AVAILABLE**
  - Object 102 (event_log): No data - no event storage capability
  - Object 103 (alarm_history): No data - no historical alarm/warning records
  - Object 104 (operation_events): No data - no timestamped operation events
  - Conclusion: Only current alarm/warning state available (already implemented in Phase 0)
  
- **Historical Data: NOT AVAILABLE**
  - Object 105 (performance_trends): No data - no time-series performance data
  - Object 106 (data_log): No data - no data export capability
  - Conclusion: Client-side logging required for trend analysis
  
- **Alternative Solutions Documented**
  - Client-side logging recommendations for event tracking
  - External monitoring integration patterns (Home Assistant, InfluxDB, Grafana)
  - Application-layer coordination strategies for multi-pump systems
  - Real-time telemetry streaming as basis for custom monitoring
  
- **Known Issue: Object 93 Intermittent Availability**
  - Object 93 (operation_history_pump_obj) successfully read in Phase 1 (operating hours, start count)
  - Same object returned no data in Phase 4 scanning attempts
  - **RESOLVED:** Issue was with probe script using non-existent internal API method
  - Object 93 confirmed FULLY FUNCTIONAL via proper public API (`read_statistics()`)
  - Feature is stable, reliable, and not state-dependent
  - Successfully tested with rapid sequential reads and various pump states
  
- **Conclusion**
  - ALPHA HWR is specialized residential pump with no advanced professional features
  - All needed features for residential use already implemented in Phases 0-2
  - Advanced diagnostics, event logging, and multi-pump features reserved for professional models
  - Phase 4 complete with no implementation needed - documentation only

#### Phase 2: Schedule Management (Complete)

- **Weekly Schedule Reading and Writing**
  - Read weekly schedules from all 5 layers (SubIDs 1000-1004)
  - Write schedule entries with time windows (e.g., Monday 06:00-08:00)
  - Enable/disable global schedule with `set_schedule_enabled()`
  - CLI commands: `alpha-hwr schedule [--enable|--disable|--set-entry|--clear-day|--clear-layer]`
  - Export/import schedules as JSON for backup/restore
  - Comprehensive validation for overlapping time windows and midnight-crossing schedules
  - Support for multiple schedule layers (0-4) for advanced configurations
  - Clear operations: `clear_schedule_entry()` (single day) and `clear_schedule_layer()` (entire layer)

- **Configuration Backup and Restore**
  - Save pump configuration including schedules, modes, and setpoints to JSON
  - Restore configuration from backup file with validation
  - CLI commands: `alpha-hwr config backup` and `alpha-hwr config restore`
  - Automatic validation ensures configuration is compatible before restore

- **Schedule Protocol Implementation**
  - Class 10 Object 84 for schedule data access
  - OpSpec 0x93 for enable/disable operations (Type 218 ClockProgramOverview, 10 bytes)
  - OpSpec 0xB3 for schedule writes (Type 222 ClockProgramWeekDayInterval, 42 bytes)
  - Automatic multi-chunk packet splitting for BLE ATT MTU (20-byte chunks with 10ms delay)
  - Keep-alive burst mechanism for reliable large data reads
  - Object ID before SubID ordering for write operations (reversed from reads)

#### Phase 1: Essential Control Features (Complete)

- **Setpoint Limits Reading** (`alpha-hwr setpoint --limits`)
  - Read min/max/default setpoint limits from factory configuration (Class 10, Object 86)
  - Supports Constant Pressure, Proportional Pressure, Constant Speed, and Constant Flow modes
  - New `read_setpoint_limits(control_mode)` method returns tuple of (min, max, default)
  - Enhanced `SetpointInfo` model with `min_setpoint` and `max_setpoint` fields
  - New `get_limits_display()` method for unit-converted limit display
  - CLI integration with `--limits` flag shows valid setpoint range

- **Cumulative Statistics Reading** (`alpha-hwr stats`)
  - Read pump operating hours and start count from Class 10, Object 93, Sub-ID 1
  - New `read_statistics()` method returns `Statistics` model
  - Operating time automatically converted from seconds to hours
  - **Note:** Cumulative energy (kWh) is not available on ALPHA HWR (Object 77 not implemented)
  - Instantaneous power (W) available via telemetry streaming
  - See `docs/protocol/energy_power.md` for energy tracking limitations and workarounds
  - CLI displays formatted statistics with visual separators
  - New `Statistics` model in `models.py`

- **Setpoint Validation**
  - New `validate_setpoint(value, control_mode, strict)` method validates against limits
  - Automatic validation integrated into all setter methods
  - Two modes: strict (fails on missing limits) and non-strict (logs warning, proceeds)
  - Non-strict mode default ensures backward compatibility with tests/mocks

- **Proportional Pressure Mode Control**
  - New `set_proportional_pressure(value_m)` method for proportional pressure mode
  - Automatic unit conversion (meters → Pascals) and validation
  - CLI command: `alpha-hwr control set-proportional-pressure --value 1.2`
  - Uses Class 3 Command 0x17 (23) for setpoint transmission

- **Constant Speed Mode Control**
  - New `set_constant_speed(value_rpm)` method for constant speed mode
  - Automatic validation against RPM limits from factory config
  - CLI command: `alpha-hwr control set-speed --value 2500`
  - Uses Class 3 Command 0x04 (4) for setpoint transmission

- **AutoAdapt Mode Control**
  - New `set_autoadapt(value_m)` for generic AutoAdapt mode (mode 5) - **Limited support**, see warnings
  - New `set_autoadapt_radiator(value_m)` for AutoAdapt Radiator mode (mode 13) - **Fully supported**
  - New `set_autoadapt_underfloor(value_m)` for AutoAdapt Underfloor mode (mode 14) - **Fully supported**
  - New `set_autoadapt_combined(value_m)` for AutoAdapt Radiator+Underfloor mode (mode 15) - **Fully supported**
  - All AutoAdapt modes support automatic validation and unit conversion
  - CLI commands: `set-autoadapt`, `set-autoadapt-radiator`, `set-autoadapt-underfloor`, `set-autoadapt-combined`
  - Factory configuration Sub-IDs: Generic (11), Radiator (19), Underfloor (21), Combined (23)
  - All modes use pressure setpoints in meters (converted to Pascals internally)
  - Mode 5 (generic AutoAdapt) has limited/unreliable mode switching - use specific variants (13-15) instead
  - Mode 26 (Proportional Differential Pressure) **NOT supported** by ALPHA HWR hardware

#### Phase 0: Status Monitoring Features

- **Alarm/Warning System with Descriptions** (`alpha-hwr alarms`)
  - Read current alarm and warning codes from pump (Class 2 registers 158/156)
  - Comprehensive error code lookup table with 98+ error codes from GENI profile
  - Human-readable descriptions automatically included in CLI output
  - New `ERROR_CODES` dictionary in `constants.py` for programmatic access
  - Enhanced `AlarmInfo` model with `alarm_description` and `warning_description` fields

- **Current Setpoint Reading with Unit Conversion** (`alpha-hwr setpoint`)
  - Read active setpoint value from Class 10, Object 86, Sub-ID 6
  - Intelligent unit conversion based on control mode:
    - Pressure modes: Pascals → meters of water column (Pa ÷ 9806.65)
    - Flow modes: m³/h (no conversion)
    - Speed modes: RPM (no conversion)
    - Temperature modes: °C (no conversion)
  - New `SetpointInfo.get_display_value()` method returns `(value, unit)` tuple
  - CLI displays both converted and raw values for transparency

- **Device Information Reading** (`alpha-hwr info`)
  - Read product family, type, and version from BLE advertisement data
  - Scans before connection for fast, non-intrusive device identification
  - Displays human-readable product names (e.g., "Grundfos ALPHA HWR")
  - No authentication required

- **Enhanced Control Mode Display** (`alpha-hwr mode`)
  - Improved formatting with success indicator (✅)
  - Fixed byte offset bug (now reads from correct offset after 3-byte header)
  - All 31 control modes now properly recognized

### Fixed

- **Phase 2: Schedule Write Operations**
  - Fixed `set_schedule_entry()`, `set_weekly_schedule()`, `clear_schedule_entry()`, and `clear_schedule_layer()` to use correct OpSpec 0xB3 format
      - Previous implementation used OpSpec 0x90 which claimed success but didn't actually modify pump schedule data
      - Discovered correct format through protocol analysis
      - Key changes: OpSpec 5 (0xB3) instead of OpSpec 4, Object ID before SubID, Type 222 header (0xDE 0x01 0x00)  - All schedule write operations now verified to work correctly on hardware
  - Added 7 new wire protocol tests to verify packet format matches captures

- **Phase 2: BLE Packet Splitting for Schedule Writes**
  - Fixed packet splitting logic to handle 3+ chunks (59-byte schedule write packets split as 20+20+19)
  - Previous implementation only supported 2-chunk splits, causing schedule writes to fail silently
  - All schedule write operations now work correctly on hardware (8/8 hardware tests passing)

- **Phase 1: Control Mode Reading**
  - Fixed incorrect byte offset in `get_control_mode()` (was reading byte 2, now reads byte 5)
  - Added missing control modes to `ControlMode` enum (previously only had 5, now has 31)
  - Properly handles Class 10 response 3-byte header `[00 00 XX]` that must be skipped

### Changed

- **Active Control Enhancement**
  - `set_constant_pressure()` and `set_constant_flow()` now include automatic validation
  - Enhanced docstrings with clear parameter descriptions and return value semantics
  - Validation errors logged with clear error messages indicating out-of-range values
  - Added three AutoAdapt mode setters with full validation support

- **API Enhancements**
  - `AlarmInfo` model now includes `alarm_description` and `warning_description` fields
  - `SetpointInfo` model now includes `get_display_value()` and `get_limits_display()` methods
  - `SetpointInfo` model expanded with optional `min_setpoint` and `max_setpoint` fields
  - `ERROR_CODES` dictionary exported from main `__init__.py` for library users
  - CLI alarm command now shows descriptions with improved formatting
  - CLI control command expanded with new actions: `set-proportional-pressure`, `set-speed`, `set-autoadapt-radiator`, `set-autoadapt-underfloor`, `set-autoadapt-combined`
  - All setter methods now validate `--value` argument is provided

- **Documentation**
  - Updated README.md with Phase 1 CLI commands and library examples
  - Added comprehensive examples for control mode setting with validation
  - Updated feature list to include "Active Control" capabilities
  - Documented all AutoAdapt modes with CLI and library examples
  - Added detailed schedule protocol documentation in `docs/protocol/schedules.md`
  - Created `docs/protocol/ble_architecture.md` - Comprehensive guide to BLE protocol layers
  - Created `docs/protocol/device_info.md` - Device information and Class 7 limitations
  - Created `docs/protocol/energy_power.md` - Energy consumption limitations and workarounds
  - Created `docs/protocol/autoadapt_modes.md` - AutoAdapt mode support status and testing results
  - Updated schedules.md with extensive multi-layer documentation and best practices
  - Documented schedule layer architecture: 5 independent SubIDs (1000-1004) within Object 84
  - Added practical examples for weekday/weekend separation, seasonal adjustments, and overlapping schedules
  - Documented Object 77 (energy) hardware testing results showing it's not supported on ALPHA HWR
  - Documented Mode 5 (AUTO_ADAPT) limited support and Mode 26 (PROPORTIONAL_DIFF_PRESSURE) unsupported status

### Technical Notes

#### Protocol Discoveries

1. **Class 10 Object Response Format**: All Class 10 object reads return a 3-byte header `[00 00 XX]` that must be skipped before parsing object data. Always start reading at byte index 3.

2. **Setpoint Encoding**: Setpoint values are transmitted as:
   - Pressure modes: Pascals (IEEE 754 float, big-endian)
   - Flow modes: m³/h (IEEE 754 float, big-endian)
   - Speed modes: RPM (IEEE 754 float, big-endian)
   - Temperature modes: °C (IEEE 754 float, big-endian)

3. **Factory Configuration Objects** (New in Phase 1):
   - Object 86 contains multiple Sub-IDs for different control mode configurations
   - Type 301 (ControlModeFactoryConfiguration): min/max/default setpoints + PID parameters
   - Type 302 (ControlModeUserConfiguration): current setpoint + user PID overrides
   - Sub-ID mapping for factory configs:
     - CONSTANT_SPEED (2): Sub-ID 13
     - CONSTANT_PRESSURE (0): Sub-ID 15
     - PROPORTIONAL_PRESSURE (1): Sub-ID 17
     - CONSTANT_FLOW (8): Sub-ID 39
     - **AUTO_ADAPT (5): Sub-ID 11** (uint16 format, not float32)
     - AUTO_ADAPT_RADIATOR (13): Sub-ID 19
     - AUTO_ADAPT_UNDERFLOOR (14): Sub-ID 21
     - AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR (15): Sub-ID 23
   - Structure: `[header(3)][default(4)][min(4)][max(4)][resulting_min(4)][pid_kp(4)][pid_windup(4)][pid_lpf(4)]`
   - AutoAdapt modes tested on real hardware: Radiator (1.83-4.57m), Underfloor (1.83-4.57m), Combined (1.83-4.57m)
   - **Mode 5 uses uint16 format**: min=14468 Pa (1.48m), max=14935 Pa (1.52m), default=14695 Pa (1.50m)

4. **Statistics Object Structure** (New in Phase 1):
   - Object 93, Sub-ID 1 (operation_history_pump_obj)
   - Total response: 31 bytes (including 3-byte header)
   - Bytes 0-2: Header `[00 00 XX]` (always skip)
   - Bytes 3-10: Unknown (8 bytes)
   - Bytes 11-14: Operating time in seconds (uint32, big-endian)
   - Bytes 15-18: Start count (uint32, big-endian)
   - Bytes 19-30: Unknown (12 bytes, possibly reserved for future use)

5. **Device Info Location**: Product family, type, and version are NOT available via GENI Class 2 registers (IDs 148-150 return NACK). Instead, they are broadcast in BLE advertisement service data under UUID `0000fe5d-0000-1000-8000-00805f9b34fb` at bytes 3-5.

6. **Error Code 160**: Not documented in GENI profile `geni_profile_52_7.xml`. Appears as both alarm and warning on test pump. May be undocumented or a special system indicator.

7. **Class 7 Strings**: Class 7 string protocol is NOT supported by ALPHA HWR pumps via BLE. Attempts to read firmware version or serial number via Class 7 result in echo responses rather than string data.

8. **Schedule Protocol** (Discovered via packet capture analysis):
   - Object 84 contains schedule data across multiple SubIDs:
     - SubID 1: ClockProgramOverview (Type 218, 10 bytes) - enable/disable status
     - SubIDs 1000-1004: ClockProgramWeekDayInterval (Type 222, 42 bytes) - 5 schedule layers
   - **OpSpec encoding critical for success:**
     - OpSpec 0x93 (OpSpec 4, Length 19): Enable/disable operations with Type 218
     - OpSpec 0xB3 (OpSpec 5, Length 19): Schedule write operations with Type 222
     - Wrong OpSpec causes pump to acknowledge but ignore data changes
   - **Packet structure for schedule writes:**
     - Format: `[Class][OpSpec][ObjID][SubID_H][SubID_L][Reserved][Type(3)][Size(2)][Data(42)]`
     - Object ID comes BEFORE SubID (reversed from some other operations)
     - Type header: 0xDE 0x01 0x00 for Type 222
     - Size field: 0x00 0x2A (42 bytes in big-endian)
   - **Schedule data structure:** 7 days × 6 bytes = 42 bytes
     - Per-day: `[enabled(1)][action(1)][start_hour(1)][start_min(1)][end_hour(1)][end_min(1)]`
     - Day order: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday
   - **Packet splitting required:** 59-byte packets split as 20+20+19 bytes with 10ms delays

### Testing

- All 204 unit tests passing (up from 195 after Phase 1)
- Integration tests with real ALPHA HWR hardware verified:
  - **Phase 0 features:**
    - Alarm code 160 detected and described as "Unknown Error (Not in GENI Profile)"
    - Setpoint 9804 Pa correctly converted to 1.00 m
    - Device info correctly reads Family 52, Type 7, Version 2
    - Control mode correctly shows CONSTANT_PRESSURE (0)
  - **Phase 1 features:**
    - Setpoint limits successfully read for all 7 supported modes
    - Validation correctly accepts values within range (1.5m for CP mode)
    - Validation correctly rejects values outside range (5.0m for CP mode)
    - Statistics reading: 421.4 hours, 624 starts
    - AutoAdapt Radiator limits: 1.83-4.57 m
    - AutoAdapt Underfloor limits: 1.83-4.57 m
    - AutoAdapt Combined limits: 1.83-4.57 m
  - **Phase 2 features:**
    - Schedule enable/disable verified working on hardware
    - Schedule read operations across all 5 layers (1000-1004)
    - Schedule write operations (set_entry, clear_day, clear_layer) verified working
    - Configuration backup/restore verified with JSON export/import
    - Wire protocol tests verify packets match expected protocol captures
    - Added 7 new schedule write protocol tests
    - Multi-layer schedule support tested (weekday/weekend separation)
  - **Phase 3 features:**
    - Tested all 23 remaining control modes systematically
    - SubID discovery: scanned Object 86 SubIDs 0-65 for each mode
    - Mode switching: attempted to switch to each control mode
    - Result: 0 SubIDs found, 0 modes switchable, 0 modes supported
    - Confirmed ALPHA HWR is specialized for heating applications only
    - Investigation tool: `probe_all_modes.py` with JSON output
- All tox environments passing (py313, type, lint, basedpyright)

---

## [0.1.0] - 2025-01-XX

Initial release with basic monitoring capabilities.

### Added
- BLE connection to Grundfos ALPHA HWR pumps
- Telemetry reading (Flow, Head, Power, Temperature, Voltage/Current, Speed)
- Passive monitoring mode with continuous data stream
- CLI interface for monitoring
- AsyncIO-based architecture using `bleak`
- Type-safe API with Pydantic models
- Cross-platform device addressing (macOS UUID / Linux+Windows MAC)
