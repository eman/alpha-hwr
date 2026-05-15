#!/usr/bin/env python3
"""
Hardware verification script for issue #24 regression testing.

Connects to a local ALPHA HWR pump via BLE, reads telemetry and device
information to verify the fix for:
  - Sequential extension packet ordering (EXTEND_1 then EXTEND_2)
  - Bleak 3.x compatibility (_make_bleak_client adapter handling)
  - Disconnection guard in read_once (is_connected checks)

Usage:
    # Auto-discover pump:
    .venv/bin/python scripts/verify_hardware.py

    # Specify address directly:
    .venv/bin/python scripts/verify_hardware.py --address <BLE_ADDRESS>
"""

from __future__ import annotations

import asyncio
import logging
import sys
from importlib.metadata import version as pkg_version

import typer

from alpha_hwr.client import AlphaHWRClient

app = typer.Typer(add_completion=False)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    if not verbose:
        # Suppress noisy third-party loggers unless verbose
        logging.getLogger("bleak").setLevel(logging.WARNING)


async def _run(address: str | None, verbose: bool) -> int:
    _setup_logging(verbose)

    bleak_ver = pkg_version("bleak")
    alpha_ver = pkg_version("alpha-hwr")
    print(f"alpha-hwr {alpha_ver}  |  bleak {bleak_ver}  |  Python {sys.version.split()[0]}")
    print()

    # ------------------------------------------------------------------ #
    # Discovery                                                            #
    # ------------------------------------------------------------------ #
    if address is None:
        print("Scanning for ALPHA HWR pumps (10 s)...")
        devices = await AlphaHWRClient.discover(timeout=10.0)
        if not devices:
            print("ERROR: No ALPHA HWR pumps found. Is the device powered on and in range?")
            return 1
        print(f"Found {len(devices)} pump(s):")
        for d in devices:
            print(f"  - {d.name or 'Unknown'}  [{d.address}]")
        address = devices[0].address
        print(f"\nUsing first device: {address}")
    else:
        print(f"Using specified address: {address}")

    print()

    # ------------------------------------------------------------------ #
    # Connection + verification                                            #
    # ------------------------------------------------------------------ #
    passed: list[str] = []
    failed: list[str] = []

    try:
        async with AlphaHWRClient(address) as client:
            print("Connected and authenticated successfully.")
            passed.append("Connection and authentication")

            # -- Firmware / device info --------------------------------- #
            print("\n--- Device Information ---")
            try:
                info = await client.device_info.read_info()
                if info:
                    print(f"  Product name : {info.product_name or 'N/A'}")
                    print(f"  BLE firmware : {info.ble_version or 'N/A'}")
                    if info.ble_version:
                        passed.append(f"Firmware detected: {info.ble_version}")
                    else:
                        failed.append("BLE firmware version not returned")
                else:
                    print("  (no device info returned)")
                    failed.append("read_info returned None")
            except Exception as exc:
                print(f"  ERROR reading device info: {exc}")
                failed.append(f"Device info error: {exc}")

            # -- Telemetry ---------------------------------------------- #
            print("\n--- Telemetry ---")
            try:
                telemetry = await client.telemetry.read_once()
                if telemetry is not None:
                    print(f"  Flow     : {telemetry.flow_m3h} m3/h")
                    print(f"  Head     : {telemetry.head_m} m")
                    print(f"  Power    : {telemetry.power_w} W")
                    if telemetry.flow_m3h is not None:
                        passed.append("Telemetry flow_m3h populated")
                    else:
                        failed.append("flow_m3h is None (possible regression)")
                    if telemetry.head_m is not None:
                        passed.append("Telemetry head_m populated")
                    else:
                        failed.append("head_m is None (possible regression)")
                else:
                    print("  Telemetry returned None")
                    failed.append("read_once returned None")
            except Exception as exc:
                print(f"  ERROR reading telemetry: {exc}")
                failed.append(f"Telemetry error: {exc}")

            # -- Control mode ------------------------------------------- #
            print("\n--- Control Mode ---")
            try:
                mode_info = await client.control.get_mode()
                if mode_info:
                    mode_name = (
                        mode_info.control_mode.name
                        if hasattr(mode_info.control_mode, "name")
                        else f"unknown({mode_info.control_mode})"
                    )
                    print(f"  Mode : {mode_name}")
                    value, unit = mode_info.get_display_value()
                    print(f"  Setpoint: {value:.2f} {unit}")
                    passed.append("Control mode read")
                else:
                    print("  (no control mode data)")
                    failed.append("get_mode returned None")
            except Exception as exc:
                print(f"  ERROR reading control mode: {exc}")
                failed.append(f"Control mode error: {exc}")

    except Exception as exc:
        print(f"\nFATAL: Could not connect/authenticate: {exc}")
        failed.append(f"Connection failed: {exc}")
        logging.exception("Connection error")

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    for item in passed:
        print(f"  PASS  {item}")
    for item in failed:
        print(f"  FAIL  {item}")

    regression_keywords = ["Service Discovery", "BleakError", "regression", "None"]
    regressions = [f for f in failed if any(k in f for k in regression_keywords)]
    if regressions:
        print("\nPotential regressions detected (see FAIL lines above).")
        return 2

    if failed:
        print("\nSome checks failed - review output above.")
        return 1

    print("\nAll checks passed. No regressions detected.")
    return 0


@app.command()
def main(
    address: str | None = typer.Option(
        None, "--address", "-a", help="BLE device address. Auto-discovers if omitted."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Verify hardware connectivity and firmware info for issue #24 regression testing."""
    exit_code = asyncio.run(_run(address, verbose))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    app()
