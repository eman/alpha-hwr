import asyncio
import struct

from bleak.exc import BleakError


class AlphaHWRError(Exception):
    """Base exception for Alpha HWR errors."""


class ConnectionError(AlphaHWRError):
    """Raised when connection fails."""


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
