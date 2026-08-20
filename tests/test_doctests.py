"""
Every example in the source that claims to be runnable, runs.

This repository already guards the prose in ``docs/`` against drifting
away from the code (``test_docs_consistency.py``). The docstrings had no
such guard, and 185 of the 279 examples in them were failing - most
because they were never executable in the first place (``await`` at the
top level, or a ``client`` nobody had constructed), and seven because they
were simply wrong:

* ``encode_float_be(1.5)`` claimed ``b'\\x3f\\xc0\\x00\\x00'``; Python
  prints that byte as ``?``.
* ``decode_float_be(b'\\x00\\x00')`` claimed to print ``None``, which a
  bare expression does not do.
* ``build_command_info(0x02, 0x45)`` claimed ``'27050e7f8020345...'`` -
  an ellipsis, and a stray ``0`` in the address.
* the frame length for a 3-byte register read was given as 9; it is 11.
* three ``Session`` examples referred to a session that was never built,
  and one expected a raised ``ConnectionError`` without a traceback.

Illustrative examples now carry ``# doctest: +SKIP`` and say so. That is
the honest distinction: they are documentation, not tests, and marking
them keeps the ones that *are* tests visible.
"""

from __future__ import annotations

import doctest
import importlib
import pkgutil

import pytest

import alpha_hwr

MODULES = sorted(
    m.name for m in pkgutil.walk_packages(alpha_hwr.__path__, "alpha_hwr.")
)


@pytest.mark.parametrize("module_name", MODULES)
def test_module_doctests(module_name: str) -> None:
    module = importlib.import_module(module_name)
    result = doctest.testmod(module, verbose=False, report=True)
    assert result.failed == 0, (
        f"{result.failed} of {result.attempted} doctests failed in "
        f"{module_name}"
    )


def test_the_suite_still_runs_a_meaningful_number_of_examples() -> None:
    """
    A floor, so the previous state cannot be reached by skipping everything.

    Marking an example ``+SKIP`` is the right call for one that cannot run,
    and the wrong call for one that merely fails. Without a floor the
    difference is invisible: a green run and a fully-skipped run look the
    same.
    """
    attempted = sum(
        doctest.testmod(
            importlib.import_module(name), verbose=False, report=False
        ).attempted
        for name in MODULES
    )
    assert attempted >= 250, (
        f"only {attempted} doctests ran; examples are being skipped rather "
        f"than fixed"
    )
