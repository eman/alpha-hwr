"""Test version consistency across the project files."""

import re
from pathlib import Path


def get_version_from_pyproject():
    """Extract version from pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject_path.read_text()
    match = re.search(r'version = "([^"]+)"', content)
    if match:
        return match.group(1)
    return None


def get_version_from_init():
    """Extract version from __init__.py."""
    init_path = (
        Path(__file__).parent.parent / "src" / "alpha_hwr" / "__init__.py"
    )
    content = init_path.read_text()
    match = re.search(r'__version__ = "([^"]+)"', content)
    if match:
        return match.group(1)
    return None


def get_version_from_mkdocs():
    """Extract version from mkdocs.yml."""
    mkdocs_path = Path(__file__).parent.parent / "mkdocs.yml"
    content = mkdocs_path.read_text()
    match = re.search(r'version: "([^"]+)"', content)
    if match:
        return match.group(1)
    return None


def get_version_from_docs_index():
    """Extract version from docs/index.md."""
    docs_index_path = Path(__file__).parent.parent / "docs" / "index.md"
    content = docs_index_path.read_text()
    match = re.search(r"\*Version: ([^\*]+)\*", content)
    if match:
        return match.group(1)
    return None


def get_version_from_bumpversion_cfg():
    """Extract current_version from .bumpversion.cfg."""
    bumpversion_path = Path(__file__).parent.parent / ".bumpversion.cfg"
    content = bumpversion_path.read_text()
    match = re.search(r"current_version = (.+)", content)
    if match:
        return match.group(1).strip()
    return None


def test_version_consistency():
    """Test that version is consistent across all project files."""
    pyproject_version = get_version_from_pyproject()
    init_version = get_version_from_init()
    mkdocs_version = get_version_from_mkdocs()
    docs_index_version = get_version_from_docs_index()
    bumpversion_version = get_version_from_bumpversion_cfg()

    # Ensure all versions were found
    assert pyproject_version is not None, "Version not found in pyproject.toml"
    assert init_version is not None, "Version not found in __init__.py"
    assert mkdocs_version is not None, "Version not found in mkdocs.yml"
    assert docs_index_version is not None, "Version not found in docs/index.md"
    assert bumpversion_version is not None, (
        "Version not found in .bumpversion.cfg"
    )

    # Check consistency
    assert init_version == pyproject_version, (
        f"Version mismatch: __init__.py ({init_version}) != "
        f"pyproject.toml ({pyproject_version})"
    )
    assert mkdocs_version == pyproject_version, (
        f"Version mismatch: mkdocs.yml ({mkdocs_version}) != "
        f"pyproject.toml ({pyproject_version})"
    )
    assert docs_index_version == pyproject_version, (
        f"Version mismatch: docs/index.md ({docs_index_version}) != "
        f"pyproject.toml ({pyproject_version})"
    )
    assert bumpversion_version == pyproject_version, (
        f"Version mismatch: .bumpversion.cfg ({bumpversion_version}) != "
        f"pyproject.toml ({pyproject_version})"
    )


def test_bumpversion_search_patterns():
    """Test that bumpversion search patterns match actual file content."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    init_path = (
        Path(__file__).parent.parent / "src" / "alpha_hwr" / "__init__.py"
    )
    mkdocs_path = Path(__file__).parent.parent / "mkdocs.yml"
    docs_index_path = Path(__file__).parent.parent / "docs" / "index.md"
    bumpversion_path = Path(__file__).parent.parent / ".bumpversion.cfg"

    # Get current version
    version = get_version_from_pyproject()
    assert version is not None, "Could not determine current version"

    # Check that patterns would match
    pyproject_content = pyproject_path.read_text()
    assert f'version = "{version}"' in pyproject_content, (
        f'pyproject.toml does not contain expected pattern: version = "{version}"'
    )

    init_content = init_path.read_text()
    assert f'__version__ = "{version}"' in init_content, (
        f'__init__.py does not contain expected pattern: __version__ = "{version}"'
    )

    mkdocs_content = mkdocs_path.read_text()
    assert f'version: "{version}"' in mkdocs_content, (
        f'mkdocs.yml does not contain expected pattern: version: "{version}"\n'
        f"This usually means the indentation or quotes don't match the bumpversion config."
    )

    docs_index_content = docs_index_path.read_text()
    assert f"*Version: {version}*" in docs_index_content, (
        f"docs/index.md does not contain expected pattern: *Version: {version}*"
    )

    # Verify .bumpversion.cfg has correct patterns
    bumpversion_content = bumpversion_path.read_text()

    # Check mkdocs.yml pattern includes proper indentation
    # The pattern should have 2 spaces before 'version:'
    assert 'search =   version: "{current_version}"' in bumpversion_content, (
        ".bumpversion.cfg mkdocs.yml search pattern must include proper indentation "
        "(2 spaces before 'version:')"
    )
