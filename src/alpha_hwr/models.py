from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator


from typing import ClassVar
from alpha_hwr.constants import (
    FACTOR_M3H_TO_GPM,
    FACTOR_M_TO_FT,
    FACTOR_M_TO_PSI,
    FACTOR_CELSIUS_TO_FAHRENHEIT,
)


class TelemetryData(BaseModel):
    """
    Telemetry data from Grundfos Alpha HWR pump.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    timestamp: datetime = Field(
        default_factory=datetime.now, description="Time of reading"
    )

    # Primary Metrics
    flow_m3h: float | None = Field(
        default=None, description="Flow rate in m³/h"
    )
    head_m: float | None = Field(
        default=None, description="Head pressure in meters"
    )
    power_w: float | None = Field(
        default=None, description="Power consumption in Watts"
    )

    # Temperatures
    media_temperature_c: float | None = Field(
        default=None, description="Media temperature in Celsius"
    )
    pcb_temperature_c: float | None = Field(
        default=None, description="PCB temperature in Celsius"
    )
    control_box_temperature_c: float | None = Field(
        default=None, description="Control box temperature in Celsius"
    )

    # Electrical details
    voltage_ac_v: float | None = Field(
        default=None, description="Input AC voltage in Volts"
    )
    voltage_dc_v: float | None = Field(
        default=None, description="Internal DC voltage in Volts"
    )
    current_a: float | None = Field(
        default=None, description="Input current in Amperes"
    )
    speed_rpm: float | None = Field(
        default=None, description="Actual Motor speed in RPM"
    )
    setpoint_rpm: float | None = Field(
        default=None, description="Target/Setpoint speed in RPM"
    )

    # Status
    status_code: int | None = Field(default=None, description="Raw status byte")
    control_mode: int | None = Field(
        default=None, description="Active control mode ID"
    )

    @property
    def flow_gpm(self) -> float | None:
        """Convert flow to GPM."""
        return (
            self.flow_m3h / FACTOR_M3H_TO_GPM
            if self.flow_m3h is not None
            else None
        )

    @property
    def head_ft(self) -> float | None:
        """Convert head to feet."""
        return self.head_m / FACTOR_M_TO_FT if self.head_m is not None else None

    @property
    def head_psi(self) -> float | None:
        """Convert head to PSI."""
        return (
            self.head_m / FACTOR_M_TO_PSI if self.head_m is not None else None
        )

    @property
    def media_temperature_f(self) -> float | None:
        """Convert media temperature to Fahrenheit."""
        if self.media_temperature_c is None:
            return None
        return (self.media_temperature_c / FACTOR_CELSIUS_TO_FAHRENHEIT) + 32.0

    @property
    def formatted_string(self) -> str:
        """Get a human-readable string representation."""
        parts: list[str] = []
        if self.flow_m3h is not None:
            parts.append(f"Q={self.flow_m3h:.3f}m³/h")
        if self.head_m is not None:
            parts.append(f"H={self.head_m:.2f}m")
        if self.power_w is not None:
            parts.append(f"P={self.power_w:.1f}W")

        # Temp
        if self.media_temperature_c is not None:
            parts.append(f"T_media={self.media_temperature_c:.1f}°C")
        if self.pcb_temperature_c is not None:
            parts.append(f"T_pcb={self.pcb_temperature_c:.1f}°C")
        if self.control_box_temperature_c is not None:
            parts.append(f"T_ctrl={self.control_box_temperature_c:.1f}°C")

        # Elec
        if self.voltage_ac_v is not None:
            parts.append(f"V_ac={self.voltage_ac_v:.1f}V")
        if self.voltage_dc_v is not None:
            parts.append(f"V_dc={self.voltage_dc_v:.1f}V")
        if self.current_a is not None:
            parts.append(f"I={self.current_a:.2f}A")
        if self.speed_rpm is not None:
            parts.append(f"N={self.speed_rpm:.0f}rpm")
        if self.setpoint_rpm is not None:
            parts.append(f"(Set={self.setpoint_rpm:.0f})")

        return " | ".join(parts) if parts else "No Data"


class SetpointInfo(BaseModel):
    """Setpoint information for current control mode."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    control_mode: int = Field(description="Active control mode ID")
    operation_mode: int = Field(description="Operation mode")
    setpoint: float = Field(description="Current setpoint value (raw)")
    min_setpoint: float | None = Field(
        default=None, description="Minimum allowed setpoint"
    )
    max_setpoint: float | None = Field(
        default=None, description="Maximum allowed setpoint"
    )
    unit: str | None = Field(default=None, description="Unit of measurement")

    # Operational status
    is_remote: bool | None = Field(
        default=None, description="True if remote control mode is enabled"
    )
    is_running: bool | None = Field(
        default=None, description="True if the pump motor is started"
    )
    schedule_enabled: bool | None = Field(
        default=None, description="True if internal schedule is active"
    )

    def get_display_value(self) -> tuple[float, str]:
        """
        Get setpoint value with appropriate unit based on control mode.

        Returns:
            Tuple of (value, unit_string)

        Notes:
            - CONSTANT_PRESSURE (0): Returns meters (m) - raw value is in Pascals, converted to m H2O
            - PROPORTIONAL_PRESSURE (1): Returns meters (m) - raw value is in Pascals
            - CONSTANT_FLOW (8): Returns m³/h - raw value is already in m³/h
            - CONSTANT_SPEED (2): Returns RPM - raw value is already in RPM
            - CONSTANT_TEMPERATURE (6): Returns °C - raw value is already in °C
            - Others: Returns raw value with "units"
        """
        from .constants import ControlMode

        # Pressure modes (Pascals  meters of water column)
        if self.control_mode in (
            ControlMode.CONSTANT_PRESSURE,
            ControlMode.PROPORTIONAL_PRESSURE,
            ControlMode.CONSTANT_DIFF_PRESSURE,
            ControlMode.PROPORTIONAL_DIFF_PRESSURE,
            ControlMode.AUTO_ADAPT_RADIATOR,
            ControlMode.AUTO_ADAPT_UNDERFLOOR,
            ControlMode.AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR,
        ):
            # Convert Pascals to meters of water column (1 m H2O ≈ 9806.65 Pa)
            meters = self.setpoint / 9806.65
            return (meters, "m")

        # Flow modes (already in m³/h)
        elif self.control_mode in (
            ControlMode.CONSTANT_FLOW,
            ControlMode.FLOW_ADAPT,
        ):
            return (self.setpoint, "m³/h")

        # Speed mode (already in RPM or %)
        elif self.control_mode == ControlMode.CONSTANT_SPEED:
            return (self.setpoint, "RPM")

        # Temperature modes (already in °C)
        elif self.control_mode in (
            ControlMode.CONSTANT_TEMPERATURE,
            ControlMode.CONSTANT_DIFF_TEMP,
            ControlMode.TEMPERATURE_RANGE_CONTROL,
        ):
            return (self.setpoint, "°C")

        # Level control (meters)
        elif self.control_mode == ControlMode.CONSTANT_LEVEL:
            return (self.setpoint, "m")

        # Default: return raw value
        else:
            return (self.setpoint, "units")

    def get_limits_display(
        self,
    ) -> tuple[tuple[float, str], tuple[float, str]] | None:
        """
        Get min/max setpoint limits with appropriate unit conversion.

        Returns:
            Tuple of ((min_value, unit), (max_value, unit)), or None if limits not available.
        """
        if self.min_setpoint is None or self.max_setpoint is None:
            return None

        from .constants import ControlMode

        # Use same conversion logic as get_display_value()
        if self.control_mode in (
            ControlMode.CONSTANT_PRESSURE,
            ControlMode.PROPORTIONAL_PRESSURE,
            ControlMode.CONSTANT_DIFF_PRESSURE,
            ControlMode.PROPORTIONAL_DIFF_PRESSURE,
            ControlMode.AUTO_ADAPT_RADIATOR,
            ControlMode.AUTO_ADAPT_UNDERFLOOR,
            ControlMode.AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR,
        ):
            min_val = self.min_setpoint / 9806.65
            max_val = self.max_setpoint / 9806.65
            return ((min_val, "m"), (max_val, "m"))

        elif self.control_mode in (
            ControlMode.CONSTANT_FLOW,
            ControlMode.FLOW_ADAPT,
        ):
            return ((self.min_setpoint, "m³/h"), (self.max_setpoint, "m³/h"))

        elif self.control_mode == ControlMode.CONSTANT_SPEED:
            return ((self.min_setpoint, "RPM"), (self.max_setpoint, "RPM"))

        elif self.control_mode in (
            ControlMode.CONSTANT_TEMPERATURE,
            ControlMode.CONSTANT_DIFF_TEMP,
            ControlMode.TEMPERATURE_RANGE_CONTROL,
        ):
            return ((self.min_setpoint, "°C"), (self.max_setpoint, "°C"))

        elif self.control_mode == ControlMode.CONSTANT_LEVEL:
            return ((self.min_setpoint, "m"), (self.max_setpoint, "m"))

        else:
            return ((self.min_setpoint, "units"), (self.max_setpoint, "units"))


class DeviceInfo(BaseModel):
    """Device identification and version information."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    # BLE Discovery fields
    address: str | None = Field(default=None, description="BLE MAC address")
    name: str | None = Field(default=None, description="BLE device name")

    # Product identification
    product_family: int | None = Field(
        default=None, description="Product family code (52=ALPHA)"
    )
    product_type: int | None = Field(
        default=None, description="Product type (7=HWR)"
    )
    product_version: int | None = Field(
        default=None, description="Product version"
    )
    product_name: str | None = Field(
        default=None, description="User-defined product name"
    )
    product_number: str | None = Field(
        default=None, description="Device product number"
    )
    serial_number: str | None = Field(default=None, description="Serial number")
    production_year_week: str | None = Field(
        default=None, description="Production date (YYWW)"
    )

    # Firmware versions
    software_version: str | None = Field(
        default=None, description="Software version"
    )
    hardware_version: str | None = Field(
        default=None, description="Hardware version"
    )
    ble_version: str | None = Field(
        default=None, description="BLE firmware version"
    )
    bootloader_version: str | None = Field(
        default=None, description="Bootloader version"
    )
    protocol_version: str | None = Field(
        default=None, description="Protocol version"
    )
    configuration_version: str | None = Field(
        default=None, description="Configuration version"
    )


class Statistics(BaseModel):
    """Cumulative operating statistics."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    operating_hours: float | None = Field(
        default=None, description="Total operating hours"
    )
    start_count: int | None = Field(
        default=None, description="Number of starts"
    )
    energy_kwh: float | None = Field(
        default=None, description="Total energy consumption in kWh"
    )


class AlarmInfo(BaseModel):
    """Alarm and warning information."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    alarm_code: int | None = Field(
        default=None, description="Current alarm code (0=no alarm)"
    )
    warning_code: int | None = Field(
        default=None, description="Current warning code (0=no warning)"
    )
    alarm_description: str | None = Field(
        default=None, description="Human-readable alarm description"
    )
    warning_description: str | None = Field(
        default=None, description="Human-readable warning description"
    )
    active_alarms: list[int] = Field(
        default_factory=list, description="List of active alarm codes"
    )
    active_warnings: list[int] = Field(
        default_factory=list, description="List of active warning codes"
    )


class ScheduleEntry(BaseModel):
    """
    Schedule entry for pump operation timing.

    Represents a single time window when the pump should operate.
    Includes validation for time ranges and overlap detection.

    Notes
    -----
    The `enabled` field indicates whether this specific day has an active schedule
    in the pump's internal storage. When reading schedules via get_schedule(),
    only enabled entries are returned. There is no way to "disable" an entry -
    you can only clear/remove it entirely. The enabled field is primarily used
    internally for the binary protocol format.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=False)

    # Valid day names for validation
    VALID_DAYS: ClassVar[list[str]] = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    day: str = Field(description="Day of week (Monday-Sunday)")
    begin_hour: int = Field(ge=0, le=23, description="Start hour (0-23)")
    begin_minute: int = Field(ge=0, le=59, description="Start minute (0-59)")
    end_hour: int = Field(ge=0, le=23, description="End hour (0-23)")
    end_minute: int = Field(ge=0, le=59, description="End minute (0-59)")
    action: int = Field(default=0x02, description="Action code (0x02=run pump)")
    layer: int = Field(
        default=0, ge=0, le=4, description="Schedule layer (0-4)"
    )
    enabled: bool = Field(
        default=True, description="Whether this entry is active"
    )

    @field_validator("day")
    @classmethod
    def validate_day(cls, v: str) -> str:
        """Validate day name is one of the valid weekdays (case-insensitive)."""
        # Normalize to Title Case (e.g. 'monday' -> 'Monday')
        normalized = v.capitalize()
        if normalized not in cls.VALID_DAYS:
            raise ValueError(f"Day must be one of {cls.VALID_DAYS}, got '{v}'")
        return normalized

    @property
    def day_index(self) -> int:
        """Get day index (0=Monday, 6=Sunday)."""
        return self.VALID_DAYS.index(self.day)

    @property
    def begin_time(self) -> str:
        """Get formatted begin time (HH:MM)."""
        return f"{self.begin_hour:02d}:{self.begin_minute:02d}"

    @property
    def end_time(self) -> str:
        """Get formatted end time (HH:MM)."""
        return f"{self.end_hour:02d}:{self.end_minute:02d}"

    @property
    def begin_time_obj(self) -> time:
        """Get begin time as datetime.time object."""
        return time(hour=self.begin_hour, minute=self.begin_minute)

    @property
    def end_time_obj(self) -> time:
        """Get end time as datetime.time object."""
        return time(hour=self.end_hour, minute=self.end_minute)

    def get_duration_minutes(self) -> int:
        """
        Calculate entry duration in minutes.

        Returns:
            Duration in minutes. If end time is before begin time,
            assumes the schedule crosses midnight and calculates accordingly.

        Examples:
            - 06:00 to 08:00 = 120 minutes
            - 22:00 to 02:00 = 240 minutes (crosses midnight)
        """
        begin_mins = self.begin_hour * 60 + self.begin_minute
        end_mins = self.end_hour * 60 + self.end_minute

        if end_mins < begin_mins:
            # Crosses midnight: time until midnight + time from midnight
            return (24 * 60 - begin_mins) + end_mins

        return end_mins - begin_mins

    def crosses_midnight(self) -> bool:
        """
        Check if this schedule entry crosses midnight.

        Returns:
            True if end time is before begin time (indicating midnight crossing)
        """
        begin_mins = self.begin_hour * 60 + self.begin_minute
        end_mins = self.end_hour * 60 + self.end_minute
        return end_mins < begin_mins

    def overlaps_with(self, other: "ScheduleEntry") -> bool:
        """
        Check if this entry overlaps with another entry.

        Only checks for overlap if both entries are:
        - On the same day
        - On the same layer
        - Both enabled

        Args:
            other: Another ScheduleEntry to compare with

        Returns:
            True if the entries overlap in time

        Examples:
            - 06:00-08:00 and 07:00-09:00 = True (overlap)
            - 06:00-08:00 and 08:00-10:00 = False (adjacent, no overlap)
            - 06:00-08:00 and 10:00-12:00 = False (separate)
            - 22:00-02:00 and 01:00-03:00 = True (both cross midnight, overlap)
        """
        # Only check overlap if same day, same layer, and both enabled
        if self.day != other.day:
            return False
        if self.layer != other.layer:
            return False
        if not self.enabled or not other.enabled:
            return False

        # Convert times to minutes since midnight for easier comparison
        self_begin = self.begin_hour * 60 + self.begin_minute
        self_end = self.end_hour * 60 + self.end_minute
        other_begin = other.begin_hour * 60 + other.begin_minute
        other_end = other.end_hour * 60 + other.end_minute

        # Handle midnight crossing
        self_crosses = self.crosses_midnight()
        other_crosses = other.crosses_midnight()

        if not self_crosses and not other_crosses:
            # Simple case: neither crosses midnight
            # Overlap if: self_begin < other_end AND other_begin < self_end
            return self_begin < other_end and other_begin < self_end

        elif self_crosses and not other_crosses:
            # Self crosses midnight: runs from [self_begin to 23:59] AND [00:00 to self_end]
            # Other is normal: [other_begin to other_end]
            #
            # Overlap cases:
            # 1. Other is in evening segment: other_begin >= self_begin (in evening part)
            # 2. Other is in morning segment: other_begin < self_end OR other_end <= self_end
            #    (other starts or ends in morning part)
            in_evening_segment = other_begin >= self_begin
            overlaps_morning_segment = (other_begin < self_end) or (
                other_end <= self_end
            )
            return in_evening_segment or overlaps_morning_segment

        elif not self_crosses and other_crosses:
            # Other crosses midnight, self doesn't
            # Mirror logic: check if self overlaps with other's evening or morning segments
            in_evening_segment = self_begin >= other_begin
            overlaps_morning_segment = (self_begin < other_end) or (
                self_end <= other_end
            )
            return in_evening_segment or overlaps_morning_segment

        else:
            # Both cross midnight - they definitely overlap somewhere
            return True

    def is_valid_time_range(self) -> tuple[bool, str | None]:
        """
        Validate that the time range is sensible.

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if valid
            - (False, "error message") if invalid

        Checks:
            - Duration is not zero
            - Times are not identical
        """
        duration = self.get_duration_minutes()

        if duration == 0:
            return (
                False,
                f"Invalid time range: begin and end times are identical ({self.begin_time})",
            )

        # All checks passed
        return (True, None)

    def to_dict(self) -> dict:
        """
        Convert to dictionary format matching get_schedule() output.

        Returns:
            Dictionary with all schedule entry fields
        """
        return {
            "day": self.day,
            "enabled": self.enabled,
            "action": self.action,
            "begin_hour": self.begin_hour,
            "begin_minute": self.begin_minute,
            "end_hour": self.end_hour,
            "end_minute": self.end_minute,
            "begin_time": self.begin_time,
            "end_time": self.end_time,
            "layer": self.layer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleEntry":
        """
        Create ScheduleEntry from dictionary (e.g., from get_schedule() output).

        Args:
            data: Dictionary with schedule entry fields

        Returns:
            ScheduleEntry instance
        """
        return cls(
            day=data["day"],
            begin_hour=data["begin_hour"],
            begin_minute=data["begin_minute"],
            end_hour=data["end_hour"],
            end_minute=data["end_minute"],
            action=data.get("action", 0x02),
            layer=data.get("layer", 0),
            enabled=data.get("enabled", True),
        )

    def to_bytes(self) -> bytes:
        """
        Convert to 6-byte binary format for writing to pump.

        Format:
            Byte 0: Enabled flag (0x01 if enabled, 0x00 if disabled)
            Byte 1: Action code (0x02 for run)
            Byte 2: Start hour (0-23)
            Byte 3: Start minute (0-59)
            Byte 4: End hour (0-23)
            Byte 5: End minute (0-59)

        Returns:
            6-byte binary representation
        """
        return bytes(
            [
                0x01 if self.enabled else 0x00,
                self.action,
                self.begin_hour,
                self.begin_minute,
                self.end_hour,
                self.end_minute,
            ]
        )

    @classmethod
    def from_bytes(
        cls, data: bytes, day: str, layer: int = 0
    ) -> "ScheduleEntry":
        """
        Parse from 6-byte binary format.

        Args:
            data: 6-byte binary data
            day: Day name for this entry
            layer: Schedule layer (0-4)

        Returns:
            ScheduleEntry instance

        Raises:
            ValueError: If data is not 6 bytes
        """
        if len(data) != 6:
            raise ValueError(f"Expected 6 bytes, got {len(data)}")

        return cls(
            day=day,
            enabled=data[0] != 0,
            action=data[1],
            begin_hour=data[2],
            begin_minute=data[3],
            end_hour=data[4],
            end_minute=data[5],
            layer=layer,
        )


class TrendDataPoint(BaseModel):
    """Single data point in a trend series."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    timestamp: datetime
    value: float


class TrendDataSeries(BaseModel):
    """
    A series of trend data points for a specific metric.

    Contains two sets of data:
    - 10-cycle: High frequency recent data
    - 100-cycle: Lower frequency historical data
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    unit: str
    cycle_10_points: list[TrendDataPoint]
    cycle_100_points: list[TrendDataPoint]


class TrendDataCollection(BaseModel):
    """Collection of all trend data series."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    flow_series: TrendDataSeries | None = None
    head_series: TrendDataSeries | None = None
    media_temperature_series: TrendDataSeries | None = None
    power_on_time_series: TrendDataSeries | None = None


class AdvancedTelemetry(BaseModel):
    """
    Advanced telemetry metrics from GENI DataObjects.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    timestamp: datetime = Field(default_factory=datetime.now)

    # Detailed temperatures
    converter_temperature_c: float | None = Field(
        default=None, description="Converter temperature in Celsius"
    )
    pcb_temperature_c: float | None = Field(
        default=None, description="PCB temperature in Celsius"
    )
    control_box_temperature_c: float | None = Field(
        default=None, description="Control box temperature in Celsius"
    )

    # Detailed pressures
    inlet_pressure_bar: float | None = Field(
        default=None, description="Inlet pressure in bar"
    )
    outlet_pressure_bar: float | None = Field(
        default=None, description="Outlet pressure in bar"
    )

    # Alerts
    active_alarms: list[int] = Field(
        default_factory=list, description="List of active alarm codes"
    )
    active_warnings: list[int] = Field(
        default_factory=list, description="List of active warning codes"
    )


class EventLogEntry(BaseModel):
    """
    Single event log entry from the pump.

    The pump maintains a circular buffer of 20 event log entries
    (SubID 10200-10219), where 0 is the newest and 19 is the oldest.

    Each entry is 16 bytes containing timestamp, cycle counter, mode,
    and event type information.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index: int = Field(description="Entry index (0=newest, 19=oldest)")
    subid: int = Field(
        description="SubID this entry was read from (10200-10219)"
    )
    cycle_counter: int = Field(
        description="Pump cycle counter at time of event"
    )
    timestamp: datetime = Field(description="Event timestamp (UTC)")
    mode_byte: int = Field(description="Mode byte (raw value)")
    event_type_flag: int = Field(description="Event type flag")
    raw_hex: str = Field(description="Raw hex data of the entry")


class EventLogMetadata(BaseModel):
    """
    Metadata about the event log (SubID 10199).

    The metadata is 7 bytes containing information about the current
    cycle counter and number of available entries in the log.

    Structure (7 bytes):
    - Bytes 0-1: Current cycle counter (uint16 BE)
    - Bytes 2-3: Available entries (uint16 BE)
    - Bytes 4-5: Max buffer size (uint16 BE, always 20)
    - Byte  6:   Reserved/flags (uint8, typically 0)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    current_cycle: int = Field(
        description="Current pump cycle counter (highest cycle in log)"
    )
    available_entries: int = Field(
        description="Number of available entries in the log (0-20)"
    )
    max_buffer_size: int = Field(description="Maximum buffer size (always 20)")
    reserved: int = Field(description="Reserved byte (typically 0)")
    raw_hex: str = Field(description="Raw hex data for debugging")
