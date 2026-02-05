from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def _load_version(pyproject_path: Path) -> str:
    """Return project version string from pyproject.toml."""
    with pyproject_path.open("rb") as pyproject_file:
        data = tomllib.load(pyproject_file)
    project = data.get("project", {})
    version = project.get("version")
    if not isinstance(version, str):
        raise ValueError("project.version must be defined in pyproject.toml")
    return version


def define_env(env: Any) -> None:
    """Expose project version to MkDocs macros and theme configuration."""
    root = Path(__file__).resolve().parent
    version = _load_version(root / "pyproject.toml")
    env.variables["project_version"] = version
    extra = env.conf.get("extra") or {}
    extra["version"] = version
    env.conf["extra"] = extra
