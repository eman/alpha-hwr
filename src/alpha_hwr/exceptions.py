class AlphaHWRError(Exception):
    """Base exception for Alpha HWR errors."""

    pass


class ConnectionError(AlphaHWRError):
    """Raised when connection fails."""

    pass


class ProtocolError(AlphaHWRError):
    """Raised when protocol parsing fails."""

    pass


class TimeoutError(AlphaHWRError):
    """Raised when operations timeout."""

    pass
