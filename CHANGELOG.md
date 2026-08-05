# Changelog


## [Unreleased]

### Added

- **Verified writes** (`WriteResult`). Every write now goes through one
  serialized path that queues operations, runs them strictly one at a time,
  builds each frame from the arguments it was given rather than a cache
  that may have moved, and decides the outcome by reading the pump back.
  A write settles as `accepted`, `clamped`, `rejected`, `invalid`,
  `timeout` or `superseded`, carrying both what the pump stored and what
  was asked for.

  The ACK is not the verdict: this pump *clamps* values it dislikes rather
  than refusing them - 600 RPM is stored as 1650 and 4400 as 3671 - so a
  bare success cannot tell a caller what happened. `result.ok` treats a
  clamp as written, because the pump did take the command.

  `ControlService` gains `set_enabled()`, `set_setpoint()`,
  `set_mode_verified()`, `set_temperature_range()` and `set_cycle_times()`
  returning `WriteResult`. The bool-returning setters remain as the wire
  primitives underneath.

- **`client.is_ready` and `wait_until_ready()`.** Some writes carry fields
  the caller did not set - the temperature range writes min, max and
  AutoAdapt together - and can only preserve them by knowing what the pump
  currently holds. The client reads that once after authenticating; until
  it has, those writes are refused rather than run against a guess. This is
  the signal to wait for before driving the pump programmatically, in place
  of an arbitrary settle delay.

- **Single events and vacations** (`client.single_events`). One-off
  scheduled runs, and `Stop` events that hold the pump off across a date
  range. Slot capacity is read from the pump rather than assumed - the unit
  this was developed against exposes 5, not the 35 the sub-id range
  suggests - and a free slot is chosen only after reading them all, since
  an unread slot looks empty.

- **`client.get_run_state()` / `set_run_state()`** and the `RunState`
  model. The run flag and schedule flag are written independently but the
  pump couples them: the motor runs only when the run state is AUTO *and*
  the schedule is off or a window is open. That leaves one combination -
  stopped with a schedule armed - which never runs and reports no fault.
  It is now named (`stalled`), detectable, and impossible to pass through
  accidentally: `set_run_state()` writes only the flags that differ, in an
  order that never routes through it.

- **`docs/protocol/bench_findings.md`** - what was measured against a real
  pump, and how, so a future disagreement can be settled by repeating a
  measurement rather than re-reading the code.

- **Central response matching** (`alpha_hwr.protocol.matcher`): a single
  stateless place that decides which notification answers which outstanding
  command, replacing the six ad-hoc byte predicates scattered across the
  services. It encodes the pump's actual firmware behaviour - bare Class 3/7
  acknowledgements (`[03 00]` executed vs `[03 01 xx]` descriptor-only),
  Class 10 write acks that carry no identifiers, the Sub-ID-0 wildcard, the
  inconsistent identifier field order, and the register-read operation
  specifiers that belong to the telemetry decoder rather than to a queued
  read. `Transport.send_command()` pairs a frame with a `Command` describing
  what reply to accept, and every service now goes through it - the
  per-callsite predicates in `base`, `control`, `telemetry`, `time` and
  `schedule` are gone. `Command.for_request()` derives the expected class
  from the frame being sent, so a Class 3 command can no longer be
  satisfied by a Class 10 notification that happens to arrive first.

- **Replies are matched by the pump's type code, measured per object.**
  `RESPONSE_IDENTIFIERS` records what the pump actually answers each object
  read with, captured from an ALPHA HWR on 2026-08-04 and identical across
  two runs; range ends were checked rather than extrapolated, which is how
  the power-on-time trend turned out to use a different type from the other
  three. All sixteen objects the library reads were verified end to end
  against hardware.

  This replaced an inherited filter that was rejecting replies **by payload
  length**. The set carried over as "register-read operation specifiers",
  `{0x30, 0x2B, 0x14, 0x2E, 0x2D, 0x09}`, is really the payload sizes 48,
  43, 20, 46, 45 and 9: in a *response* the frame's second byte is a length
  field, not an operation specifier - measured across 13 objects and 10
  distinct values, the operation bits are always `00` and
  `len(frame) == (byte5 & 0x3F) + 8` holds without exception. That is why
  the event log, whose entries carry a 20-byte payload, had to be exempted
  from the filter by hand. The `allow_register_read` flag is gone with it.

- **The Sub-ID-0 wildcard is gone.** It was inherited as a firmware quirk
  ("the pump answers with Sub-ID 0, so match on the other field"), but the
  pump never echoes the Sub-ID it was asked for at all - it answers with a
  type code, and a zero in the first identifier field is that object's real
  value. Treating it as a wildcard was an active bug: the temperature-range
  config (`0x0003, 0xF402`) and an event log entry (`0x0000, 0xF402`) share
  a type code and differ only in the field the rule discarded, so each could
  answer the other's read.

- **`MockPump` answers with the real type codes.** It previously echoed the
  request's Object/Sub, which no reply from the real device ever does - so
  any matching logic it exercised was tested against behaviour the pump does
  not have.

- **One GENI frame builder.** `FrameBuilder.build_geni_frame()` is now the
  single place the frame header and CRC are assembled; the three hand-rolled
  copies in `BaseService` and `ScheduleService` delegate to it. A byte-level
  test of one of those copies used to prove nothing about the others -
  `tests/unit/protocol/test_frame_assembly.py` now pins the layout against
  the captured authentication frames. `FrameBuilder.build_class10_object_read()`
  addresses a configuration object as an Object/Sub pair (the same bytes as
  the equivalent 24-bit register read).

- **Event-driven disconnect detection**: the client now registers bleak's
  `disconnected_callback`, so a dropped link is observed as it happens
  instead of the next time a read fails. `Transport.add_disconnect_handler()`
  registers callbacks; they run before the rest of the teardown, so anything
  holding a pending result can settle it before the state it would settle
  from is discarded.

### Changed

- **BREAKING: Remote Mode is removed.** `enable_remote_mode()`,
  `disable_remote_mode()` and the `control enable-remote` /
  `control disable-remote` CLI commands are gone. On the ALPHA, engaging
  Remote *takes control away* from the BLE link for ~35-45 s before
  self-cancelling, and the pump accepts commands perfectly well in Local -
  so there was harm and no demonstrated benefit. Reading remote/local state
  still works, and is now meaningful for the first time (see Object 86
  Sub 7 below).

- **BREAKING: generic AutoAdapt (mode 5) now raises.** The pump has no wire
  byte for it, and the mode map's fallback was Constant Speed - so
  `set_autoadapt()` put the pump into a different mode and reported
  success. The addressable variants (radiator, underfloor, combined) are
  now in the map, where they were also falling through to the same
  fallback. An unmapped mode raises `ValueError` instead of substituting
  one.

- **`set_temperature_range_control(autoadapt=...)` defaults to preserving
  the pump's setting** rather than `True`. The three fields share one
  write, so the old default silently turned AutoAdapt back on every time a
  bound was adjusted.

### Fixed

- **Every configuration commit switched the schedule off.**
  `_send_configuration_commit()` sent a hardcoded APDU whose
  ClockProgramOverview had `clock_program_enabled = 0x00`. A commit follows
  every setpoint write and every control request, so changing any setpoint
  silently disabled the user's weekly schedule - the overview is written
  whole, and the enabled flag is part of it. The commit is now built by
  reading the pump's current overview and writing it back; if the overview
  cannot be read, no commit is sent at all, because skipping a flush is
  recoverable and overwriting the schedule state is not. Found by writing
  to a real pump: a setpoint change disabled a live schedule.

- **Pump start/stop no longer asserts a mode and a setpoint.** `start()`
  and `stop()` send the Class 3 run-state commands (`[03 81 06]` /
  `[03 81 05]`), which carry neither. They previously went through the
  fused control object with no setpoint, so every start wrote the mode
  map's default suffix - `45 65 70 00`, which decodes to exactly 3671.0 -
  over whatever the mode's setpoint had been. That value is not an inert
  placeholder: it appears verbatim in the pump's own speed-limits block.

- **Mode changes no longer force the pump on or clobber the setpoint.**
  `set_mode()` writes Object 86 sub-id 10
  (`overall_control_mode_local_request`, wire Obj `0x0A01`), whose payload
  carries `operation_mode = NoCmd` and `set_point = NaN` so only the mode
  is applied. Reading that object back from the pump returns exactly those
  sentinels, which is how the format was confirmed. Where the fused object
  must still be used and no setpoint is known, it now sends the NaN
  "keep existing" sentinel rather than the 3671.0 default.

- **Constant Flow setpoints were written in the wrong unit** (#28). The
  pump stores them in SI m³/s; the library wrote m³/h, so a commanded
  2.5 reached the pump as 2.5 m³/s - 9000 m³/h - which it rejected as out
  of range, keeping its old value. That is why the register looked frozen
  and read back ~1000× low. Writes now convert, and reads scale back.
  Telemetry flow is unaffected: it really is m³/h.

- **`get_mode()` read the wrong object** (#32). It read Object 86 Sub 6,
  the write-only *request* object, which reports `control_source = 0`
  whatever the pump is doing - so `is_remote` was never meaningful. It now
  reads Sub 7, the prioritized state. Measured side by side on hardware:
  Sub 6 returned 0, Sub 7 returned 1 (Local/Panel).

- **Cycle times read and wrote the wrong object.** Object 91 Sub 430 is
  `TemperatureRangeControlUserSettings`, whose trailing bytes are the
  on/off-time *limits* - invariant to the configuration - so the values
  never changed and writes never took. The live configuration is Sub 421
  (`dhw_on_off_control_configuration_obj`), which also carries the flow the
  pump targets during ON periods; that is now read first and echoed back
  byte for byte, so setting the periods cannot disturb it. No configuration
  commit is sent, matching the app. New `get_cycle_flow()`.

- **Temperature-range writes overwrote the pump's limits.** The struct's
  trailing bytes are the pump's on/off-time limits, sent as the constant
  `00 00 00 16 00`. Measured on hardware, the real value is `0f 3c 02 05 01`.
  They are now read and echoed back, and the write aborts rather than
  inventing them if the read fails.

- **Schedule writes preserved `default_action` instead of setting Stop.**
  The Grundfos app always writes Stop (`0x01`) there; carrying the pump's
  existing value through is what made the app label a correct schedule
  "pump will be idle".

- **Frames over 40 bytes were silently truncated**: `Transport.write()` split
  every packet into exactly two chunks, so the second chunk still exceeded
  the 20-byte BLE MTU for anything longer - including the 59-byte
  schedule-layer write, which `docs/protocol/ble_architecture.md` already
  documented as needing three chunks. Frames are now split into as many
  chunks as they need.

- **BLE writes were not paced**: consecutive writes could be issued
  back-to-back with only a 10ms gap between chunks of one frame and none at
  all between separate commands. Every write on the link now keeps a 50ms
  gap, matching the pacing the C++ port enforces.

- **Authentication handshake was not serialized** (#31): `send_legacy_burst()`
  spawned its three writes as concurrent `asyncio.TaskGroup` tasks, so the
  packets could reach the pump out of order, and the handshake as a whole ran
  outside the transport's transaction lock, so a telemetry query or keep-alive
  burst could land between two handshake packets. Both are the same failure
  mode that #24 fixed for the extension packets: the pump drops the link about
  a second after the handshake. Every packet is now written sequentially and
  the whole sequence is held under the transaction lock. The dead
  `send_class10_burst()` (bypassed by an inlined loop in `authenticate()`) is
  now the one implementation of the stage-2 burst.

  Handshake timings were also aligned with the C++ port's `auth.cpp`, which is
  the implementation currently validated against hardware: 50ms between
  packets (was 100ms), 100ms after stage 1, and a new explicit 200ms gap after
  stage 2. `AuthenticationHandler` takes an optional `transaction` lock; the
  client passes the transport's.

- **Misleading error on mid-read disconnect**: `_read_class10_object()` now
  raises `ConnectionError` when the BLE link drops while waiting for a
  response, instead of silently returning `None`. Previously a disconnect
  during `control status` (or any other Class 10 read) surfaced as
  "Setpoint data too short or missing: 0 bytes" / "Could not read control
  mode", masking the real cause. The CLI now reports "Pump disconnected
  from BLE while reading Object X/Y" instead.

- **Disconnect reported as "no data" via the transport**: `_read_class10_object()`
  raised `ConnectionError` only when a read went unanswered on a dead link. If
  the drop instead surfaced as a transport error (e.g. `BleakError` out of
  `write_gatt_char`), it was still swallowed and returned as `None` - the same
  misleading behavior for a different failure path. Both now raise.
- **Wake burst raced in-flight queries**: `send_wake_burst()` wrote its
  keep-alive packets without holding the transport's `_transaction_lock`, so a
  burst could interleave with a concurrent `query()` and let the replies it
  drew out land in that query's response queue. It now takes the lock like
  every other multi-packet operation.
- **A failed wake burst aborted the read**: the pre-read burst in `read_once()`
  sat outside the error handling, so a burst that raised took down the whole
  read instead of degrading to partial telemetry.
- **Telemetry read throughput**: `read_once()` sent a ~0.6s wake burst before
  every read, which capped polling at well under the 10Hz `stream()` interval
  and pushed a single read to ~750ms. The burst is now sent once per session
  and re-armed after a disconnect; the retry path still re-wakes a controller
  that goes back to sleep mid-session.

### Changed

- **Timestamps are timezone-aware**: absolute instants - telemetry
  `timestamp` (including the `TelemetryData` / `AdvancedTelemetry` field
  defaults), cycle/trend timestamps, session `connected_at` /
  `authenticated_at`, and CLI config bookkeeping - are now UTC-aware
  `datetime` objects rather than naive local ones. The CLI renders them in
  local time. The pump's own wall clock (`TimeService.get_clock()` /
  `set_clock()`) stays naive by design: the pump stores bare wall-clock
  fields with no offset and runs its schedules against them.
- **Narrower exception handling**: read paths across the services, client,
  and transport now catch `alpha_hwr.exceptions.READ_ERRORS` (transport and
  decode failures) instead of bare `Exception`, so genuine bugs surface
  instead of being logged as "no data". Top-level CLI error boundaries and
  caller-supplied notification handlers still catch broadly on purpose.
- `TelemetryData.control_mode` coercion raises `TypeError` (not `ValueError`)
  for a non-int input.

### Documentation

- Clarified that ALPHA HWR pumps should be paired/bonded with the host before
  telemetry and control are expected to work reliably.

### Internal

- Upgraded ruff to 0.16.1 and pinned it in CI. Ruff 0.16 widened the default
  rule set and began formatting Python inside Markdown fences; leaving it
  unpinned meant every upstream release could fail unrelated PRs.


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
