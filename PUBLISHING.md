# Publishing Setup Guide

This guide covers the complete setup needed to publish alpha-hwr to PyPI and maintain it.

## Initial Setup (One-Time)

### 1. GitHub Repository Setup

#### Enable GitHub Pages for Documentation
1. Go to repository Settings → Pages
2. Source: Deploy from a branch
3. Branch: `gh-pages` / `root`
4. Save

#### Set Up PyPI Trusted Publishing
1. Go to https://pypi.org/manage/account/publishing/
2. Add a new "pending publisher":
   - PyPI Project Name: `alpha-hwr`
   - Owner: your GitHub username/org
   - Repository name: `alpha-hwr`
   - Workflow name: `publish.yml`
   - Environment name: (leave blank)

#### Update Repository Settings
1. Go to repository Settings → General
2. Add description: "Modern Python library and CLI for Grundfos ALPHA HWR pumps via Bluetooth Low Energy"
3. Add topics: `grundfos`, `pump`, `ble`, `bluetooth`, `iot`, `hardware-control`, `home-automation`, `asyncio`
4. Update the GitHub URLs in `pyproject.toml` to match your actual repository

### 2. Update Repository URLs

Edit `pyproject.toml` and replace `yourusername` with your actual GitHub username:
```toml
[project.urls]
Homepage = "https://github.com/YOURUSERNAME/alpha-hwr"
Documentation = "https://YOURUSERNAME.github.io/alpha-hwr"
Repository = "https://github.com/YOURUSERNAME/alpha-hwr"
Issues = "https://github.com/YOURUSERNAME/alpha-hwr/issues"
```

### 3. Optional: Custom Domain for Docs

If you have a custom domain:
1. Add a `CNAME` file to your repository root with your domain
2. Update the `cname` field in `.github/workflows/docs.yml`
3. Configure DNS with a CNAME record pointing to `YOURUSERNAME.github.io`

## Development Workflow

### Local Testing

Before pushing any changes, run local checks:

```bash
# Quick check
./scripts/check.sh

# Or use make
make check

# Individual checks
make format-check
make lint
make typecheck
make test
```

### Making Changes

1. Create a feature branch:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Make your changes and test locally:
   ```bash
   ./scripts/check.sh
   ```

3. Commit and push:
   ```bash
   git add .
   git commit -m "Add my feature"
   git push origin feature/my-feature
   ```

4. Open a Pull Request on GitHub
   - CI will automatically run tests
   - Docs will preview on merge to main

## Release Process

### 1. Prepare the Release

Update `CHANGELOG.md`:
```markdown
## [Unreleased]

## [0.2.0] - 2024-02-01

### Added
- New feature X
- Support for Y

### Fixed
- Bug in Z
```

### 2. Bump Version

Use bump2version to create a version tag:

```bash
# For bug fixes (0.1.0 → 0.1.1)
bump2version patch

# For new features (0.1.0 → 0.2.0)
bump2version minor

# For breaking changes (0.1.0 → 1.0.0)
bump2version major
```

Or use make:
```bash
make bump-patch
make bump-minor
make bump-major
```

This will:
- Update version in `pyproject.toml`, `__init__.py`, `CHANGELOG.md`, etc.
- Create a git commit
- Create a git tag (e.g., `v0.2.0`)

### 3. Push Tags

```bash
git push
git push --tags
```

### 4. Create GitHub Release

1. Go to GitHub repository → Releases → "Draft a new release"
2. Choose the tag you just pushed (e.g., `v0.2.0`)
3. Title: `Version 0.2.0`
4. Description: Copy from CHANGELOG.md
5. Click "Publish release"

**This automatically triggers:**
- PyPI publishing (via `.github/workflows/publish.yml`)
- Documentation update (via `.github/workflows/docs.yml`)

### 5. Verify Publication

- Check PyPI: https://pypi.org/project/alpha-hwr/
- Check Docs: https://YOURUSERNAME.github.io/alpha-hwr/
- Test installation: `pip install alpha-hwr==0.2.0`

## Maintenance

### Updating Dependencies

```bash
# Update dev dependencies
pip install --upgrade pip setuptools wheel
pip install --upgrade ruff mypy pytest basedpyright

# Update runtime dependencies (in pyproject.toml)
# Test thoroughly after updating bleak, pydantic, etc.
```

### Monitoring

- Watch GitHub Actions for CI failures
- Monitor PyPI download stats
- Review and respond to GitHub Issues

### Security

- Enable Dependabot in repository settings
- Review and merge Dependabot PRs regularly
- Run security scans: `pip-audit` (add to dev dependencies if desired)

## Troubleshooting

### PyPI Publishing Fails

1. Check trusted publishing setup on PyPI
2. Verify workflow permissions in `.github/workflows/publish.yml`
3. Ensure version in `pyproject.toml` matches git tag

### Documentation Not Updating

1. Check GitHub Pages is enabled
2. Verify `gh-pages` branch exists after first docs workflow run
3. Check workflow logs in Actions tab

### CI Tests Failing

1. Run `./scripts/check.sh` locally to reproduce
2. Check specific failed step in GitHub Actions logs
3. Ensure all dependencies are specified in `pyproject.toml`

## Best Practices

1. **Always test locally** before pushing
2. **Keep CHANGELOG.md updated** with each PR
3. **Version semantically**: Major.Minor.Patch
4. **Write release notes** when creating GitHub releases
5. **Monitor first 24h** after each release for issues
6. **Be responsive** to bug reports on new releases
7. **Pin major versions** of critical dependencies (bleak, pydantic)

## Tools Reference

- **bump2version**: Version management and tagging
- **ruff**: Fast Python linter and formatter
- **mypy**: Static type checker
- **basedpyright**: Advanced type checker
- **pytest**: Test framework
- **mkdocs**: Documentation generator
- **GitHub Actions**: CI/CD platform
- **PyPI**: Python Package Index
