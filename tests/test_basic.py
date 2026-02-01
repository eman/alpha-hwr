from alpha_hwr import AlphaHWRClient, TelemetryData


def test_import():
    """Test that main classes can be imported."""
    assert AlphaHWRClient is not None
    assert TelemetryData is not None


def test_telemetry_model():
    """Test TelemetryData model defaults."""
    t = TelemetryData()
    assert t.flow_m3h is None
    assert t.power_w is None
    assert t.timestamp is not None
