---
description: Testing guidelines for alpha-hwr
applies_to:
  - "tests/**/*.py"
---

# Testing Guidelines

## Test Organization

### Directory Structure
- `tests/unit/`: Protocol logic, frame parsing, validators (no I/O)
- `tests/integration/`: End-to-end workflows using MockPump
- `tests/reference/`: Known byte-level protocol vectors
- `tests/benchmarks/`: Performance validation
- `tests/mocks/`: Test utilities (MockPump, fixtures)

### File Naming
- Test files: `test_*.py`
- Test functions: `test_<feature>_<scenario>()`
- Test classes: `class Test<Feature>:`

## MockPump Usage

### When to Use MockPump
- **ALWAYS** for integration tests
- **ALWAYS** when testing service layer
- **NEVER** test against real hardware in CI

### Example
```python
from tests.mocks.mock_pump import MockPump
from alpha_hwr import AlphaHWRClient


@pytest.mark.asyncio
async def test_telemetry_reading():
    """Test reading telemetry from pump."""
    async with MockPump() as mock_pump:
        # MockPump automatically handles BLE protocol
        async with AlphaHWRClient(mock_pump.address) as client:
            # Test your code
            data = await client.telemetry.read_once()
            assert data.flow_m3h >= 0
```

### MockPump Features
- Simulates BLE connection and authentication
- Responds to protocol requests automatically
- Can be configured with specific test data
- Tracks all requests for verification

## Test Patterns

### Async Test Template
```python
import pytest
from alpha_hwr import AlphaHWRClient
from tests.mocks.mock_pump import MockPump


@pytest.mark.asyncio
async def test_feature_name():
    """Test specific feature behavior.

    This test verifies that [describe what you're testing].
    """
    # Arrange
    async with MockPump() as mock_pump:
        async with AlphaHWRClient(mock_pump.address) as client:
            # Act
            result = await client.some_operation()

            # Assert
            assert result.expected_property == expected_value
```

### Protocol Test Template
```python
from alpha_hwr.protocol.frame import Frame


def test_frame_parsing():
    """Test frame parsing logic."""
    # Arrange
    raw_bytes = bytes([0x01, 0x02, 0x03])

    # Act
    frame = Frame.parse(raw_bytes)

    # Assert
    assert frame.command == 0x01
    assert frame.data == bytes([0x02, 0x03])
```

### Parametrized Tests
```python
import pytest


@pytest.mark.parametrize(
    "pressure,expected_rpm",
    [
        (1.0, 2000),
        (2.0, 2800),
        (3.0, 3400),
    ],
)
@pytest.mark.asyncio
async def test_pressure_to_rpm(pressure, expected_rpm):
    """Test pressure to RPM conversion."""
    async with MockPump() as mock_pump:
        async with AlphaHWRClient(mock_pump.address) as client:
            await client.control.set_constant_pressure(pressure)
            status = await client.control.get_status()
            assert abs(status.rpm - expected_rpm) < 100
```

## Test Fixtures

### Using Pytest Fixtures
Fixtures are defined in `conftest.py`:

```python
import pytest
from tests.mocks.mock_pump import MockPump
from alpha_hwr import AlphaHWRClient


@pytest.fixture
async def mock_pump():
    """Provide a MockPump instance."""
    async with MockPump() as pump:
        yield pump


@pytest.fixture
async def client(mock_pump):
    """Provide an authenticated client."""
    async with AlphaHWRClient(mock_pump.address) as client:
        yield client


# Use in tests:
@pytest.mark.asyncio
async def test_with_client(client):
    """Test using the client fixture."""
    data = await client.telemetry.read_once()
    assert data is not None
```

## Testing Best Practices

### Coverage Goals
- **Protocol layer**: 100% coverage (critical code)
- **Services layer**: >95% coverage
- **Client layer**: >90% coverage
- **Overall**: >90% coverage

### Test Independence
- Each test must be completely independent
- No shared state between tests
- Use fixtures for setup/teardown
- Clean up resources in finally blocks or async context managers

### Test Naming
```python
# GOOD: Good test names (descriptive, specific)
def test_telemetry_parses_valid_frame():
    """Test parsing of valid telemetry frame."""


def test_control_rejects_negative_pressure():
    """Test that negative pressure values are rejected."""


def test_schedule_entry_validates_time_range():
    """Test time range validation in schedule entries."""


# BAD: Bad test names (vague, generic)
def test_telemetry():
    """Test telemetry."""


def test_control():
    """Test control."""
```

### Assertions
```python
# GOOD: Specific assertions with messages
assert result.flow_m3h > 0, "Flow rate should be positive"
assert result.head_m <= 6.0, "Head should not exceed maximum"

# GOOD: Use pytest helpers for complex checks
pytest.approx(result.temperature_c, 25.0, abs=0.5)

# BAD: Generic assertions without context
assert result
assert result.value
```

### Error Testing
```python
import pytest
from alpha_hwr.exceptions import ValidationError


@pytest.mark.asyncio
async def test_invalid_pressure_raises_error():
    """Test that invalid pressure raises ValidationError."""
    async with MockPump() as mock_pump:
        async with AlphaHWRClient(mock_pump.address) as client:
            # Expect specific exception
            with pytest.raises(ValidationError, match="pressure.*range"):
                await client.control.set_constant_pressure(-1.0)
```

## Running Tests

### Full Test Suite
```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=alpha_hwr --cov-report=term --cov-report=html

# Run in parallel (faster)
pytest tests/ -n auto
```

### Specific Tests
```bash
# Run specific test file
pytest tests/test_telemetry_service.py -v

# Run specific test function
pytest tests/test_telemetry_service.py::test_read_telemetry -v

# Run specific test class
pytest tests/test_telemetry_service.py::TestTelemetryService -v

# Run tests matching pattern
pytest tests/ -k "telemetry" -v
```

### Test Markers
```bash
# Run only async tests
pytest tests/ -m asyncio

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v
```

## Performance Testing

### Benchmark Tests
Located in `tests/benchmarks/`:

```python
import pytest


def test_frame_parsing_performance(benchmark):
    """Benchmark frame parsing speed."""
    raw_frame = bytes([0x01] * 100)

    def parse():
        return Frame.parse(raw_frame)

    result = benchmark(parse)
    assert result is not None
```

### Performance Guidelines
- Frame parsing: <1ms per frame
- Telemetry reading: <100ms end-to-end
- Control command: <200ms end-to-end
- MockPump overhead: Minimal (<10ms)

## Common Testing Mistakes

### BAD - Don't Do This
```python
# Testing against real hardware
async def test_with_real_pump():
    client = AlphaHWRClient("AA:BB:CC:DD:EE:FF")  # WRONG!


# Tests that depend on timing
async def test_telemetry():
    await asyncio.sleep(5)  # WRONG! Brittle test


# Tests with side effects
def test_modify_global():
    global_state["key"] = "value"  # WRONG!


# Commented-out test code
# def test_old_feature():  # WRONG! Delete or fix
#     pass
```

### GOOD - Do This Instead
```python
# Always use MockPump
async def test_with_mock():
    async with MockPump() as mock_pump:
        async with AlphaHWRClient(mock_pump.address) as client:
            # Test code

# Use fixtures for setup/teardown
@pytest.fixture
async def prepared_client():
    async with MockPump() as mock_pump:
        async with AlphaHWRClient(mock_pump.address) as client:
            await client.control.start()
            yield client

# Clean test code (no commented code, no print statements)
async def test_clean():
    """Test with clean, maintainable code."""
    result = await client.operation()
    assert result.is_valid()
```

## Test Documentation

### Docstrings in Tests
All test functions should have clear docstrings:

```python
@pytest.mark.asyncio
async def test_telemetry_stream_stops_on_error():
    """Test that telemetry stream stops gracefully on BLE error.
    
    This test verifies that when a BLE connection error occurs during
    telemetry streaming, the stream stops cleanly without leaving
    dangling resources or pending tasks.
    
    Regression test for issue #123.
    """
```

### Test Comments
Use comments to explain non-obvious test logic:

```python
@pytest.mark.asyncio
async def test_schedule_conflict_resolution():
    """Test schedule entry conflict resolution."""
    # Create overlapping entries to trigger conflict resolution
    entry1 = ScheduleEntry(day="Monday", begin_hour=8, end_hour=10)
    entry2 = ScheduleEntry(day="Monday", begin_hour=9, end_hour=11)
    
    # The service should merge or reject conflicting entries
    result = await client.schedule.write_entries([entry1, entry2])
    assert len(result.conflicts) > 0
```
