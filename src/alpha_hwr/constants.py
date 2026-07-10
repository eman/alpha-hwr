from __future__ import annotations

from enum import IntEnum

# ============================================================================
# BLE UUIDs
# ============================================================================
GENI_SERVICE_UUID = "0000fdd0-0000-1000-8000-00805f9b34fb"
GENI_CHAR_UUID = "859cffd1-036e-432a-aa28-1a0085b87ba9"

# ============================================================================
# Protocol Constants
# ============================================================================
FRAME_START = 0x27
RESPONSE_START = 0x24
SERVICE_ID_HIGH = 0xE7
SERVICE_ID_LOW = 0xF8
RESERVED_BYTE = 0x0A

# ============================================================================
# Authoritative Unit Conversions (from resources/unit_conversion/unit_factor_mapping.csv)
# ============================================================================
# Factor is dividend: to_unit = from_unit / factor
FACTOR_M3H_TO_GPM = 0.22712470704
FACTOR_M_TO_FT = 0.3048
FACTOR_M_TO_PSI = 0.70329
FACTOR_CELSIUS_TO_FAHRENHEIT = 0.555555555555556  # (9/5)^-1

# Class 10 DataObjects
CLASS_10 = 0x0A

# ============================================================================
# Authentication Sequences
# ============================================================================
# Legacy/Nested Magic Packet
AUTH_LEGACY_MAGIC = bytes.fromhex("2707fff802039495964f91")

# Class 10 Unlock Packet
AUTH_CLASS10_MAGIC = bytes.fromhex("2707e7f80a03560006c55a")

# Auth Extend Packets
AUTH_EXTEND_1 = bytes.fromhex("2705e7f805c14bc382")
AUTH_EXTEND_2 = bytes.fromhex("2705e7f80bc10fd0c3")


# ============================================================================
# Enums
# ============================================================================
# Enums
# ============================================================================


class TelemetryObject:
    """
    Class 10 DataObject identifiers for telemetry requests.

    These are Object-ID and Sub-ID pairs used in Class 10 INFO commands
    to query telemetry data. Use these with FrameBuilder.build_data_object_info().

    Note:
        Tuple order is (Obj ID, Sub ID) to match the decoder match
        pattern in TelemetryDecoder.decode() and FrameParser.is_telemetry_frame().

    Example:
        >>> obj_id, sub_id = TelemetryObject.MOTOR_STATE
        >>> register = (obj_id << 16) | sub_id
        >>> req = FrameBuilder.build_data_object_info(register)
    """

    # (Obj ID, Sub ID) tuples
    MOTOR_STATE = (0x0057, 0x0045)  # Voltage, Current, Power, RPM, Temp
    FLOW_PRESSURE = (0x005D, 0x0122)  # Flow rate and head pressure
    TEMPERATURE = (0x005D, 0x012C)  # Media, PCB, control box temperatures
    # SETPOINT reserved for future use: passive notification of current RPM setpoint
    SETPOINT = (0x012F, 0x0001)


class Register(IntEnum):
    """GENI Register Addresses for Alpha HWR (Control/Configuration only)."""

    # Control Registers
    OPERATION_LOCAL_REQUEST = 0x560600
    OPERATION_LOCAL_MODE = 0x560700
    CONTROL_MODE_LOCAL_REQUEST = 0x560A00
    CONTROL_MODE_CP_USER_CONFIG = 0x561000
    CONTROL_MODE_CF_USER_CONFIG = 0x562800

    # Class 3 Commands (not used in BLE captures)
    RESET = 0x0301
    STOP = 0x0305
    AUTO = 0x0306
    REMOTE = 0x0307
    CONSTANT_FLOW = 0x0315
    CONSTANT_PRESSURE = 0x0318


class OperationMode(IntEnum):
    """
    Operation Mode from GENI Profile (id=6/81).
    XML: Auto=0, Stop=1, Min=2, Max=3, ...
    """

    AUTO = 0
    STOP = 1
    MIN = 2
    MAX = 3
    USER_DEFINED = 4
    FORCED_START = 5
    NO_CMD = 6
    HAND = 7
    STANDBY = 8
    STOP_WITHOUT_DELAY = 9
    EMERGENCY_RUN = 10


class ControlMode(IntEnum):
    """
    Control Mode from GENI Profile (id=112).
    XML: ConstPressure=0, PropPressure=1, ConstSpeed=2, AutoAdapt=5, ...
    """

    CONSTANT_PRESSURE = 0
    PROPORTIONAL_PRESSURE = 1
    CONSTANT_SPEED = 2
    AUTO_ADAPT = 5
    CONSTANT_TEMPERATURE = 6
    CLOSED_LOOP_SENSOR = 7
    CONSTANT_FLOW = 8
    CONSTANT_LEVEL = 9
    FLOW_ADAPT = 10
    CONSTANT_DIFF_PRESSURE = 11
    CONSTANT_DIFF_TEMP = 12
    AUTO_ADAPT_RADIATOR = 13
    AUTO_ADAPT_UNDERFLOOR = 14
    AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR = 15
    CONSTANT_DOSING = 16
    DISINFECTANT_CONTROL = 17
    FLOCCULENT_CONTROL = 18
    PH_CONTROL = 19
    PID_CONTROL = 20
    CONSTANT_RELATIVE_SETPOINT = 21
    LEVEL_CONTROL = 22
    ZONE_PUMP_CONTROL = 23
    USER_DEFINED = 24
    DHW_ON_OFF_CONTROL = 25
    PROPORTIONAL_DIFF_PRESSURE = 26
    TEMPERATURE_RANGE_CONTROL = 27
    COMFORT_VALVE_CONTROL = 28
    ON_OFF_CONTROL = 29
    CONSTANT_VOLTAGE = 30
    SYSTEM_AIR_VENTING = 128
    NONE = 254


MODE_NAMES = {
    ControlMode.CONSTANT_PRESSURE: "CONSTANT_PRESSURE",
    ControlMode.PROPORTIONAL_PRESSURE: "PROPORTIONAL_PRESSURE",
    ControlMode.CONSTANT_SPEED: "CONSTANT_SPEED",
    ControlMode.AUTO_ADAPT: "AUTO_ADAPT",
    ControlMode.CONSTANT_TEMPERATURE: "CONSTANT_TEMPERATURE",
    ControlMode.CLOSED_LOOP_SENSOR: "CLOSED_LOOP_SENSOR",
    ControlMode.CONSTANT_FLOW: "CONSTANT_FLOW",
    ControlMode.CONSTANT_LEVEL: "CONSTANT_LEVEL",
    ControlMode.FLOW_ADAPT: "FLOW_ADAPT",
    ControlMode.CONSTANT_DIFF_PRESSURE: "CONSTANT_DIFF_PRESSURE",
    ControlMode.CONSTANT_DIFF_TEMP: "CONSTANT_DIFF_TEMP",
    ControlMode.AUTO_ADAPT_RADIATOR: "AUTO_ADAPT_RADIATOR",
    ControlMode.AUTO_ADAPT_UNDERFLOOR: "AUTO_ADAPT_UNDERFLOOR",
    ControlMode.AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR: "AUTO_ADAPT_RADIATOR_AND_UNDERFLOOR",
    ControlMode.CONSTANT_DOSING: "CONSTANT_DOSING",
    ControlMode.DISINFECTANT_CONTROL: "DISINFECTANT_CONTROL",
    ControlMode.FLOCCULENT_CONTROL: "FLOCCULENT_CONTROL",
    ControlMode.PH_CONTROL: "PH_CONTROL",
    ControlMode.PID_CONTROL: "PID_CONTROL",
    ControlMode.CONSTANT_RELATIVE_SETPOINT: "CONSTANT_RELATIVE_SETPOINT",
    ControlMode.LEVEL_CONTROL: "LEVEL_CONTROL",
    ControlMode.ZONE_PUMP_CONTROL: "ZONE_PUMP_CONTROL",
    ControlMode.USER_DEFINED: "USER_DEFINED",
    ControlMode.DHW_ON_OFF_CONTROL: "DHW_ON_OFF_CONTROL",
    ControlMode.PROPORTIONAL_DIFF_PRESSURE: "PROPORTIONAL_DIFF_PRESSURE",
    ControlMode.TEMPERATURE_RANGE_CONTROL: "TEMPERATURE_RANGE_CONTROL",
    ControlMode.COMFORT_VALVE_CONTROL: "COMFORT_VALVE_CONTROL",
    ControlMode.ON_OFF_CONTROL: "ON_OFF_CONTROL",
    ControlMode.CONSTANT_VOLTAGE: "CONSTANT_VOLTAGE",
    ControlMode.SYSTEM_AIR_VENTING: "SYSTEM_AIR_VENTING",
    ControlMode.NONE: "NONE",
}


# ============================================================================
# Error Codes (Alarms and Warnings)
# ============================================================================
# From GENI Profile enum ErrorCode (geni_profile_52_7.xml)
# Note: Code 160 is not defined in the GENI profile and may be undocumented
ERROR_CODES = {
    0: "OK",
    1: "Leakage Current",
    2: "Motor Phase Missing",
    3: "External Alarm",
    4: "Max Number of Restarts",
    7: "Too Many Hardware Shutdowns",
    9: "Motor Phase Sequence Reversal",
    10: "Pump Communication",
    12: "Service Interval",
    14: "Electronic DC Link Protection",
    15: "Communication Fault Main System",
    16: "Other",
    17: "Low System Performance",
    19: "Diaphragm Break",
    21: "Too Many Starts Per Hour",
    22: "Motor Moisture",
    24: "Vibration",
    25: "User Wrong Configuration",
    26: "Welding Contactor",
    28: "Battery Low",
    29: "Impeller Forced Backwards",
    30: "Bearing Wear",
    31: "Varistor Change",
    32: "Over Voltage",
    33: "Service Soon",
    35: "Air in Pump Head",
    36: "Discharge Valve Leakage",
    37: "Suction Valve Leakage",
    39: "Mixing Loop Valve Stuck",
    40: "Motor Low Supply Voltage",
    41: "Motor Low Supply Voltage Transient",
    42: "Cut-In Fault",
    43: "Motor Positive Turbine Operation",
    44: "Under Temperature",
    45: "Voltage Asymmetry",
    46: "External Warning",
    48: "Motor Over Load",
    49: "Motor Over Current",
    50: "Motor Protection General Shut Down",
    51: "Motor Blocked",
    54: "Motor Protection Function 3 Seconds Limit",
    55: "Motor Current Protection",
    56: "Motor Under Load",
    57: "Dry Run",
    58: "Low Flow",
    59: "No Flow",
    60: "Low Input Power",
    61: "Water Hammer",
    63: "Media Temperature Frozen Protection",
    64: "Over Temperature",
    65: "Motor Over Temperature",
    66: "Control Electronics Over Temperature",
    67: "Power Converter Over Temperature",
    68: "High Media Temperature Protection",
    69: "Motor Over Heated",
    70: "Motor Over Heated Thermal Relay 2",
    72: "Motor Drive Unit Internal Fault",
    73: "Hardware Shut Down",
    74: "Motor High DC Link Voltage",
    75: "Motor Low DC Link Voltage",
    76: "PMCM Lost Node Internal",
    77: "Twin Pumps Communication Fault",
    80: "Hardware Fault Type 2",
    83: "FE Parameter Area Verification Error",
    84: "Persistence Break Down",
    85: "Motor Drive Unit Memory Fault",
    87: "Multi Sensor Limit Exceeded",
    88: "General Sensor Fault",
    89: "Primary Feedback Sensor Signal Fault",
    90: "Speed Sensor Signal Fault",
    91: "Pump Flow Temperature Sensor",
    92: "Feedback Sensor Calibration Fault",
    93: "Fallback Sensor Signal Fault",
    94: "Limit Exceeded 1",
    95: "Limit Exceeded 2",
    96: "Reference Input Signal Fault",
    97: "Invalid Setpoint",
    105: "Electronic Rectifier Protection",
    106: "Electronic Inverter Protection",
    110: "Electrical Asymmetry",
    114: "Frost Protection",
    117: "Door Opened",
    125: "Outdoor Temperature Sensor",
    126: "Zone Air Supply Temperature Sensor",
    127: "Shunt Relative Pressure Sensor",
    130: "Cable Theft",
    131: "Unbalance",
    132: "Invalid GSC File",
    133: "Generic Limit Exceeded",
    134: "Data Fault from Remote Sensors",
    142: "Running on Battery Common",
    143: "Multi Sensor Signal Fault",
    148: "Motor Drive End Bearing Temperature High",
    149: "Motor Non Drive End Bearing Temperature High",
    152: "Communication Fault Add-On Module",
    155: "Inrush Fault",
    156: "Internal Freq Converter Communication",
    157: "Real Time Clock Out of Order",
    159: "CIM Communication",
    160: "Unknown Error (Not in GENI Profile)",
    161: "Sensor Supply Fault 5V/12V",
    162: "Sensor Supply Fault 24V",
    163: "Motor Drive Unit Configuration Fault",
    164: "LiqTec Sensor Signal Fault",
    165: "AI Signal Fault",
    166: "AI2 Signal Fault",
    167: "AI3 Signal Fault",
    168: "Pressure Sensor Signal Fault",
    169: "Flow Sensor Signal Fault",
    175: "Supply Flow Temperature Sensor",
    176: "Return Flow Temperature Sensor",
    181: "PTC Sensor Signal Fault",
    190: "Sensor 1 Limit Exceeded",
    191: "Level Control High Water",
    193: "Sensor Limit 4 Exceeded",
    197: "Operation with Reduced Pressure",
    200: "Application Fault",
    203: "Alarm on All Pumps",
    204: "Inconsistency Between Sensors",
    205: "Level Switch Inconsistency",
    206: "Water Shortage Level 1",
    207: "Water Leakage",
    208: "Cavitation",
    209: "Non-Return Valve Fault",
    210: "Overpressure",
    211: "Shunt Relative Pressure Surveillance",
    215: "Pipe Filling Time Out",
    220: "Motor Contactor Wear Out",
    225: "PMCM Lost Node External",
    226: "IO Module Communication",
    228: "Flow Switch Monitoring",
    229: "Water on Floor",
    230: "Invalid MAC Address",
    236: "Pump Fault",
    237: "Pump 2 Fault",
    240: "Motor Bearing Lubrication",
    241: "Motor Phase Failure",
    242: "Motor Model Auto Recognition Failure",
    245: "Pump Max Running Time Protection",
    247: "Power On Notice",
    248: "Running on Battery",
    249: "User Configurable Alert",
    250: "User Configurable Alert 1",
    255: "Electronics Short Circuit Fault",
}


class CommandOpcode(IntEnum):
    """GENI Command Opcodes."""

    SET = 0x02
    READ = 0x03
    WRITE = 0xC1
    EXECUTE = 0x05


# CRC-16-CCITT Lookup Table
CRC_TABLE = [
    0x0000,
    0x1021,
    0x2042,
    0x3063,
    0x4084,
    0x50A5,
    0x60C6,
    0x70E7,
    0x8108,
    0x9129,
    0xA14A,
    0xB16B,
    0xC18C,
    0xD1AD,
    0xE1CE,
    0xF1EF,
    0x1231,
    0x0210,
    0x3273,
    0x2252,
    0x52B5,
    0x4294,
    0x72F7,
    0x62D6,
    0x9339,
    0x8318,
    0xB37B,
    0xA35A,
    0xD3BD,
    0xC39C,
    0xF3FF,
    0xE3DE,
    0x2462,
    0x3443,
    0x0420,
    0x1401,
    0x64E6,
    0x74C7,
    0x44A4,
    0x5485,
    0xA56A,
    0xB54B,
    0x8528,
    0x9509,
    0xE5EE,
    0xF5CF,
    0xC5AC,
    0xD58D,
    0x3653,
    0x2672,
    0x1611,
    0x0630,
    0x76D7,
    0x66F6,
    0x5695,
    0x46B4,
    0xB75B,
    0xA77A,
    0x9719,
    0x8738,
    0xF7DF,
    0xE7FE,
    0xD79D,
    0xC7BC,
    0x48C4,
    0x58E5,
    0x6886,
    0x78A7,
    0x0840,
    0x1861,
    0x2802,
    0x3823,
    0xC9CC,
    0xD9ED,
    0xE98E,
    0xF9AF,
    0x8948,
    0x9969,
    0xA90A,
    0xB92B,
    0x5AF5,
    0x4AD4,
    0x7AB7,
    0x6A96,
    0x1A71,
    0x0A50,
    0x3A33,
    0x2A12,
    0xDBFD,
    0xCBDC,
    0xFBBF,
    0xEB9E,
    0x9B79,
    0x8B58,
    0xBB3B,
    0xAB1A,
    0x6CA6,
    0x7C87,
    0x4CE4,
    0x5CC5,
    0x2C22,
    0x3C03,
    0x0C60,
    0x1C41,
    0xEDAE,
    0xFD8F,
    0xCDEC,
    0xDDCD,
    0xAD2A,
    0xBD0B,
    0x8D68,
    0x9D49,
    0x7E97,
    0x6EB6,
    0x5ED5,
    0x4EF4,
    0x3E13,
    0x2E32,
    0x1E51,
    0x0E70,
    0xFF9F,
    0xEFBE,
    0xDFDD,
    0xCFFC,
    0xBF1B,
    0xAF3A,
    0x9F59,
    0x8F78,
    0x9188,
    0x81A9,
    0xB1CA,
    0xA1EB,
    0xD10C,
    0xC12D,
    0xF14E,
    0xE16F,
    0x1080,
    0x00A1,
    0x30C2,
    0x20E3,
    0x5004,
    0x4025,
    0x7046,
    0x6067,
    0x83B9,
    0x9398,
    0xA3FB,
    0xB3DA,
    0xC33D,
    0xD31C,
    0xE37F,
    0xF35E,
    0x02B1,
    0x1290,
    0x22F3,
    0x32D2,
    0x4235,
    0x5214,
    0x6277,
    0x7256,
    0xB5EA,
    0xA5CB,
    0x95A8,
    0x8589,
    0xF56E,
    0xE54F,
    0xD52C,
    0xC50D,
    0x34E2,
    0x24C3,
    0x14A0,
    0x0481,
    0x7466,
    0x6447,
    0x5424,
    0x4405,
    0xA7DB,
    0xB7FA,
    0x8799,
    0x97B8,
    0xE75F,
    0xF77E,
    0xC71D,
    0xD73C,
    0x26D3,
    0x36F2,
    0x0691,
    0x16B0,
    0x6657,
    0x7676,
    0x4615,
    0x5634,
    0xD94C,
    0xC96D,
    0xF90E,
    0xE92F,
    0x99C8,
    0x89E9,
    0xB98A,
    0xA9AB,
    0x5844,
    0x4865,
    0x7806,
    0x6827,
    0x18C0,
    0x08E1,
    0x3882,
    0x28A3,
    0xCB7D,
    0xDB5C,
    0xEB3F,
    0xFB1E,
    0x8BF9,
    0x9BD8,
    0xABBB,
    0xBB9A,
    0x4A75,
    0x5A54,
    0x6A37,
    0x7A16,
    0x0AF1,
    0x1AD0,
    0x2AB3,
    0x3A92,
    0xFD2E,
    0xED0F,
    0xDD6C,
    0xCD4D,
    0xBDAA,
    0xAD8B,
    0x9DE8,
    0x8DC9,
    0x7C26,
    0x6C07,
    0x5C64,
    0x4C45,
    0x3CA2,
    0x2C83,
    0x1CE0,
    0x0CC1,
    0xEF1F,
    0xFF3E,
    0xCF5D,
    0xDF7C,
    0xAF9B,
    0xBFBA,
    0x8FD9,
    0x9FF8,
    0x6E17,
    0x7E36,
    0x4E55,
    0x5E74,
    0x2E93,
    0x3EB2,
    0x0ED1,
    0x1EF0,
]
