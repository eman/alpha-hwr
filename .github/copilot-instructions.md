# GitHub Copilot Instructions for alpha-hwr

## Project Overview

**alpha-hwr** is a modern Python library and CLI for controlling Grundfos ALPHA HWR pumps via Bluetooth Low Energy (BLE). The library provides a clean, async-first API for pump telemetry, control modes, scheduling, and configuration management.

### Technology Stack
- **Language**: Python 3.13+ (uses modern type hints and async/await)
- **BLE Communication**: `bleak` library
- **Data Validation**: `pydantic` v2 with strict validation
- **CLI Framework**: `typer` with `rich` for beautiful terminal output
- **Build System**: `setuptools` with `pyproject.toml`
- **Documentation**: MkDocs with Material theme
- **Type Checking**: MyPy and BasedPyright (strict mode)
- **Linting/Formatting**: Ruff (replaces Black, isort, flake8)
- **Testing**: pytest with async support and MockPump for hardware emulation

## Architecture Guidelines

**CRITICAL**: Adhere strictly to the layered `Core -> Protocol -> Services -> Client` architecture.

### Layer Structure
1. **Core** (`src/alpha_hwr/core/`): 
   - BLE connection management
   - Session handling
   - Authentication
   - Low-level transport
   
2. **Protocol** (`src/alpha_hwr/protocol/`):
   - Frame building and parsing
   - Binary codec (Class 10 DataObjects, Class 3 fallback)
   - Raw packet structure
   - NO business logic here
   
3. **Services** (`src/alpha_hwr/services/`):
   - `TelemetryService`: Read and stream telemetry data
   - `ControlService`: Pump control modes and operations
   - `ScheduleService`: Time-based operation scheduling
   - `DeviceInfoService`: Device metadata
   - `ConfigurationService`: Backup/restore configurations
   
4. **Client** (`src/alpha_hwr/client.py`):
   - Thin facade exposing all services
   - Unified entry point for users
   - Manages service lifecycle

### Dependency Rules
- Core depends on: nothing (only stdlib and bleak)
- Protocol depends on: Core only
- Services depend on: Core and Protocol only
- Client depends on: All layers

**Never violate these dependencies**. Services should NOT depend on other services.

## Code Style and Standards

### General Conventions
- **Line Length**: 80 characters (strictly enforced by ruff)
- **Docstrings**: Google-style format for all public APIs
- **Type Hints**: Required for all function signatures, use `| None` not `Optional`
- **Async/Await**: All I/O operations must be async
- **Immutability**: Prefer frozen Pydantic models where appropriate
- **No Emoji**: Do not use emoji in code, comments, or documentation
- **Naming**:
  - Classes: `PascalCase`
  - Functions/variables: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
  - Private members: `_leading_underscore`

### Python-Specific Rules
- Use `from __future__ import annotations` for forward references
- Prefer dataclasses or Pydantic models over dictionaries
- Use context managers (`async with`) for resource management
- Import order: stdlib, third-party, local (enforced by ruff)
- Use explicit None checks: `if x is not None:` not `if x:`

### Example Code Style
```python
"""Module docstring explaining purpose."""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, Field


class TelemetryData(BaseModel):
    """Telemetry data from pump.
    
    Attributes:
        flow_m3h: Flow rate in cubic meters per hour.
        head_m: Head pressure in meters.
        power_w: Power consumption in watts.
    """
    
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    
    flow_m3h: float | None = Field(
        default=None, 
        description="Flow rate in m³/h"
    )
    head_m: float | None = Field(
        default=None, 
        description="Head pressure in meters"
    )
```

## Testing Requirements

### Test Organization
- **Unit Tests** (`tests/unit/`): Protocol logic, frame parsing, validators
- **Integration Tests** (`tests/integration/`): End-to-end workflows with MockPump
- **Reference Tests** (`tests/reference/`): Known byte-level protocol vectors
- **Benchmarks** (`tests/benchmarks/`): Performance validation

### Testing Rules
1. **MockPump**: Use `tests/mocks/mock_pump.py` for hardware emulation
2. **Async Tests**: Mark with `@pytest.mark.asyncio`
3. **Coverage**: Maintain >90% coverage for new code
4. **Fixtures**: Use pytest fixtures in `conftest.py`
5. **Isolation**: Tests must not depend on external hardware or network

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=alpha_hwr --cov-report=term

# Run specific test file
pytest tests/test_telemetry_service.py -v

# Run all checks (format, lint, type, test)
tox
```

## Build and Lint Commands

### Essential Commands
```bash
# Format code (auto-fix)
tox -e format -- --fix

# Check formatting (CI mode)
tox -e format

# Lint (show issues)
tox -e lint

# Lint with auto-fix
ruff check --fix .

# Type check
tox -e type && tox -e basedpyright

# Build package
python -m build

# Build documentation
mkdocs build

# Serve docs locally
mkdocs serve
```

### Pre-commit Requirements
Before committing, ALWAYS run:
```bash
tox
```
This runs: ruff format check → ruff lint → mypy → basedpyright → pytest

## Documentation Requirements

**CRITICAL**: All changes MUST update relevant documentation.

### Source Code Documentation
- Add/update docstrings (Google-style format)
- Include parameter types, return types, examples
- Document exceptions that can be raised
- Do not use emoji in docstrings or comments

### User-Facing Documentation
When modifying features, update:
- `README.md`: Examples and CLI usage
- `CHANGELOG.md`: Add entry under "Unreleased" section
- `docs/api/*.md`: API reference
- `docs/getting_started/quick_start.md`: Tutorials
- `docs/guides/*.md`: User guides
- `docs/protocol/*.md`: Protocol documentation
- `docs/reference/*.md`: Reference material

### What to Document
- New API methods or parameters
- New control modes or capabilities
- Protocol changes or discoveries
- CLI command additions or changes
- Breaking changes (mark clearly in CHANGELOG)

## Security and Quality

### Security Rules
1. **Never commit secrets**: Use environment variables or `.env` files
2. **Validate all inputs**: Use Pydantic models for validation
3. **Sanitize BLE data**: Always validate binary protocol data
4. **No arbitrary code execution**: No `eval()` or `exec()`
5. **Dependencies**: Only use well-maintained, audited packages

### Quality Checklist
- [ ] Code passes `ruff format --check`
- [ ] Code passes `ruff check`
- [ ] Code passes `mypy` and `basedpyright`
- [ ] All tests pass (`pytest`)
- [ ] Test coverage maintained/improved
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if user-facing change)
- [ ] No warnings in CI pipeline

## Common Pitfalls to Avoid

### Architecture Violations
**DON'T**: Import services in protocol layer
**DON'T**: Put business logic in protocol layer
**DON'T**: Have services depend on other services
**DO**: Keep layers independent and focused

### Async/Await Issues
**DON'T**: Mix sync and async code without proper handling
**DON'T**: Forget `await` on async calls
**DON'T**: Use blocking I/O in async functions
**DO**: Use `asyncio.to_thread()` for blocking operations
**DO**: Always use `async with` for BLE client

### Type Checking
**DON'T**: Use `Any` type without justification
**DON'T**: Ignore type errors with `# type: ignore` without comment
**DON'T**: Use bare `except:` clauses
**DO**: Provide explicit types for all parameters
**DO**: Use union types (`str | None`) over `Optional`

### Testing
**DON'T**: Test against real hardware in CI
**DON'T**: Write tests that depend on timing
**DON'T**: Commit commented-out test code
**DO**: Use MockPump for all integration tests
**DO**: Test edge cases and error conditions
**DO**: Keep tests fast (<1s per test)

## File Organization

### Important Files
- `src/alpha_hwr/`: Source code (layered architecture)
- `tests/`: Test suite (unit, integration, reference, mocks)
- `docs/`: MkDocs documentation
- `scripts/check.sh`: Local CI checks
- `pyproject.toml`: Build and tool configuration
- `Makefile`: Common development tasks
- `CONTRIBUTING.md`: Detailed contribution guidelines

### Configuration Files
- `pyproject.toml`: Package metadata, dependencies, tool configs
- `tox.ini`: Test automation
- `.bumpversion.cfg`: Version management
- `mkdocs.yml`: Documentation structure
- `.gitignore`: Excluded files (build artifacts, caches, etc.)

## Project Status and Goals

### Current Status
- **Refactor**: Monolithic client split into modular services (Complete)
- **Protocol**: Fully implemented (Class 10 DataObjects, Class 3 fallback)
- **Documentation**: Comprehensive user guides and protocol specs
- **Testing**: High coverage with MockPump integration
- **PyPI**: Published and actively maintained

### Goals
1. **Maintenance**: Fix bugs, improve stability
2. **Features**: Add missing advanced capabilities
3. **Optimization**: Profile and optimize protocol throughput
4. **Portability**: Keep design portable to other languages

## Getting Help

- See `CONTRIBUTING.md` for detailed contribution guidelines
- Check `docs/` for comprehensive documentation
- Review `tests/` for usage examples
- Use MockPump (`tests/mocks/`) for testing without hardware

## Quick Reference

### Development Workflow
1. Create feature branch
2. Make minimal, focused changes
3. Run `./scripts/check.sh` frequently
4. Update tests and documentation
5. Verify all checks pass
6. Submit pull request

### Testing Workflow
```bash
# Quick test iteration
tox -e py313 -- tests/test_mymodule.py -v

# Full check before commit
tox

# Coverage check
tox -e py313 -- --cov=alpha_hwr --cov-report=html
open htmlcov/index.html
```