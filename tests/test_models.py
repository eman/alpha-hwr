from alpha_hwr.models import TelemetryData


class TestModels:
    def test_telemetry_data_defaults(self):
        """Verify default values for TelemetryData."""
        data = TelemetryData()
        assert data.speed_rpm is None
        assert data.power_w is None
        assert data.flow_m3h is None

    def test_telemetry_data_update(self):
        """Verify model_copy update mechanism."""
        data = TelemetryData()
        updated = data.model_copy(update={"speed_rpm": 1500.0, "power_w": 45.0})

        assert updated.speed_rpm == 1500.0
        assert updated.power_w == 45.0
        assert updated.flow_m3h is None  # Should remain unchanged/None

        # Original should be untouched
        assert data.speed_rpm is None

    def test_unit_conversions(self):
        """Verify authoritative unit conversions."""
        from alpha_hwr.constants import (
            FACTOR_CELSIUS_TO_FAHRENHEIT,
            FACTOR_M3H_TO_GPM,
            FACTOR_M_TO_FT,
            FACTOR_M_TO_PSI,
        )

        data = TelemetryData(
            flow_m3h=1.0, head_m=10.0, media_temperature_c=100.0
        )

        # GPM: m3h / factor
        expected_gpm = 1.0 / FACTOR_M3H_TO_GPM
        assert data.flow_gpm is not None
        assert abs(data.flow_gpm - expected_gpm) < 0.00001

        # Ft: m / factor
        expected_ft = 10.0 / FACTOR_M_TO_FT
        assert data.head_ft is not None
        assert abs(data.head_ft - expected_ft) < 0.00001

        # PSI: m / factor
        expected_psi = 10.0 / FACTOR_M_TO_PSI
        assert data.head_psi is not None
        assert abs(data.head_psi - expected_psi) < 0.00001

        # Temp F: (C / factor) + 32
        expected_f = (100.0 / FACTOR_CELSIUS_TO_FAHRENHEIT) + 32.0
        assert data.media_temperature_f is not None
        assert abs(data.media_temperature_f - expected_f) < 0.00001
