"""
Tests that the documentation describes things that exist.

An audit found roughly forty code examples across docs/ that had never
run: CLI commands that were never registered, flags on commands that take
positionals, and client attributes under names the code does not use
(``client.clock`` for ``client.time``, ``client.events`` for
``client.event_log``). Every one of them looked plausible.

These are cheap structural checks, not a substitute for running the
examples. They catch the failure mode that actually occurred - prose
drifting away from an API that moved - and they catch it in CI rather
than in an issue report.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.main import get_command  # type: ignore[import-not-found]

from alpha_hwr.cli.app import app

REPO = Path(__file__).resolve().parent.parent
DOC_FILES = sorted(
    [*(REPO / "docs").rglob("*.md"), REPO / "README.md"],
)

#: Words that follow "alpha-hwr" in prose without being commands.
_NOT_COMMANDS = {"pip", "backup", "restore", "library", "config"}


def _docs_text() -> list[tuple[Path, str]]:
    return [(p, p.read_text()) for p in DOC_FILES if p.exists()]


def _cli_registry() -> dict[str, dict[str, set[str]]]:
    """``{group: {command: {--flag, ...}}}`` for the real CLI."""
    cli = get_command(app)
    registry: dict[str, dict[str, set[str]]] = {}
    for group_name, group in cli.commands.items():
        commands: dict[str, set[str]] = {}
        for cmd_name, cmd in getattr(group, "commands", {}).items():
            opts = {"--help"}
            for param in cmd.params:
                opts |= set(getattr(param, "opts", []))
                opts |= set(getattr(param, "secondary_opts", []))
            commands[cmd_name] = opts
        registry[group_name] = commands
    return registry


#: ``alpha-hwr <group> <command> <rest of the line>``
_INVOCATION = re.compile(
    r"alpha-hwr\s+([a-z][a-z-]*)\s+([a-z][a-z-]*)([^\n`]*)"
)


def _invocations() -> list[tuple[Path, str, str, str]]:
    found = []
    for path, text in _docs_text():
        for match in _INVOCATION.finditer(text):
            group, command, rest = match.groups()
            if group in _NOT_COMMANDS:
                continue
            found.append((path, group, command, rest))
    return found


def test_the_docs_invoke_some_cli_commands() -> None:
    """A guard that finds nothing to check has stopped working."""
    assert len(_invocations()) > 20


def test_every_documented_command_exists() -> None:
    """
    Caught in the audit: ``config list-backups``, ``schedule show``,
    ``schedule set-entry``, ``schedule export``/``import``,
    ``monitor telemetry``, and four ``control set-autoadapt*`` commands.
    """
    registry = _cli_registry()
    missing = []

    for path, group, command, _ in _invocations():
        rel = path.relative_to(REPO)
        if group not in registry:
            missing.append(f"{rel}: no CLI group '{group}' (in '{command}')")
        elif command not in registry[group]:
            missing.append(
                f"{rel}: 'alpha-hwr {group} {command}' is not a command"
            )

    assert not missing, "documented commands that do not exist:\n" + "\n".join(
        sorted(set(missing))
    )


def test_every_documented_flag_exists() -> None:
    """
    Caught in the audit: ``control set-mode --setpoint`` and
    ``control set-pressure --value`` (both take positionals),
    ``device info --format``, ``monitor live --timeout``,
    ``schedule clear --all``, and six invented ``config`` flags.
    """
    registry = _cli_registry()
    bad = []

    for path, group, command, rest in _invocations():
        valid = registry.get(group, {}).get(command)
        if valid is None:
            continue  # covered by the previous test
        for flag in re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", rest):
            if flag not in valid:
                rel = path.relative_to(REPO)
                bad.append(f"{rel}: 'alpha-hwr {group} {command} {flag}'")

    assert not bad, "documented flags that do not exist:\n" + "\n".join(
        sorted(set(bad))
    )


# ---------------------------------------------------------------------------
# Client attributes
# ---------------------------------------------------------------------------

#: ``client.<attr>`` in prose or code.
_CLIENT_ATTR = re.compile(r"\bclient\.([a-z_][a-z0-9_]*)")

#: ``client.py`` and ``client.md`` are filenames, not attribute access.
_FILE_SUFFIXES = {"py", "md", "cpp", "h", "json", "yml"}

#: Not ours. Raw-protocol examples bind ``client`` to a BleakClient, whose
#: surface is the BLE library's problem rather than this package's.
_BLEAK_METHODS = {
    "connect",
    "disconnect",
    "discover_services",
    "get_service",
    "is_connected",
    "read_gatt_char",
    "services",
    "start_notify",
    "stop_notify",
    "write_gatt_char",
}


def _client_attributes() -> set[str]:
    from alpha_hwr.client import AlphaHWRClient

    names = set(dir(AlphaHWRClient))
    # Service handles are assigned in _initialize_services, not declared
    # on the class, so dir() alone misses them.
    names |= set(AlphaHWRClient.__init__.__code__.co_names)
    names |= set(AlphaHWRClient._initialize_services.__code__.co_names)
    return names


def test_every_documented_client_attribute_exists() -> None:
    """
    Caught in the audit: ``client.clock`` (it is ``client.time``),
    ``client.events`` (``client.event_log``) and
    ``client.get_telemetry()`` (no such method).
    """
    known = _client_attributes()
    bad = []

    for path, text in _docs_text():
        for match in _CLIENT_ATTR.finditer(text):
            attr = match.group(1)
            if attr in known or attr in _BLEAK_METHODS:
                continue
            if attr in _FILE_SUFFIXES:
                continue
            bad.append(f"{path.relative_to(REPO)}: client.{attr}")

    assert not bad, (
        "documented client attributes that do not exist:\n"
        + "\n".join(sorted(set(bad)))
    )


# ---------------------------------------------------------------------------
# Python examples
# ---------------------------------------------------------------------------

_PY_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


@pytest.mark.parametrize(
    "doc",
    [
        "docs/guides/verified_writes.md",
        "docs/guides/run_state_and_schedules.md",
        "docs/getting_started/quick_start.md",
        "docs/reference/data_models.md",
        "README.md",
    ],
)
def test_python_examples_parse(doc: str) -> None:
    """
    Syntax only - these examples talk to a pump, so running them is not
    an option here. It still catches a truncated or mis-indented block.
    """
    import ast

    text = (REPO / doc).read_text()
    blocks = _PY_BLOCK.findall(text)
    assert blocks, f"{doc} has no python examples; has it been renamed?"

    for n, code in enumerate(blocks, 1):
        if code.lstrip().startswith(">>>"):
            continue  # doctest style, not a module
        body = code
        needs_async = re.search(
            r"^\s*(await|async for|async with)\b", body, re.MULTILINE
        )
        if needs_async and "async def" not in body:
            body = "async def _example():\n" + "\n".join(
                "    " + line for line in body.split("\n")
            )
        try:
            ast.parse(body)
        except SyntaxError as exc:
            pytest.fail(f"{doc} block {n}: {exc}")


# ---------------------------------------------------------------------------
# Generated pages
# ---------------------------------------------------------------------------


def test_test_vectors_page_is_not_stale() -> None:
    """
    ``docs/reimplementation/test_vectors.md`` is emitted by executing the
    codec, so it cannot be wrong unless the library is. This asserts the
    committed copy still matches what the generator produces.

    The hand-written version it replaced specified CRC-16/MODBUS and
    decoded 0x46E5B000 as 14710.0 (it is 29400.0). Nothing caught either,
    because nothing ran it.
    """
    import importlib.util

    script = REPO / "scripts" / "generate_test_vectors.py"
    spec = importlib.util.spec_from_file_location("_gen_vectors", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected = module.build()
    actual = (
        REPO / "docs" / "reimplementation" / "test_vectors.md"
    ).read_text()

    assert actual == expected, (
        "test_vectors.md is stale; regenerate it with\n"
        "  uv run python scripts/generate_test_vectors.py"
    )
