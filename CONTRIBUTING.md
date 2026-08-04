# Contributing to alpha-hwr

Thank you for your interest in contributing to alpha-hwr!

## Development Setup

### Quick Setup (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/eman/alpha-hwr.git
   cd alpha-hwr
   ```

2. **Install uv (if not already installed):**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Install dependencies:**
   ```bash
   uv sync --all-extras
   ```

   This creates a `.venv` virtual environment and installs all dependencies including dev tools.

### Alternative: Without uv

If you prefer not to use `uv`, use traditional pip:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev,docs]"
```

**Note:** We recommend `uv` for faster, more reliable dependency management and deterministic builds.

## Running Tests and Checks

We use **tox** for all testing and validation. Tox automatically creates isolated environments and runs all checks consistently.

### Run All Checks

```bash
tox
```

This runs all environments:
- `py313` - Tests with pytest (parallel via pytest-xdist)
- `format` - Code formatting check with ruff
- `lint` - Linting with ruff
- `type` - Type checking with mypy
- `basedpyright` - Type checking with basedpyright
- `security` - Security checks with bandit and safety

### Run Specific Checks

```bash
# Run tests only (parallel execution with pytest-xdist)
# Replace py313 with py311 or py312 if using a different Python version
tox -e py313

# Run tests sequentially
tox -e py313 -- -n 0

# Run specific test file
tox -e py313 -- tests/unit/protocol/test_frame_parser.py

# Run tests with coverage
tox -e py313 -- --cov=alpha_hwr --cov-report=term

# Format code (auto-fix)
tox -e format -- --fix

# Check formatting (no auto-fix)
tox -e format

# Lint code
tox -e lint

# Type check with MyPy
tox -e type

# Type check with BasedPyright
tox -e basedpyright

# Security checks
tox -e security
```

## Testing

### Test Organization
- **Unit Tests** (`tests/unit/`): Protocol logic, frame parsing, validators
- **Integration Tests** (`tests/integration/`): End-to-end workflows with MockPump
- **Property-Based Tests**: Using Hypothesis for edge case discovery

### Parallel Test Execution
Tests run in parallel by default using `pytest-xdist` (`-n auto`). This significantly speeds up CI. To run sequentially:

```bash
# Replace py313 with your Python version (py311, py312, etc.)
tox -e py313 -- -n 0
```

### Property-Based Testing with Hypothesis
We use Hypothesis to generate random test cases and find edge cases:

```python
from hypothesis import given
from tests.conftest import valid_frame_bytes


@given(valid_frame_bytes())
def test_frame_parsing_handles_all_valid_frames(frame_bytes):
    """Hypothesis generates 100+ variations of valid frames."""
    frame = Frame.parse(frame_bytes)
    assert frame is not None
```

Available Hypothesis strategies in `conftest.py`:
- `valid_frame_bytes()` - Random but valid GENI protocol frames
- `valid_telemetry_values()` - Realistic telemetry readings
- `valid_pressure_values()` - Valid pump pressure setpoints

## Code Quality

- **Linting**: Code must pass `ruff check`
- **Type Checking**: Code must pass `mypy` and `basedpyright`
- **Testing**: All tests must pass (`pytest`)
- **Coverage**: Maintain or improve test coverage

## Code Style

- We use **Ruff** for formatting and linting
- Line length: 80 characters
- Follow PEP 8 conventions
- Use type hints for all functions
- Write docstrings for public APIs (Google-style format)

## Architecture

Please read `copilot-instructions.md` for architecture guidelines. The project follows a strict layered architecture:

- **Core**: Connection, authentication, transport (`src/alpha_hwr/core/`)
- **Protocol**: Frame building, parsing, codec (`src/alpha_hwr/protocol/`)
- **Services**: Business logic for Telemetry, Control, Schedule, etc. (`src/alpha_hwr/services/`)
- **Client**: Unified facade API (`src/alpha_hwr/client.py`)

## Documentation Requirements

**IMPORTANT**: When adding or modifying features, you MUST update the corresponding documentation files:

1. **Source Code Documentation**:
   - Add/update docstrings in the source code
   - Follow Google-style docstring format
   - Include parameter types, return types, and examples

2. **User-Facing Documentation** (update ALL applicable files):
   - `README.md` - User-facing examples and CLI usage
   - `CHANGELOG.md` - Add entry under "Unreleased" section
   - `docs/api/client.md` - API method documentation
   - `docs/api/models.md` - Data model documentation
   - `docs/api/constants.md` - Constants and enums
   - `docs/getting_started/quick_start.md` - Usage examples
   - `docs/index.md` - Feature list and overview
   - `docs/protocol/control.md` - Protocol details
   - `docs/reference/data_models.md` - Reference material

3. **What to Document**:
   - New API methods or parameters
   - New control modes or capabilities
   - Protocol changes or discoveries
   - CLI command additions or changes

## Testing

- **Unit Tests**: Test protocol logic in isolation (`tests/unit/`)
- **Integration Tests**: Test end-to-end workflows using MockPump (`tests/integration/`)
- **Reference Tests**: Validate against known byte-level vectors (`tests/reference/`)

All new features should include appropriate tests.

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run `tox` to ensure all checks pass
5. Update relevant documentation
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to your fork (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Release Process

Releases are managed by maintainers:

1. Update CHANGELOG.md
2. Push a version tag: `git tag v<version> && git push --tags`
3. Create a GitHub Release from that tag - this triggers PyPI publishing automatically

## Questions?

Open an issue for questions, bug reports, or feature requests.
