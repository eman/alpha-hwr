from typing import Optional
import platform
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALPHA_HWR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    device_address: Optional[str] = Field(
        None,
        description="BLE Device UUID (macOS) or MAC Address (Linux/Windows)",
    )
    device_address_macos: Optional[str] = Field(
        None, description="BLE Device UUID for macOS"
    )
    mac_address: Optional[str] = Field(
        None, description="BLE MAC Address for Linux/Windows"
    )
    adapter: Optional[str] = Field(
        None, description="BLE Adapter (Linux hci0, etc.)"
    )
    connection_timeout: float = Field(
        5.0, description="Connection timeout in seconds"
    )
    command_retries: int = Field(
        3, description="Number of retries for commands"
    )
    log_level: str = Field("INFO", description="Logging level")

    @model_validator(mode="after")
    def select_platform_address(self):
        """Select the appropriate device address based on platform."""
        # If device_address is explicitly set, use it
        if self.device_address:
            return self

        # Detect platform and choose appropriate address
        system = platform.system()
        if system == "Darwin" and self.device_address_macos:
            self.device_address = self.device_address_macos
        elif system in ("Linux", "Windows") and self.mac_address:
            self.device_address = self.mac_address

        return self


# Global settings instance (can be overridden)
_settings: Optional["Settings"] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        try:
            _settings = Settings()  # type: ignore
        except Exception as e:
            # If env vars are missing, we might fail.
            # We should probably raise or return a default
            # For now, let's raise to satisfy mypy and safety.
            raise RuntimeError(f"Failed to load settings: {e}")

    return _settings


def load_settings(device_address: Optional[str] = None, **kwargs) -> Settings:
    """Load settings with overrides."""
    # Create a temporary dict for overrides
    overrides = {k: v for k, v in kwargs.items() if v is not None}
    if device_address:
        overrides["device_address"] = device_address

    global _settings
    _settings = Settings(**overrides)  # type: ignore
    return _settings
