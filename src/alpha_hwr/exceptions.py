import asyncio
import builtins
import struct

from bleak.exc import BleakError


class AlphaHWRError(Exception):
    """Base exception for Alpha HWR errors."""


class ConnectionError(AlphaHWRError, builtins.ConnectionError):
    """
    Raised when the link is not there, or goes while something is using it.

    Deliberately a subclass of the builtin ``ConnectionError`` as well as
    of :class:`AlphaHWRError`, because this package shadows the builtin
    name and modules disagreed about which one they were raising. Whether
    ``raise ConnectionError(...)`` produced this class or the builtin came
    down to whether that particular file happened to import this one -
    ``base.py`` and ``client.py`` raised this, ``session.py`` and
    ``time.py`` the builtin - and a caller had no way to catch both with
    one clause.

    Inheriting from both means ``except ConnectionError`` does the right
    thing under either import, which is what anybody writing it expects.
    """


class ProtocolError(AlphaHWRError):
    """Raised when protocol parsing fails."""


class TimeoutError(AlphaHWRError):
    """Raised when operations timeout."""


# ---------------------------------------------------------------------------
# Error groups for read paths
# ---------------------------------------------------------------------------
#
# A pump read fails in two ordinary ways, and neither should take down the
# caller: the BLE link drops or goes quiet, or the pump answers with bytes
# that do not decode. These tuples name those failures so read paths can
# degrade to "no data" without also swallowing genuine bugs (an
# AttributeError or TypeError in our own code still propagates).

#: The link dropped, timed out, or the OS refused the transfer.
#: OSError covers the builtin ConnectionError that Session guards raise,
#: and AlphaHWRError covers this module's own ConnectionError.
TRANSPORT_ERRORS: tuple[type[Exception], ...] = (
    AlphaHWRError,
    BleakError,
    OSError,
    asyncio.TimeoutError,
)

#: The response arrived but is malformed, truncated, or out of range.
#: pydantic's ValidationError is a ValueError subclass and is covered here.
DECODE_ERRORS: tuple[type[Exception], ...] = (
    IndexError,
    KeyError,
    ValueError,
    struct.error,
)

#: Everything a register read may legitimately fail with.
READ_ERRORS: tuple[type[Exception], ...] = TRANSPORT_ERRORS + DECODE_ERRORS
