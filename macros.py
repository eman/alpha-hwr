from __future__ import annotations

from pathlib import Path
from typing import Any

from setuptools_scm import get_version


def _load_version(root: Path) -> str:
    """Return project version string using setuptools_scm."""
    return get_version(root=str(root))


def define_env(env: Any) -> None:
    """Expose project version to MkDocs macros and theme configuration."""
    root = Path(__file__).resolve().parent
    version = _load_version(root)
    env.variables["project_version"] = version
    extra = env.conf.get("extra") or {}
    extra["version"] = version
    env.conf["extra"] = extra
