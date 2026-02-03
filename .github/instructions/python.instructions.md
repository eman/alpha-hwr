---
description: Python-specific coding instructions for alpha-hwr
applies_to:
  - "**/*.py"
---

# Python Code Instructions

## Code Style

### General Rules
- **No Emoji**: Do not use emoji in code, comments, or docstrings
- **Line Length**: 80 characters maximum

### Type Hints
- **REQUIRED**: All function signatures must have complete type hints
- Use modern syntax: `str | None` instead of `Optional[str]`
- Use `from __future__ import annotations` for forward references
- Return types are mandatory (use `-> None` for void functions)

### Pydantic Models
- Use `pydantic` v2 for all data models
- Prefer `frozen=True` for immutable data
- Use `Field()` with clear descriptions
- Define `model_config` using `ClassVar[ConfigDict]`

Example:
```python
from typing import ClassVar
from pydantic import BaseModel, ConfigDict, Field

class TelemetryData(BaseModel):
    """Telemetry data from pump."""
    
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    
    flow_m3h: float | None = Field(
        default=None,
        description="Flow rate in m³/h"
    )
```

### Async/Await
- All I/O operations MUST be async
- Always use `async with` for context managers
- Never use blocking calls in async functions
- Use `asyncio.to_thread()` if you must call blocking code

### Import Order
1. Future imports (`from __future__ import annotations`)
2. Standard library
3. Third-party packages (sorted alphabetically)
4. Local imports (relative or absolute)

Enforced by ruff. Example:
```python
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import AsyncIterator

from bleak import BleakClient
from pydantic import BaseModel

from alpha_hwr.core.transport import Transport
from alpha_hwr.protocol.frame import Frame
```

### Docstrings
- **REQUIRED** for all public classes, functions, and methods
- Use Google-style format
- Include type information in docstring (in addition to type hints)
- Document exceptions that can be raised

Example:
```python
async def read_telemetry(self, timeout: float = 5.0) -> TelemetryData:
    """Read current telemetry data from the pump.
    
    Args:
        timeout: Maximum time to wait for response in seconds.
        
    Returns:
        TelemetryData object with current readings.
        
    Raises:
        TimeoutError: If pump does not respond within timeout.
        ConnectionError: If BLE connection is lost.
        
    Example:
        ```python
        data = await client.telemetry.read_telemetry(timeout=10.0)
        print(f"Flow: {data.flow_m3h} m³/h")
        ```
    """
```

## Testing

### Test Structure
- Test files must be named `test_*.py`
- Use descriptive test function names: `test_telemetry_parses_valid_frame()`
- Group related tests in classes: `class TestTelemetryService:`

### Async Tests
```python
import pytest

@pytest.mark.asyncio
async def test_read_telemetry():
    """Test reading telemetry data."""
    async with AlphaHWRClient(address) as client:
        data = await client.telemetry.read_once()
        assert data.flow_m3h is not None
```

### MockPump Usage
For integration tests, always use MockPump:
```python
from tests.mocks.mock_pump import MockPump

@pytest.mark.asyncio
async def test_control_flow():
    """Test pump control workflow."""
    async with MockPump() as pump:
        async with AlphaHWRClient(pump.address) as client:
            await client.control.set_constant_pressure(1.5)
            # Test assertions here
```

## Common Mistakes to Avoid

### ❌ Don't
```python
# Missing type hints
def process_data(data):
    return data * 2

# Using Optional instead of | None
from typing import Optional
def get_value() -> Optional[str]:
    pass

# Blocking I/O in async function
async def read_file():
    with open("file.txt") as f:  # WRONG!
        return f.read()

# Bare except
try:
    risky_operation()
except:  # WRONG!
    pass
```

### ✅ Do
```python
# Complete type hints
def process_data(data: float) -> float:
    return data * 2

# Modern union syntax
def get_value() -> str | None:
    pass

# Async file I/O
async def read_file() -> str:
    return await asyncio.to_thread(_read_sync_file)
    
def _read_sync_file() -> str:
    with open("file.txt") as f:
        return f.read()

# Specific exceptions
try:
    risky_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
```

## Architecture Compliance

### Layer Violations - NEVER DO THIS
```python
# ❌ Protocol importing from Services
from alpha_hwr.services.telemetry import TelemetryService  # WRONG!

# ❌ Services importing from other Services
from alpha_hwr.services.control import ControlService  # WRONG!
```

### Correct Dependencies
```python
# ✅ Services can import from Protocol and Core
from alpha_hwr.core.transport import Transport
from alpha_hwr.protocol.frame import Frame

# ✅ Client can import from Services
from alpha_hwr.services.telemetry import TelemetryService
```

## Performance

- Minimize BLE round trips (batch operations when possible)
- Use async generators for streaming data
- Cache device info and static data
- Don't poll unnecessarily - use notifications when available

## Security

- Validate all binary data from BLE before parsing
- Use Pydantic validators for input validation
- Never log sensitive data (authentication tokens, etc.)
- Use `defusedxml` for any XML parsing (not built-in xml module)
