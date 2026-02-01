
import os
from unittest.mock import patch
from alpha_hwr.config import get_settings

class TestConfig:
    @patch.dict(os.environ, {"ALPHA_HWR_DEVICE_ADDRESS": "AA:BB:CC:DD:EE:FF", "ALPHA_HWR_ADAPTER": "hci0"})
    def test_settings_load_from_env(self):
        """Test loading settings from environment variables."""
        # Reset global settings
        import alpha_hwr.config
        alpha_hwr.config._settings = None
        
        settings = get_settings()
        assert settings.device_address == "AA:BB:CC:DD:EE:FF"
        assert settings.adapter == "hci0"
        assert settings.connection_timeout == 5.0 # Default

    def test_settings_defaults(self):
        """Test default values."""
        # We need to simulate missing env var for address if it's required
        # But if it's required, pydantic will raise error.
        # Let's mock a minimal env
        with patch.dict(os.environ, {"ALPHA_HWR_DEVICE_ADDRESS": "00:00:00:00:00:00"}):
             import alpha_hwr.config
             alpha_hwr.config._settings = None
             settings = get_settings()
             assert settings.command_retries == 3
