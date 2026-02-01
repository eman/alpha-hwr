# Hardware Reference

The **Grundfos ALPHA HWR** (Hot Water Recirculation) is a smart circulator pump designed for domestic hot water systems with a dedicated return line. It features integrated sensors and Bluetooth connectivity, allowing for app-based control and monitoring.

## Models

There are two primary variants of the ALPHA HWR, differentiated mainly by their performance curves (Head/Flow capability).

| Feature | ALPHA HWR 15-55 | ALPHA HWR 15-29 |
| :--- | :--- | :--- |
| **Max Flow Rate (Q)** | 13.6 GPM ($3.1 m^3/h$) | 11 GPM ($2.5 m^3/h$) |
| **Max Head (H)** | 18 ft (5.5 m) | 9.5 ft (2.9 m) |
| **Power Consumption** | 2 - 38 W | 2 - 21 W |

## Technical Specifications

| Parameter | Value | Notes |
| :--- | :--- | :--- |
| **Supply Voltage** | 1 x 115 V, ± 10 %, 60 Hz | |
| **Max Outlet Pressure** | 175 psi (12 bar) | |
| **Liquid Temperature** | 36 - 203 °F (2 - 95 °C) | Hard water deposits may occur > 140°F |
| **Ambient Temperature** | 32 - 131 °F (0 - 55 °C) | |
| **Relative Humidity** | Max 95% | |
| **Sound Pressure** | < 25 dB(A) | Silent operation |
| **Pump Housing** | Stainless Steel | |
| **Enclosure Class** | Type 2 | Indoor use only |

## Alarm & Warning Codes

The pump reports internal error states via the `status_code` field in the telemetry stream.

| Code | Error Type | Description |
| :--- | :--- | :--- |
| **51** | **Blocked Motor** | The rotor is jammed or blocked by debris. |
| **57** | **Dry Running** | The pump detects no water in the housing. |
| **40** | **Undervoltage** | Supply voltage is too low. |
| **4** | **Overvoltage** | Supply voltage is too high. |
| **35** | **Air in Media** | Significant air bubbles detected in the system. |
| **72, 76, 85** | **Internal Fault** | Electronics or internal hardware failure. |
| **29** | **Forced Pumping** | Water is being forced through the pump by another source. |
| **43** | **Impellers Forced** | Impellers are being forced forward. |

## Hardware Features

### Integrated Temperature Sensor
The pump includes an internal sensor that estimates the media temperature. This eliminates the need for an external aquastat in many recirculation setups.

*   *Note: The sensor value is available in the telemetry stream as `media_temperature_c`.*

### Air Detection & Venting
The ALPHA HWR has a "Continuous Air Detection" feature. If air is detected (Code 35), the pump can run a special venting sequence to push air to the system vent.

### Flow Limitation
The pump logic includes safety limits based on pipe diameters to prevent flow-accelerated corrosion.
*   **1/2" pipes**: ~1.5 GPM limit
*   **3/4" pipes**: ~2.3 GPM limit
*   **1" pipes**: ~3.8 GPM limit

## Operating Panel vs. Digital Control

The physical operating panel on the pump is limited to selecting three basic modes:
1.  **AutoAdapt**: Temperature control (95-102°F range).
2.  **Temperature Control**: Fixed temp control.
3.  **Continuous (24/7)**: Constant Curve III.

**Advanced Control**: Using the Bluetooth interface unlocks the full range of control modes, including Constant Pressure, Constant Flow, and custom setpoints.