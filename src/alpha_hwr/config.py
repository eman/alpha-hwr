from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from .utils import resolve_platform_address


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALPHA_HWR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    device_address: Optional[str] = Field(
        None,
        description="BLE Device Address (UUID on macOS, MAC on Linux/Windows). Supports comma-separated lists.",
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
    def resolve_address(self) -> "Settings":
        """Resolve device_address if it's a comma-separated list."""
        if self.device_address:
            self.device_address = resolve_platform_address(self.device_address)
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
