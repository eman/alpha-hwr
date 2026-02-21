"""Test version configuration for the project."""

import re
from pathlib import Path


def test_version_consistency():
    """Test that pyproject.toml is correctly configured for setuptools_scm."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject_path.read_text()

    # Version must be dynamic, not static
    assert 'dynamic = ["version"]' in content, (
        "pyproject.toml must declare version as dynamic for setuptools_scm"
    )
    assert re.search(r'^\s*version\s*=\s*"[^"]+"', content, re.MULTILINE) is None, (
        "pyproject.toml must not have a static version field in [project]"
    )

    # setuptools_scm must be in build requirements
    assert "setuptools_scm" in content, (
        "setuptools_scm must be listed in [build-system].requires"
    )

    # [tool.setuptools_scm] section must exist
    assert "[tool.setuptools_scm]" in content, (
        "pyproject.toml must have a [tool.setuptools_scm] section"
    )


def test_init_uses_importlib_metadata():
    """Test that __init__.py reads version from importlib.metadata."""
    init_path = (
        Path(__file__).parent.parent / "src" / "alpha_hwr" / "__init__.py"
    )
    content = init_path.read_text()

    assert "importlib.metadata" in content, (
        "__init__.py must use importlib.metadata to read the package version"
    )
    assert re.search(r'__version__\s*=\s*"[^"]+"', content) is None, (
        "__init__.py must not have a hardcoded __version__ string"
    )
