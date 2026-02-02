"""
Configuration manager for CLI settings.

Handles persistent storage of device addresses and profiles in XDG-compliant
config directory (~/.config/alpha-hwr/config.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TypedDict
from datetime import datetime

from rich.console import Console

console = Console()


class DeviceEntry(TypedDict):
    """TypedDict for device configuration entry."""

    address: str
    saved_at: str


class Config(TypedDict):
    """TypedDict for complete configuration structure."""

    default_device: Optional[str]
    devices: dict[str, DeviceEntry]
    last_used: Optional[str]
    last_used_at: Optional[str]
    version: str


class ConfigManager:
    """Manages CLI configuration including saved device profiles."""

    CONFIG_DIR: Path = Path.home() / ".config" / "alpha-hwr"
    CONFIG_FILE: Path = CONFIG_DIR / "config.json"

    DEFAULT_CONFIG: Config = {
        "default_device": None,
        "devices": {},
        "last_used": None,
        "last_used_at": None,
        "version": "1.0",
    }

    @classmethod
    def _ensure_config_dir(cls) -> None:
        """Create config directory if it doesn't exist."""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _load_config(cls) -> Config:
        """Load config from file, or return default if not present."""
        cls._ensure_config_dir()

        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE, "r") as f:
                    loaded: dict = json.load(f)
                # Ensure all required keys exist with correct types
                config: Config = {
                    "default_device": loaded.get("default_device"),
                    "devices": loaded.get("devices", {}),
                    "last_used": loaded.get("last_used"),
                    "last_used_at": loaded.get("last_used_at"),
                    "version": loaded.get("version", "1.0"),
                }
                return config
            except (json.JSONDecodeError, IOError) as e:
                console.print(
                    f"[yellow]Warning:[/yellow] Failed to load config: {e}"
                )
                return cls.DEFAULT_CONFIG.copy()
        return cls.DEFAULT_CONFIG.copy()

    @classmethod
    def _save_config(cls, config: Config) -> None:
        """Save config to file."""
        cls._ensure_config_dir()
        try:
            with open(cls.CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except IOError as e:
            console.print(
                f"[yellow]Warning:[/yellow] Failed to save config: {e}"
            )

    @classmethod
    def get_default_device(cls) -> Optional[str]:
        """Get the default device address."""
        config = cls._load_config()
        return config.get("default_device")

    @classmethod
    def set_default_device(cls, address: str) -> None:
        """Set the default device address."""
        config = cls._load_config()
        config["default_device"] = address
        config["last_used"] = address
        config["last_used_at"] = datetime.now().isoformat()
        cls._save_config(config)

    @classmethod
    def save_device(
        cls, address: str, name: Optional[str] = None, set_default: bool = False
    ) -> None:
        """
        Save a device to the configuration.

        Args:
            address: MAC address of the device
            name: Optional friendly name for the device
            set_default: Whether to set this as the default device
        """
        config = cls._load_config()
        device_name = name or address
        device_entry: DeviceEntry = {
            "address": address,
            "saved_at": datetime.now().isoformat(),
        }
        config["devices"][device_name] = device_entry

        if set_default:
            config["default_device"] = address

        config["last_used"] = address
        config["last_used_at"] = datetime.now().isoformat()
        cls._save_config(config)

    @classmethod
    def get_device(cls, name_or_address: str) -> Optional[str]:
        """
        Get device address by name or return if it matches an address.

        Args:
            name_or_address: Device name or MAC address

        Returns:
            MAC address if found, None otherwise
        """
        config = cls._load_config()

        # Direct lookup by name
        devices = config["devices"]
        if name_or_address in devices:
            return devices[name_or_address]["address"]

        # Check if it's already a MAC address
        if _is_valid_mac(name_or_address):
            return name_or_address

        return None

    @classmethod
    def list_devices(cls) -> list[dict]:
        """
        List all saved devices.

        Returns:
            List of device dicts with name, address, and saved_at
        """
        config = cls._load_config()
        devices_list = []
        devices = config["devices"]
        for name, info in devices.items():
            devices_list.append(
                {
                    "name": name,
                    "address": info["address"],
                    "saved_at": info["saved_at"],
                    "is_default": info["address"]
                    == config.get("default_device"),
                }
            )
        return devices_list

    @classmethod
    def delete_device(cls, name: str) -> bool:
        """
        Delete a device from the configuration.

        Args:
            name: Device name to delete

        Returns:
            True if deleted, False if not found
        """
        config = cls._load_config()
        devices = config["devices"]
        if name in devices:
            device_entry = devices[name]
            del devices[name]
            # If this was the default, clear it
            if config.get("default_device") == device_entry.get("address"):
                config["default_device"] = None
            cls._save_config(config)
            return True
        return False

    @classmethod
    def get_last_used(cls) -> Optional[str]:
        """Get the last used device address."""
        config = cls._load_config()
        return config.get("last_used")


def _is_valid_mac(address: str) -> bool:
    """Check if string looks like a MAC address."""
    parts = address.split(":")
    return (
        len(parts) == 6
        and all(len(part) == 2 for part in parts)
        and all(
            all(c in "0123456789ABCDEFabcdef" for c in part) for part in parts
        )
    )
