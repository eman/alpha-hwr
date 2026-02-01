# Contributing to alpha-hwr

Thank you for your interest in contributing to alpha-hwr!

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/alpha-hwr.git
   cd alpha-hwr
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev,docs]"
   ```

## Running Tests Locally

We provide a convenient script to run all checks that will be executed in CI:

```bash
./scripts/check.sh
```

This will run:
- Ruff format check
- Ruff lint
- MyPy type checking
- BasedPyright type checking
- Pytest with coverage

### Running Individual Checks

```bash
# Format code
ruff format .

# Check formatting
ruff format --check .

# Lint
ruff check .

# Type check with MyPy
mypy src/alpha_hwr

# Type check with BasedPyright
basedpyright

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=alpha_hwr --cov-report=term

# Run all checks with tox
tox
```

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
4. Run `./scripts/check.sh` to ensure all checks pass
5. Update relevant documentation
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to your fork (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Release Process

Releases are managed by maintainers:

1. Update CHANGELOG.md
2. Run `bump2version [major|minor|patch]` to create version tag
3. Push tags: `git push --tags`
4. Create a GitHub Release - this triggers PyPI publishing automatically

## Questions?

Open an issue for questions, bug reports, or feature requests.
