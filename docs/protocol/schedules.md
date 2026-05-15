# Schedule Management

The Grundfos ALPHA HWR features an internal weekly schedule system that allows the pump to operate only during specific time windows (e.g., mornings and evenings), saving energy.

The `alpha-hwr` library supports **full schedule management** - reading and writing schedules across all 5 layers.

## Protocol Overview

Unlike basic telemetry which is streamed automatically, the schedule data must be actively requested using **Class 10 DataObject READ** operations.

*   **Object ID**: `84` (`0x54`) - Clock Program / Schedule
*   **SubIDs**:
    *   `1`: Overview (Enabled Status, Metadata)
    *   `1000-1004`: **5 Independent Schedule Layers** (0-4)

### Multiple Schedule Layers

The ALPHA HWR supports **5 independent schedule layers** that allow complex scheduling patterns:

- **Layer 0 (SubID 1000)**: Primary schedule (typically weekday mornings)
- **Layer 1 (SubID 1001)**: Secondary schedule (typically weekday evenings)
- **Layer 2 (SubID 1002)**: Tertiary schedule (typically weekends)
- **Layer 3 (SubID 1003)**: Seasonal/temporary adjustments
- **Layer 4 (SubID 1004)**: Special events or overrides

**Features:**
- Each layer contains a full 7-day schedule (42 bytes)
- Layers can have **overlapping time windows** (e.g., Layer 0 and Layer 1 both active on Monday)
- The pump operates whenever **any layer** is active
- Layers allow organizing schedules by purpose (weekday/weekend, seasonal, etc.)

**Practical Example:**
```
Layer 0: Mon-Fri 6:30-8:30   (weekday morning showers)
Layer 1: Mon-Fri 18:00-22:00 (weekday evening usage)
Layer 2: Sat-Sun 8:00-23:00  (weekend all-day)
Layer 3: Dec-Feb extended    (winter heating boost)
Layer 4: Special events      (holiday adjustments)
```

### Critical Requirements

To successfully read the schedule, the client must follow a strict sequence:

1.  **Authentication**: The device must be unlocked via the [Connection Handshake](connection.md).
2.  **Keep-Alive Burst**: Before requesting large data structures, the client must send a burst of "Keep-Alive" packets to wake up the GENI controller fully.
3.  **Timing**: A delay of ~200-500ms is required after the burst before sending the Read Request.

## Data Structure

The schedule is stored as a `ClockProgramWeekDayInterval` (Type 222).

### Read Request
The client sends a standard Class 10 INFO (Read) request.

```text
[Class=0x0A] [OpSpec=0x03] [ObjID=0x54] [SubID=0x03E8 (1000)]
```

### Response Format
The device responds with a Class 10 packet containing the full week's schedule.

*   **Header**: 3 bytes (Padding/Length)
*   **Data**: 42 bytes (7 days $\times$ 6 bytes/day)

**Per-Day Structure (6 bytes):**

| Offset | Field | Description |
| :--- | :--- | :--- |
| 0 | **Enabled** | `0x01` if this day has an active schedule, `0x00` otherwise. |
| 1 | **Action** | Action ID (e.g., `0x02` for Run Pump). |
| 2 | **Start Hour** | 0-23 |
| 3 | **Start Minute** | 0-59 |
| 4 | **End Hour** | 0-23 |
| 5 | **End Minute** | 0-59 |

**Day Order**: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday.

## One-Time Schedule (Vacation Mode)

The pump supports a dedicated "One-Time" schedule slot, often used for "Vacation Mode" or temporary overrides.

*   **Object ID**: `0x6702` (26370)
*   **SubID**: `0x5E00` (24064)
*   **OpSpec**: `0x8B` (Set)

### Packet Structure
The payload controls whether the one-time schedule is enabled or disabled (deleted).

**Enable One-Time Schedule:**
```text
4D 01 [StartTimestamp] [EndTimestamp] [Mode] ...
```
*   `4D`: Command marker
*   `01`: Enable flag
*   ... followed by start/end times and mode configuration.

**Disable/Delete One-Time Schedule:**
```text
4D 00 ...
```
*   `4D`: Command marker
*   `00`: Disable flag
*   ... rest of payload is ignored or zeroed.

### Python Implementation

```python
# Set a one-time schedule (e.g., Vacation Mode)
start_time = datetime.now() + timedelta(days=1)
end_time = start_time + timedelta(weeks=1)
await client.set_one_time_schedule(start_time, end_time, ControlMode.CONSTANT_SPEED)

# Delete/Cancel one-time schedule
await client.delete_schedule()
```

## Unsupported Features

### Alternative Schedules
Testing confirmed that "Alternative Schedule" slots (typically associated with SubIDs 1100+) are **not supported** on this firmware version. The `ClockProgramOverview` (Obj 84, Sub 1) reports `max_nof_alternative_events_per_day = 0`.

## Python Implementation

### Reading Schedules

The `AlphaHWRClient` handles the complexity of the keep-alive burst and parsing.

```python
async with AlphaHWRClient(address) as client:
    await client.authenticate()
    
    # Check if schedule is globally enabled
    is_enabled = await client.get_schedule_enabled()
    print(f"Schedule Active: {is_enabled}")
    
    # Get detailed entries for all layers (consolidated)
    schedule = await client.get_schedule()
    
    # Get entries for a specific layer (e.g., Layer 0)
    layer0_schedule = await client.get_schedule(layer=0)
    
    for entry in schedule:
        if entry.enabled:
            print(f"{entry.day}: {entry.begin_time} - {entry.end_time} (Layer {entry.layer})")
```

### Writing Schedules

#### Enable/Disable Schedule

The global schedule can be enabled or disabled:

```python
# Enable the schedule
success = await client.set_schedule_enabled(True)

# Disable the schedule
success = await client.set_schedule_enabled(False)
```

**Protocol Details:**

To enable/disable the schedule, the client:
1. Reads the current `ClockProgramOverview` data (Object 84, SubID 1)
2. Modifies the complete 10-byte structure with the new enabled flag
3. Writes back using Class 10 SET operation with OpSpec encoding `0x93`

**Data Structure (ClockProgramOverview - Type 218, 10 bytes):**
```text
Byte 0:   max_nof_actions (uint8)
Byte 1:   max_nof_single_events (uint8)
Byte 2:   max_nof_alternative_events_per_day (uint8)
Byte 3:   max_nof_events_per_day (uint8)
Byte 4:   clock_program_enabled (bool) - 0x01 = enabled, 0x00 = disabled
Byte 5:   default_action (SchedulingActionType - uint8)
Bytes 6-9: base_set_point (float32)
```

**Write Request Format:**
```text
Start:    0x27 (REQUEST)
Length:   0x17 (23 bytes)
Dest:     0xE7 (pump)
Source:   0xF8 (Local Master)
Class:    0x0A (Class 10)
OpSpec:   0x93 (OpSpec 4, Length 19)
Object:   0x54 (Object ID 84)
SubID:    0x00 0x01 (SubID 1, big-endian)
Reserved: 0x00
Type:     0xDA 0x01 0x00 (Type 218 = ClockProgramOverview, big-endian)
Size:     0x00 0x0A (10 bytes)
Data:     [10 bytes of ClockProgramOverview structure]
CRC:      [2 bytes CRC-16-CCITT with final XOR]
```

**Complete packet example (ENABLE):**
```text
2717e7f80a9354000100da0100000a02050005010100000000b44e
```

**Important Implementation Notes:**
*   **Complete structure required**: Must send all 10 bytes of the structure, not just the enabled flag
*   **Read first**: Always read current values to preserve capabilities and settings
*   **Packet splitting**: Packets > 20 bytes must be split across multiple BLE writes due to ATT MTU limit (20 bytes max per write)
*   **OpSpec encoding**: Use `0x93` (OpSpec 4, Length 19) for the 19-byte APDU
*   **Source address**: Use `0xF8` (Local Master), matching standard client behavior
*   **CRC calculation**: Use CRC-16-CCITT with final XOR (not the write CRC variant)

#### OpSpec Encoding Summary

Different schedule operations require different OpSpec codes:

| Operation | OpSpec | OpSpec Value | Length | Type ID | Structure Size |
|-----------|--------|--------------|--------|---------|----------------|
| Enable/Disable | OpSpec 4 | `0x93` | 19 | Type 218 (Overview) | 10 bytes |
| Write Schedule | OpSpec 5 | `0xB3` | 19 | Type 222 (Interval) | 42 bytes |

**OpSpec Encoding Format:** `[OpSpec (3 bits)][Length (5 bits)]`
- `0x93` = `(4 << 5) | 19` = OpSpec 4, Length 19
- `0xB3` = `(5 << 5) | 19` = OpSpec 5, Length 19

**Differences:**
- **OpSpec 0x93**: Used for enable/disable (Type 218 ClockProgramOverview, 10 bytes)
- **OpSpec 0xB3**: Used for schedule writes (Type 222 ClockProgramWeekDayInterval, 42 bytes)
- The OpSpec determines which structure type the pump expects

#### Write Schedule Entries

##### Single Entry

Write a schedule entry for a specific day:

```python
# Set Monday 6:00-8:00
success = await client.set_schedule_entry("Monday", 6, 0, 8, 0)
```

**Protocol Details:**

To write a single entry, the client:
1. Reads the current layer data (Object 84, SubIDs 1000-1004)
2. Modifies the 6 bytes for the specific day
3. Writes back using Class 10 SET operation with OpSpec `0xB3`

**Data Structure (ClockProgramWeekDayInterval - Type 222, 42 bytes):**
```text
Per-Day Structure (6 bytes):
[0]: Enabled flag (0x01 = enabled, 0x00 = disabled)
[1]: Action (0x02 = run pump)
[2]: Start hour (0-23)
[3]: Start minute (0-59)
[4]: End hour (0-23)
[5]: End minute (0-59)
```

**Day Order:** Monday (offset 0), Tuesday (offset 6), Wednesday (offset 12), Thursday (offset 18), Friday (offset 24), Saturday (offset 30), Sunday (offset 36)

**Write Request Format:**
```text
Start:    0x27 (REQUEST)
Length:   [varies - typically 55 bytes for APDU, 59 bytes total]
Dest:     0xE7 (pump)
Source:   0xF8 (Local Master)
Class:    0x0A (Class 10)
OpSpec:   0xB3 (OpSpec 5, Length 19)
Object:   0x54 (Object ID 84)
SubID:    [SubID for layer, big-endian] (1000-1004)
Reserved: 0x00
Type:     0xDE 0x01 0x00 (Type 222 = ClockProgramWeekDayInterval)
Size:     0x00 0x2A (42 bytes)
Data:     [42 bytes of schedule data - 7 days × 6 bytes]
CRC:      [2 bytes CRC-16-CCITT with final XOR]
```

**Complete packet example (Layer 0, SubID 1000):**
```text
2737e7f80ab35403e800de0100002a0102052d09000102052d09000102062d09000102062d09000102071e09000102081e16000102081e160092f3
```

**Important Implementation Notes:**
*   **OpSpec encoding**: Use `0xB3` (OpSpec 5, Length 19) for schedule write operations
*   **Byte order**: Object ID comes BEFORE SubID (opposite of older protocol variants)
*   **Complete data required**: Must send all 42 bytes (full week), even when modifying a single day
*   **Packet splitting**: 59-byte packets must be split: 20 + 20 + 19 bytes across multiple BLE writes due to ATT MTU limit
*   **Type header**: Must include Type 222 header (0xDE 0x01 0x00) and size (0x00 0x2A)

##### Weekly Schedule

Write multiple entries at once:

```python
from alpha_hwr import ScheduleEntry

entries = [
    ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0),
    ScheduleEntry(day="Monday", begin_hour=18, begin_minute=0, end_hour=20, end_minute=0),
    ScheduleEntry(day="Tuesday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0),
]

success = await client.set_weekly_schedule(entries, layer=0)
```

**Protocol Details:**

To write a weekly schedule, the client:
1. Validates all entries for conflicts (using `validate_schedule()`)
2. Builds a 42-byte payload (7 days × 6 bytes)
3. Writes to the specified layer (SubIDs 1000-1004) using OpSpec `0xB3`

**Important:** This method overwrites the entire layer. Days not included in the entries list will be cleared (disabled).

**Write Request Format:**
```text
Class:    0x0A (Class 10)
OpSpec:   0xB3 (OpSpec 5, Length 19)
Object:   0x54 (Object ID 84)
SubID:    [SubID for layer, big-endian] (1000-1004)
Reserved: 0x00
Type:     0xDE 0x01 0x00 (Type 222)
Size:     0x00 0x2A (42 bytes)
Data:     [42 bytes of schedule data]
```

For layer 0 (SubID 1000), the APDU is:
```text
0A B3 54 03 E8 00 DE 01 00 00 2A [42 bytes...]
```

#### Clear Schedule Entries

##### Clear Single Day

Clear a schedule entry for a specific day:

```python
# Clear Monday on layer 0
success = await client.clear_schedule_entry("Monday", layer=0)
```

**Protocol Details:**

To clear a single day, the client:
1. Reads the current layer data (Object 84, SubIDs 1000-1004)
2. Sets the 6 bytes for the specific day to 0x00 (disabled)
3. Writes back using Class 10 SET operation with OpSpec `0xB3`

This preserves other days on the same layer. Uses the same packet format as `set_schedule_entry()`.

##### Clear Entire Layer

Clear all schedule entries on a specific layer:

```python
# Clear all entries on layer 0
success = await client.clear_schedule_layer(0)
```

**Protocol Details:**

To clear a layer, the client:
1. Builds a 42-byte payload of all zeros
2. Writes to the specified layer (SubIDs 1000-1004) using OpSpec `0xB3`

This is more efficient than clearing individual days. Uses the same packet format as `set_weekly_schedule()`.

##### Clear All Schedules

Clear all schedule entries on all 5 layers:

```python
# Clear everything
success = await client.clear_all_schedules()
```

**Protocol Details:**

This method iterates through all 5 layers (0-4) and clears each one. Returns True only if all 5 layers are successfully cleared.

#### Export/Import JSON

##### Export Schedule

Export the current schedule to a JSON file:

```python
# Export current schedule
success = await client.export_schedule_json("schedule.json")
```

**Details:**

The export method:
1. Reads the complete schedule using `get_schedule()`
2. Writes the data to a JSON file with proper formatting
3. Creates parent directories if needed

**JSON Format:**

```json
{
  "enabled": true,
  "days": [
    {
      "day": "Monday",
      "enabled": true,
      "action": 2,
      "begin_hour": 6,
      "begin_minute": 0,
      "end_hour": 8,
      "end_minute": 0,
      "begin_time": "06:00",
      "end_time": "08:00"
    }
  ]
}
```

##### Import Schedule

Import a schedule from a JSON file:

```python
# Import from file
import json
from alpha_hwr import ScheduleEntry

with open("schedule.json", 'r') as f:
    data = json.load(f)

entries = [ScheduleEntry(**entry) for entry in data['days']]
success = await client.set_weekly_schedule(entries, layer=0)
```

Or use the CLI:

```bash
alpha-hwr schedule --import-json schedule.json --layer 0
```

## Working with Multiple Layers

### Understanding Schedule Layers

The ALPHA HWR pump supports **5 independent schedule layers** that enable sophisticated scheduling patterns. Each layer is a complete 7-day schedule stored independently.

#### Why Multiple Layers

1. **Separation of Concerns**: Keep different schedule types separate
   - Layer 0: Weekday mornings
   - Layer 1: Weekday evenings
   - Layer 2: Weekend schedule
   - Layer 3: Seasonal adjustments
   - Layer 4: Special events

2. **Overlapping Time Windows**: Different layers can be active simultaneously
   - Monday 6:00-9:00 (Layer 0: morning)
   - Monday 7:00-10:00 (Layer 1: extended morning)
   - Result: Pump runs 6:00-10:00 (union of both)

3. **Easier Maintenance**: Modify one schedule type without affecting others
   - Update weekend schedule (Layer 2) without touching weekday schedules
   - Add seasonal boost (Layer 3) without changing base schedule

### Layer Best Practices

#### Pattern 1: Time-of-Day Separation
```python
# Layer 0: Morning schedule
morning = [
    ScheduleEntry(day="Monday", begin_hour=6, begin_minute=30, end_hour=8, end_minute=30),
    ScheduleEntry(day="Tuesday", begin_hour=6, begin_minute=30, end_hour=8, end_minute=30),
    # ... rest of weekdays
]

# Layer 1: Evening schedule
evening = [
    ScheduleEntry(day="Monday", begin_hour=18, begin_minute=0, end_hour=22, end_minute=0),
    ScheduleEntry(day="Tuesday", begin_hour=18, begin_minute=0, end_hour=22, end_minute=0),
    # ... rest of weekdays
]

await client.set_weekly_schedule(morning, layer=0)
await client.set_weekly_schedule(evening, layer=1)
```

#### Pattern 2: Weekday/Weekend Separation
```python
# Layers 0-1: Weekday schedules (as above)
# Layer 2: Weekend all-day
weekend = [
    ScheduleEntry(day="Saturday", begin_hour=8, begin_minute=0, end_hour=23, end_minute=0),
    ScheduleEntry(day="Sunday", begin_hour=8, begin_minute=0, end_hour=23, end_minute=0),
]

await client.set_weekly_schedule(weekend, layer=2)
```

#### Pattern 3: Seasonal Adjustments
```python
# Layers 0-2: Year-round schedules
# Layer 3: Winter boost (December-February)
winter_boost = [
    ScheduleEntry(day="Monday", begin_hour=5, begin_minute=0, end_hour=6, end_minute=30),
    # ... pre-morning heating boost
]

# Enable in winter, clear in summer
if is_winter:
    await client.set_weekly_schedule(winter_boost, layer=3)
else:
    await client.clear_schedule_layer(3)
```

### Reading from Specific Layers

```python
# Read all layers (combined view)
schedule = await client.get_schedule()
# Returns all enabled entries from all 5 layers

# Read specific layer (direct)
layer0_data = await client.get_schedule(layer=0)
layer2_data = await client.get_schedule(layer=2)
```

### Layer Operations

```python
# Write to specific layer
await client.set_weekly_schedule(entries, layer=2)

# Clear specific layer
await client.clear_schedule_layer(2)

# Clear all layers
await client.clear_all_schedules()

# Single entry affects only one layer
await client.set_schedule_entry("Monday", 6, 0, 8, 0, layer=0)
await client.clear_schedule_entry("Monday", layer=0)
```

### Layer Validation

**Per-Layer Validation**: The validation system checks for overlaps **within each layer**:

```python
# This is VALID (different layers)
layer0 = [ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0, end_hour=9, end_minute=0)]
layer1 = [ScheduleEntry(day="Monday", begin_hour=7, begin_minute=0, end_hour=10, end_minute=0)]

await client.set_weekly_schedule(layer0, layer=0)  #  Valid
await client.set_weekly_schedule(layer1, layer=1)  #  Valid
# Result: Monday 6:00-10:00 (overlapping is allowed across layers)

# This is INVALID (same layer)
entries = [
    ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0, end_hour=9, end_minute=0),
    ScheduleEntry(day="Monday", begin_hour=7, begin_minute=0, end_hour=10, end_minute=0),
]
await client.set_weekly_schedule(entries, layer=0)  #  Validation error
# Error: Overlap detected: Monday layer 0: 06:00-09:00 overlaps with 07:00-10:00
```

### Layer Interaction with Pump Operation

The pump operates when **any layer** has an active time window:

```mermaid
gantt
    title Monday Schedule (Combined Layers)
    dateFormat HH:mm
    axisFormat %H:%M
    
    section Layer 0
    Morning (6:00-9:00) :active, l0, 06:00, 09:00
    
    section Layer 1
    Late Morning (8:00-11:00) :active, l1, 08:00, 11:00
    
    section Layer 2
    Noon (10:00-12:00) :active, l2, 10:00, 12:00
    
    section Combined
    Pump ON (6:00-12:00) :crit, done, 06:00, 12:00
```

The pump runs from 6:00-12:00 (union of all active layers).

### CLI Layer Management

```bash
# Write to specific layer
alpha-hwr schedule --set-entry Monday 6 0 9 0 --layer 0

# Set weekly schedule on layer
alpha-hwr schedule --import-json weekday.json --layer 0
alpha-hwr schedule --import-json weekend.json --layer 2

# Clear specific layer
alpha-hwr schedule --clear-layer 3

# View all layers (combined)
alpha-hwr schedule
```

## Limitations

1.  **Multi-Layer Support**: The library supports all 5 schedule layers (0-4) for reading and writing.
2.  **Validation Required**: Always validate schedules before writing to prevent overlaps within the same layer.
3.  **Cross-Layer Overlaps**: Overlapping time windows across different layers are allowed and intentional.

## Schedule Validation

The library includes validation for schedule entries to prevent conflicts and errors.

### ScheduleEntry Model

The `ScheduleEntry` model provides a structured way to work with schedule time windows:

```python
from alpha_hwr import ScheduleEntry

entry = ScheduleEntry(
    day="Monday",
    begin_hour=6,
    begin_minute=0,
    end_hour=8,
    end_minute=0,
    layer=0,  # Schedule layer (0-4)
    action=0x02,  # Run pump
    enabled=True
)
```

### Validation Features

**Automatic Field Validation:**
*   Day names must be valid weekdays (Monday-Sunday)
*   Hours must be 0-23
*   Minutes must be 0-59
*   Layer must be 0-4

**Time Range Validation:**
*   Zero-duration entries are rejected
*   Midnight-crossing schedules are supported (e.g., 22:00-02:00)

**Overlap Detection:**
*   Detects overlapping time windows on same day/layer
*   Handles midnight-crossing overlaps correctly
*   Ignores disabled entries and different layers

**Example:**
```python
# Validate a list of schedule entries
entries = [
    ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0),
    ScheduleEntry(day="Monday", begin_hour=7, begin_minute=0, end_hour=9, end_minute=0),  # Overlaps!
]

is_valid, errors = client.validate_schedule(entries)
if not is_valid:
    for error in errors:
        print(f"Error: {error}")
# Output: Error: Overlap detected: Monday layer 0: 06:00-08:00 overlaps with 07:00-09:00
```

### Duration Calculation

Calculate schedule entry duration, including midnight-crossing:

```python
# Normal entry
entry = ScheduleEntry(day="Monday", begin_hour=6, begin_minute=0, end_hour=8, end_minute=0)
print(entry.get_duration_minutes())  # 120 minutes (2 hours)

# Midnight-crossing entry
entry = ScheduleEntry(day="Monday", begin_hour=22, begin_minute=0, end_hour=2, end_minute=0)
print(entry.get_duration_minutes())  # 240 minutes (4 hours)
print(entry.crosses_midnight())  # True
```