"""
Every surface reads the pump's clock the same way.

The risk this guards is interoperability rather than arithmetic. More than
one client writes this pump's clock - the Grundfos GO app, the ESPHome
component, this library - and the pump cannot say which time base a value
arrived in, because it has no timezone or UTC-offset field anywhere in its
GENI profile. Two clients disagreeing is worse than either being wrong
alone: one sets the clock, the other resets it seven hours out, and every
stored schedule fires at the wrong hour.

The device evidence, read off the bench unit:

  * ``DateTimeActual`` carries ``dst_status``, and it reads ``SummerTime``.
    A device tracking whether it is in summer time is keeping local time.
  * ``DaylightSavingTime`` (Object 94 Sub 102) reads enabled, second Sunday
    of March to first Sunday of November, 60-minute offset - the US rule.
    The pump shifts its own clock.
  * The pump's clock matched host local time to the second.

So the rule is: express local wall clock, never UTC.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta

import pytest

from alpha_hwr import pump_time


def _identifiers(module) -> set[str]:
    """Every name the module's *code* mentions, ignoring prose."""
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.rsplit(".", 1)[-1])
    return names


from alpha_hwr.pump_time import MAX_PUMP_TIME, from_pump_time, to_pump_time
from alpha_hwr.services import event_log, history, single_event


class TestTheEncoding:
    def test_it_round_trips_exactly(self) -> None:
        when = datetime(2026, 8, 20, 9, 30, 15)
        assert from_pump_time(to_pump_time(when)) == when

    def test_it_round_trips_across_both_dst_transitions(self) -> None:
        """
        No timezone is consulted, so there is no offset to resolve wrongly.

        The ESPHome port had a real bug here, but it is a consequence of
        converting to UTC - which this encoding does not do. Anyone
        "fixing" it by adding a conversion reintroduces that bug.
        """
        for base in (datetime(2026, 3, 8), datetime(2026, 11, 1)):
            when = base
            for _ in range(97):  # 24 h at 15-minute steps
                assert from_pump_time(to_pump_time(when)) == when
                when += timedelta(minutes=15)

    def test_it_never_consults_a_timezone(self) -> None:
        """
        Checked against the parsed code, not the text, so the prose
        explaining *why* not to do this does not trip its own rule.
        """
        names = _identifiers(pump_time)

        for forbidden in ("astimezone", "utcoffset", "localtime", "tzinfo"):
            assert forbidden not in names, (
                f"{forbidden} in the encoding: the pump stores no offset, "
                f"and inventing one is how the other implementation "
                f"acquired a DST bug"
            )

    def test_the_wire_range_is_enforced(self) -> None:
        with pytest.raises(ValueError, match="outside the range"):
            to_pump_time(datetime(1969, 12, 31))
        with pytest.raises(ValueError, match="outside the range"):
            to_pump_time(datetime(2107, 1, 1))
        assert to_pump_time(datetime(2106, 2, 7)) <= MAX_PUMP_TIME


class TestOneTimeBase:
    """No surface may decode a pump timestamp as an aware datetime."""

    def test_a_decoded_timestamp_is_naive(self) -> None:
        assert from_pump_time(1787218200).tzinfo is None

    @pytest.mark.parametrize(
        "module", [single_event, event_log, history], ids=lambda m: m.__name__
    )
    def test_no_module_stamps_a_pump_timestamp_as_utc(self, module) -> None:
        """
        ``fromtimestamp(ts, tz=UTC)`` gives the right digits and the wrong
        instant: the digits are the pump's local wall clock, so anything
        calling ``.astimezone()`` shifts them by the local offset and
        produces a time the pump never meant.
        """
        assert "fromtimestamp" not in _identifiers(module), (
            f"{module.__name__} decodes a pump timestamp itself; it should "
            f"use pump_time.from_pump_time so every surface agrees"
        )

    @pytest.mark.parametrize(
        "module", [single_event, event_log, history], ids=lambda m: m.__name__
    )
    def test_every_module_uses_the_shared_helper(self, module) -> None:
        assert "from_pump_time" in _identifiers(module)
