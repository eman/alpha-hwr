# GEMINI Session: Polish & Maintenance

## Goal

Maintain and polish the `alpha-hwr` library in preparation for PyPI publishing. The focus is on code quality, test coverage, documentation accuracy, and stability.

## Key Instructions

1. **Architecture Compliance**: Adhere strictly to the `Core -> Protocol -> Services -> Client` architecture.
   - **Core**: Connection, authentication, transport (`src/alpha_hwr/core/`)
   - **Protocol**: Frame building, parsing, codec (`src/alpha_hwr/protocol/`)
   - **Services**: Business logic for Telemetry, Control, Schedule, etc. (`src/alpha_hwr/services/`)
   - **Client**: Unified facade API (`src/alpha_hwr/client.py`)

2. **Testing Standards**:
   - **Unit Tests**: Ensure all protocol logic is covered in `tests/unit/`.
   - **Integration Tests**: Verify end-to-end workflows using `MockPump` in `tests/integration/`.
   - **Reference Tests**: Validate against byte-level vectors in `tests/reference/`.
   - **Execution**: Run tests frequently (`pytest`) to ensure no regressions.

3. **Documentation**:
   - Keep `docs/` up-to-date with code changes.
   - Ensure the `reimplementation/` guide matches the actual codebase ("Ground Truth").
   - Maintain accurate docstrings for all public APIs.

4. **Publishing Readiness**:
   - Verify `pyproject.toml` configuration.
   - Ensure clean package builds.
   - maintain semantic versioning practices.

## Key Files

* `src/alpha_hwr/`: Source code root.
* `tests/`: Test suite (Unit, Integration, Reference, Mocks).
* `docs/`: Documentation (MkDocs).
* `pyproject.toml`: Build configuration.

## Status

* **Refactor**: ✅ Complete. Monolithic client split into modular services.
* **Protocol**: ✅ Fully implemented (Class 10 DataObjects, Class 3 fallback).
* **Documentation**: ✅ Comprehensive (User guides, Protocol specs, Reimplementation guide).
* **Testing**: ✅ High coverage with MockPump integration.

## Next Steps

1. **Feature Additions**: Implement any missing advanced features (e.g., advanced logging, specific pump variants).
2. **Optimization**: Profile and optimize protocol throughput (packet splitting, timings).
3. **Distribution**: Prepare for PyPI release.

## Developer Notes

* **Running Tests**: Use `.venv/bin/pytest` or `python -m pytest`.
* **Building Docs**: Use `mkdocs serve` to preview.
* **MockPump**: The `MockPump` class in `tests/mocks/` is the primary tool for integration testing without hardware. Keep it updated with any new protocol findings.