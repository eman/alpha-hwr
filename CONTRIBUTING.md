# Contributing to alpha-hwr

## Development Guidelines

### Code Quality

- **Linting**: Code must pass `ruff check`
- **Type Checking**: Code must pass `mypy` and `basedpyright`
- **Testing**: All tests must pass (`pytest`)
- **Coverage**: Maintain or improve test coverage

Run all checks with:
```bash
tox
```

### Documentation Requirements

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
