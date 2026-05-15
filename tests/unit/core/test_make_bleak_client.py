"""
Unit tests for _make_bleak_client().

Verifies correct BleakClient construction for Bleak 2.x vs 3.x and
Linux vs non-Linux platforms, including the PackageNotFoundError fallback.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch


from alpha_hwr.client import _make_bleak_client

ADDRESS = "AA:BB:CC:DD:EE:FF"
ADAPTER = "hci1"


def _patch_version(version_str: str):
    """Return a context manager that patches _pkg_version to return version_str."""
    return patch("alpha_hwr.client._pkg_version", return_value=version_str)


def _patch_platform(platform: str):
    """Return a context manager that patches sys.platform."""
    return patch("alpha_hwr.client.sys.platform", platform)


# ---------------------------------------------------------------------------
# No adapter — always returns plain BleakClient(address)
# ---------------------------------------------------------------------------


def test_no_adapter_returns_plain_client() -> None:
    """When adapter is None, version/platform are never consulted."""
    with (
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
        patch("alpha_hwr.client._pkg_version") as mock_ver,
    ):
        _make_bleak_client(ADDRESS, None)

    mock_bleak.assert_called_once_with(ADDRESS)
    mock_ver.assert_not_called()


def test_empty_adapter_returns_plain_client() -> None:
    """Empty string adapter is treated the same as None."""
    with patch("alpha_hwr.client.BleakClient") as mock_bleak:
        _make_bleak_client(ADDRESS, "")

    mock_bleak.assert_called_once_with(ADDRESS)


# ---------------------------------------------------------------------------
# Bleak 3.x on Linux — use bluez= kwarg
# ---------------------------------------------------------------------------


def test_bleak3_linux_uses_bluez_kwarg() -> None:
    """Bleak >= 3 on Linux must use bluez={'adapter': ...}."""
    with (
        _patch_version("3.0.0"),
        _patch_platform("linux"),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS, bluez={"adapter": ADAPTER})


def test_bleak3_future_version_linux_uses_bluez_kwarg() -> None:
    """Any Bleak major version >= 3 on Linux should use bluez=."""
    with (
        _patch_version("4.1.0"),
        _patch_platform("linux"),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS, bluez={"adapter": ADAPTER})


# ---------------------------------------------------------------------------
# Bleak 3.x on non-Linux — adapter is silently dropped
# ---------------------------------------------------------------------------


def test_bleak3_macos_ignores_adapter() -> None:
    """Bleak >= 3 on macOS drops the adapter (BlueZ-only concept)."""
    with (
        _patch_version("3.0.0"),
        _patch_platform("darwin"),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS)


def test_bleak3_windows_ignores_adapter() -> None:
    """Bleak >= 3 on Windows drops the adapter."""
    with (
        _patch_version("3.0.0"),
        _patch_platform("win32"),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS)


# ---------------------------------------------------------------------------
# Bleak 2.x — use legacy adapter= kwarg
# ---------------------------------------------------------------------------


def test_bleak2_uses_adapter_kwarg() -> None:
    """Bleak < 3 must use the legacy adapter= keyword."""
    with (
        _patch_version("0.22.3"),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS, adapter=ADAPTER)


def test_bleak2_9x_uses_adapter_kwarg() -> None:
    """Bleak 2.x regardless of minor/patch uses adapter=."""
    with (
        _patch_version("2.9.1"),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS, adapter=ADAPTER)


# ---------------------------------------------------------------------------
# PackageNotFoundError fallback — probe BleakClient signature
# ---------------------------------------------------------------------------


def test_package_not_found_falls_back_to_signature_probe_bluez() -> None:
    """When metadata is unavailable, detect Bleak 3 via signature inspection."""
    mock_sig = MagicMock()
    mock_sig.parameters = {"self": None, "address": None, "bluez": None}

    with (
        patch(
            "alpha_hwr.client._pkg_version",
            side_effect=PackageNotFoundError("bleak"),
        ),
        _patch_platform("linux"),
        patch("alpha_hwr.client.inspect.signature", return_value=mock_sig),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS, bluez={"adapter": ADAPTER})


def test_package_not_found_falls_back_to_signature_probe_adapter() -> None:
    """When metadata unavailable and no bluez param, fall back to adapter=."""
    mock_sig = MagicMock()
    mock_sig.parameters = {"self": None, "address": None, "adapter": None}

    with (
        patch(
            "alpha_hwr.client._pkg_version",
            side_effect=PackageNotFoundError("bleak"),
        ),
        patch("alpha_hwr.client.inspect.signature", return_value=mock_sig),
        patch("alpha_hwr.client.BleakClient") as mock_bleak,
    ):
        _make_bleak_client(ADDRESS, ADAPTER)

    mock_bleak.assert_called_once_with(ADDRESS, adapter=ADAPTER)
