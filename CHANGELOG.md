# Changelog


## [Unreleased]

### Fixed

- **The APDU head is a length, not an opcode.** Byte 5 of a GENI frame is
  `0booLLLLLL`: an operation (GET/SET/INFO) or an acknowledgement in the
  top two bits, and the payload's byte count in the low six. There is no
  "OpSpec". `byte5 == len(frame) - 8` held for every reply measured
  against the pump.

  Two mistakes followed from reading it as an opcode. The set `{0x30,
  0x2B, 0x14, 0x2E, 0x2D, 0x09}`, carried as "register-read operation
  specifiers" and used to select a payload offset, is really the payload
  lengths 48, 43, 20, 46, 45 and 9 — it worked because 48, 43 and 20 are
  exactly the three telemetry replies, and mis-sliced anything else that
  size. And `0x81` was read as an acknowledgement carrying an error code:
  it is Unknown Data Item with one payload byte, and that byte names the
  item the pump did not recognise, so a refused write read as accepted
  whenever the item was `0x00` — the case this pump produces.

- **A response carries no Object ID and no Sub-ID.** Bytes 6-9 are
  `[00][TypeH][TypeL][Version]`, the type of the object answered. Matching
  therefore discriminates types, not instances: Object 86 sub-ids 13, 15,
  17 and 39 all answer `00 01 2d 01`, and alarms and warnings answer
  identically to each other.

  The rule that accepted the two fields in either order is gone — they are
  one type field, every measured reply matches in wire order, and
  accepting a transpose let unrelated objects answer each other's reads.

- **Telemetry routed on the address it asked for.** The decoder's table,
  the frame parser's telemetry set and the stream-detection flags all
  compared against `(87, 69)`, `(93, 290)` and `(93, 300)`. No reply
  carries those, so every case fell through to a raw-frame fallback, and
  `_has_motor_state_stream` could never be set by a notification — so the
  polling it exists to suppress ran whether or not the pump was streaming.

- **Every reason a frame is thrown away is now counted**
  (`transport.frame_drops`): bad CRC, an abandoned partial, bytes that
  start no frame, an impossible declared length, a reassembly overflow,
  and a full response queue. They are separate counters because they mean
  different things - a bad CRC is a corrupted link, a runt length is a
  peer talking nonsense, and unsolicited fragments usually mean sync was
  lost rather than that the radio is bad. A dropped frame is the system
  working; what was missing was any way to know it had happened.

- **Inbound CRC is now enforced.** It was computed and never read:
  `validate_frame_integrity()` was its only consumer and had no call site,
  so every write verdict was decided by reading unverified bytes back.
  Frames are trimmed to their declared length first, since the completion
  test is `>=` and trailing bytes sit outside what the CRC covers. Bad
  frames are dropped and counted (`transport.crc_failures`).

- **Reassembly.** `0x27` was accepted as an inbound start byte; the pump
  never sends it. A frame start now begins a new packet only when
  reassembly is not already under way — a mid-frame fragment can perfectly
  well begin `0x24`, and treating it as a start discarded the frame in
  progress. A partial frame is abandoned after a second rather than
  wedging the buffer. The declared length is bounded at both ends: there
  was no minimum, so a length byte of `0x00` completed a four-byte
  "frame" instantly, and the maximum was 256 against a real 257. A second
  frame arriving in the same notification is now delivered instead of
  being swallowed into the first one's payload.

- **Every device-info string was a character short.** The Class 7 header
  is six bytes, not seven: byte 5 is the string's byte count and the text
  starts at offset 6, with no echoed string ID. Two strings were patched
  up afterwards and so looked right — an `"A"` prepended to `LPHA HWR`,
  and a `"1"` prepended to a serial reading `0000479`, which was correct
  for this unit only by coincidence. The versions had no such patch:

      software  2601618V04.02.01.02539  ->  92601618V04.02.01.02539
      hardware  2601617V01.03.00.00469  ->  92601617V01.03.00.00469
      BLE       2811431V06.00.01.00001  ->  92811431V06.00.01.00001

  Both rewrites are removed rather than retuned.

- **Single-event writes declared a payload length they did not carry.**
  The APDU head was `0xB3` - SET with 51 bytes - borrowed from the schedule
  layer write, whose 53-byte APDU really does carry 51. A single event
  carries 19, so the head is `0x93`. Every one of the 29 single-event
  writes in the capture corpus uses `0x93`; the 8 layer writes use `0xB3`.
  The pump accepts either, so nothing was visibly failing, but a firmware
  that checked the field would have refused ours with no diagnostic.

- **A single-event write never checked what the pump kept.** It now reads
  the slot back and compares the window, the enabled flag and - the point
  of the exercise - the ACTION byte. ACTION is half the meaning of a
  single event: `0x01` holds the pump off across the window, which is what
  a vacation *is*, and `0x02` runs it once. A confirm without it would
  settle a vacation as written while the pump was scheduled to run.

- **`clear_vacation()` ignored the clock.** It cleared the first enabled
  Stop event in slot order, so a finished vacation in an early slot
  shadowed a live one later: the call reported success and the pump stayed
  off. It now prefers the vacation that is running, then the next one due,
  and says so when it falls back to an expired one. `find_free_slot()` one
  method up had always been clocked; the asymmetry was the bug.

- **A wholly-past window is refused**, rather than spending one of five
  slots on an event that can never run. A window already *underway* is
  still accepted - starting part-way through is legitimate, so only the
  end is compared.

- **Slot bounds are checked in two stages, in that order.** The protocol
  envelope first and without touching the pump - sub-id is `900 + slot`
  and the schedule layers start at 1000, so slot 100 addresses layer 0
  whatever the pump is doing. The pump's own count second, from the
  overview. Deferring the first check made an impossible slot on a broken
  link report "the overview could not be read", blaming the link for an
  argument that could never have been right.

- **Single-event timestamps are bounded to what the wire can hold**
  (uint32, 1970 to 2106). `build_apdu` previously raised `OverflowError`
  from inside a `try` that caught only read errors, so it escaped
  uncaught.

- **A read chain cut short by a disconnect reported itself as success.**
  `get_all_entries()` skipped entries it could not read - which is right,
  since a log with twelve entries reports the other eight as unreadable -
  and a dropped link went down the same path. The result was a short list
  and `Retrieved 5/20`, which is exactly what a five-entry log looks like.
  `get_trend_data()` had the same shape: three of its four series are
  legitimately `None` on some pumps, so a half-built collection did not
  look wrong.

  Both now raise `ConnectionError` and say how far they got, rather than
  handing back something indistinguishable from less data. Measured on the
  pump: dropping the link 0.35 s into a full event-log read now raises
  *"disconnected while reading the event log after 4 of 20 entries"*
  instead of returning four entries.

- **A waiter sat out its own timeout after the link had gone.** Nothing
  woke a pending read when the BLE link dropped, so each one waited its
  full three seconds for a pump that was no longer there. `read_response`
  now races the reply against the disconnect, and a dropped link is
  reported as such rather than as a timeout - 0.1 s instead of 3.0 s in
  the unit test that pins it.

- **`alpha_hwr.exceptions.ConnectionError` now subclasses the builtin.**
  The package shadows the builtin name, and which one a module raised came
  down to whether that file happened to import this one - `base.py` and
  `client.py` raised the package's, `session.py` and `time.py` the
  builtin - so no single `except` clause caught both. It now inherits from
  both, which is what anyone writing `except ConnectionError` expects.

- **A GENI frame must be split into 20-byte GATT writes.** The transport
  has always chunked at `BLE_MTU_LIMIT = 20`, and it turns out that is a
  pump requirement rather than a guess about the radio: with the ATT MTU
  negotiated at 65, a 27-byte frame sent in one `write_gatt_char` is
  ignored outright, while the identical bytes chunked at 20 are
  acknowledged in 111 ms. Documented, and pinned by tests, so it does not
  get "optimised" away.

- **The dedicated Class 10 setpoint write was refused, always.** It
  addressed sub-id first where every Class 10 SET this pump accepts is
  object first, so it named object `0x00` and the pump answered Unknown
  Data Item quoting `0x00` back — on every setpoint write since the method
  existed, invisibly, because the send was fire-and-forget and the retry
  helper reports success even on a timeout. It is deleted: the fused
  Object 86 Sub 6 request already carries the setpoint, which is how the
  Grundfos GO app sets one.

### Added

- **Setpoint bounds read from the pump** (`read_setpoint_ranges()`,
  `get_setpoint_range()`). The pump publishes them in the type 301
  objects at Object 86 sub 13, 15, 17 and 39. Every constant this client
  validated against was wrong in both directions:

  | mode | pump | was |
  |---|---|---|
  | constant speed | 1650 – 3671 RPM | 500 – 4500 |
  | constant pressure | 1.000 – 2.450 m | 0.5 – 10.0 |
  | proportional pressure | 2.599 – 4.569 m | 0.5 – 10.0 |
  | constant flow | 0.114 – 2.498 m³/h | 0.1 – 10.0 |

  Proportional pressure was the worst: a 0.5 m floor against a real 2.6 m,
  in a range that does not overlap constant pressure's — and the two
  shared one constant. The read runs once per connection during cache
  sync, sequentially, and stops at the first failure, because all four
  objects answer with the same type code and carrying on would shift every
  remaining range by one slot. The old constants remain as a deliberately
  wide fallback: refusing a setpoint the pump would have taken is worse
  than letting it clamp one it dislikes.

- **`read_limiters()` and `alpha-hwr control limiters`.** An enabled flow
  limiter caps delivered flow whatever the setpoint says, and nothing in
  the setpoint range reveals it — so a setpoint can settle accepted, read
  back correct, and still not be delivered.

### Removed

- **The authentication handshake.** Ten packets went out on every
  connection as a three-stage "unlock". All four distinct packets are
  reads — two GETs and two INFO queries — and their replies were
  discarded. A read cannot change device state. With none of them sent, a
  bare connect-and-subscribe link answers every read this client makes.
  The 750 ms of inter-stage delays went too; they were transcribed from
  this client's own `sleep()` calls and then documented as pump timing
  requirements. `authenticate()` keeps its name and now only waits for the
  radio to settle.

- **`set_flow_limit()` and `alpha-hwr control set-flow-limit`**, along
  with the `--flow-limit` options on `set-speed` and `set-temperature`.
  They wrote Object 86 Sub 39 — the constant-flow *setpoint range*, not a
  limiter — through the refused frame above. The real limiters are at
  Object 86 Sub 600 (MaxFlow) and Sub 601 (MinFlow); `read_limiters()`
  reads them. The write is not reimplemented, because enabling a limiter
  silently caps the pump and that is not a change to make as a side effect
  of a protocol sync.

### Tests

- **Doctests are run, and green.** 185 of 279 examples in the source were
  failing. Seven were genuinely wrong — `encode_float_be(1.5)` claimed
  `b'\x3f\xc0\x00\x00'` where Python prints `?`, a three-byte register
  read's frame length was given as 9 rather than 11, `build_command_info`
  claimed an address with a stray digit and a trailing ellipsis, and four
  `Session` examples referred to objects nobody had built. The rest were
  never executable — `await` at the top level, or a client that does not
  exist — and now carry `# doctest: +SKIP`, which says what they are.
  `tests/test_doctests.py` runs the remainder with a floor on the count,
  so the failure mode cannot return as "skip everything".

### Documentation

- **The clock write's frame layout is described correctly.** It is Object
  94 **Sub 100**, type **321 version 2**; the constant carrying its first
  six bytes was named `_TYPE_322_HEADER`, and 322 is the type the *read*
  of Sub 101 answers with. Those six bytes are not an opaque header either
  - they are the tail of the address, the object's size field and the
  struct's leading byte. Verified against the frame the builder emits.

- `docs/protocol/bench_findings.md` records the 2026-08-20 session: the
  Class 7 header, the response type table, the setpoint ranges, the
  second Class 10 acknowledgement, the limiter survey, the post-SET quiet
  period, and how long an Object 91 write takes to become visible.


## [0.7.0] - 2026-08-05

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
