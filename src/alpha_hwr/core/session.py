"""
Session state management for Alpha HWR connections.

This module provides explicit state tracking for BLE connections,
making it easier to understand connection lifecycle and implement
proper error handling.

States
------
DISCONNECTED : Initial state, no BLE connection
CONNECTED : BLE connected but not authenticated
AUTHENTICATING : Authentication handshake in progress
AUTHENTICATED : Ready for normal operations
ERROR : Error state requiring reconnection

State Transitions
-----------------
DISCONNECTED -> CONNECTED : connect() succeeds
CONNECTED -> AUTHENTICATING : authenticate() called
AUTHENTICATING -> AUTHENTICATED : authenticate() succeeds
AUTHENTICATING -> ERROR : authenticate() fails
AUTHENTICATED -> DISCONNECTED : disconnect() called
ERROR -> DISCONNECTED : on_disconnected()
* -> ERROR : any operation fails critically
"""

import logging
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class SessionState(IntEnum):
    """
    Connection session states.

    Attributes
    ----------
    DISCONNECTED : int = 0
        No active BLE connection. Initial state and post-disconnect state.
    CONNECTED : int = 1
        BLE GATT connection established but not authenticated.
        Can receive notifications but control commands will fail.
    AUTHENTICATING : int = 2
        Authentication handshake in progress.
        Temporary state during pair_device() operation.
    AUTHENTICATED : int = 3
        Fully authenticated and ready for all operations.
        Control commands, reads, and writes are permitted.
    ERROR : int = 4
        Error state due to connection failure or protocol error.
        Requires disconnect and reconnect to recover.

    Examples
    --------
    >>> state = SessionState.DISCONNECTED
    >>> print(state.name)
    'DISCONNECTED'
    >>> state = SessionState.AUTHENTICATED
    >>> if state >= SessionState.AUTHENTICATED:
    ...     print("Can send control commands")
    """

    DISCONNECTED = 0
    CONNECTED = 1
    AUTHENTICATING = 2
    AUTHENTICATED = 3
    ERROR = 4


class Session:
    """
     Manages connection session state and lifecycle.

     This class provides explicit state tracking and validation for
     Alpha HWR pump connections. It ensures operations are only
     attempted in appropriate states and provides clear error messages
     when operations are attempted in wrong states.

     State Machine
     -------------
     ```
     ┌─────────────┐
     │ DISCONNECTED│◄──────────────┐
     └──────┬──────┘               │
            │ connect()            │ disconnect()
            ▼                      │
     ┌─────────────┐               │
     │  CONNECTED  │               │
     └──────┬──────┘               │
            │ authenticate()       │
            ▼                      │
     ┌───────────────┐             │
     │AUTHENTICATING │             │
     └───┬───────┬───┘             │
         │       │                 │
    success│     │failure          │
         │       ▼                 │
         │  ┌────────┐             │
         │  │ ERROR  │─────────────┘
         │  └────────┘
         │
         ▼
     ┌──────────────┐
     │AUTHENTICATED │──────────────┘
     └──────────────┘
     ```

     Attributes
     ----------
     state : SessionState
         Current session state
     connected_at : datetime | None
         Timestamp when connection was established
     authenticated_at : datetime | None
         Timestamp when authentication completed

     Examples
     --------
     >>> session = Session()
     >>> session.state
     <SessionState.DISCONNECTED: 0>

     >>> session.on_connected()
     >>> session.state
     <SessionState.CONNECTED: 1>

     >>> session.ensure_connected()  # No error
     >>> session.ensure_authenticated()  # Raises error
     ConnectionError: Not authenticated. Current state: CONNECTED

     Notes for Reimplementation
     --------------------------
     This is a simple state machine with validation methods.
     Key implementation points:

     1. Initialize state to DISCONNECTED
     2. Track state transitions with timestamp logging
     3. Provide guard methods (ensure_*) for operation validation
     4. Log all state changes for debugging
     5. Make state transitions atomic (no partial states)
    """

    def __init__(self):
        """Initialize a new session in DISCONNECTED state."""
        self.state: SessionState = SessionState.DISCONNECTED
        self.connected_at: datetime | None = None
        self.authenticated_at: datetime | None = None
        self._last_error: str | None = None
        logger.debug(f"Session initialized: state={self.state.name}")

    def on_connected(self) -> None:
        """
        Transition to CONNECTED state.

        Called when BLE GATT connection is established.
        Updates state and records connection timestamp.

        Raises
        ------
        ValueError
            If called from invalid state (should only be called from DISCONNECTED)
        """
        if self.state not in (SessionState.DISCONNECTED, SessionState.ERROR):
            logger.warning(
                f"on_connected() called from unexpected state: {self.state.name}"
            )

        from datetime import UTC, datetime

        self.state = SessionState.CONNECTED
        self.connected_at = datetime.now(UTC)
        self.authenticated_at = None
        self._last_error = None
        logger.info(
            f"Session state: {self.state.name} (connected_at={self.connected_at})"
        )

    def on_authenticating(self) -> None:
        """
        Transition to AUTHENTICATING state.

        Called when authentication handshake begins.

        Raises
        ------
        ValueError
            If called from state other than CONNECTED or AUTHENTICATED
        """
        if self.state not in (
            SessionState.CONNECTED,
            SessionState.AUTHENTICATED,
        ):
            raise ValueError(
                f"Cannot authenticate from state {self.state.name}. "
                "Must be CONNECTED or AUTHENTICATED first."
            )

        self.state = SessionState.AUTHENTICATING
        logger.info(f"Session state: {self.state.name}")

    def on_authenticated(self) -> None:
        """
        Transition to AUTHENTICATED state.

        Called when authentication handshake completes successfully.
        Updates state and records authentication timestamp.

        Raises
        ------
        ValueError
            If called from state other than AUTHENTICATING
        """
        if self.state != SessionState.AUTHENTICATING:
            raise ValueError(
                f"Cannot complete authentication from state {self.state.name}. "
                "Must be AUTHENTICATING."
            )

        from datetime import UTC, datetime

        self.state = SessionState.AUTHENTICATED
        self.authenticated_at = datetime.now(UTC)
        logger.info(
            f"Session state: {self.state.name} "
            f"(authenticated_at={self.authenticated_at})"
        )

    def on_disconnected(self) -> None:
        """
        Transition to DISCONNECTED state.

        Called when BLE connection is closed (graceful or error).
        Clears timestamps and resets state.
        """
        self.state = SessionState.DISCONNECTED
        self.connected_at = None
        self.authenticated_at = None
        self._last_error = None
        logger.info(f"Session state: {self.state.name}")

    def on_error(self, error_message: str) -> None:
        """
        Transition to ERROR state.

        Called when a critical error occurs that requires reconnection.

        Parameters
        ----------
        error_message : str
            Description of the error that occurred
        """
        self.state = SessionState.ERROR
        self._last_error = error_message
        logger.error(f"Session state: {self.state.name} - {error_message}")

    def is_connected(self) -> bool:
        """
        Check if session is connected (any state >= CONNECTED).

        Returns
        -------
        bool
            True if state is CONNECTED, AUTHENTICATING, or AUTHENTICATED
        """
        return self.state >= SessionState.CONNECTED

    def is_authenticated(self) -> bool:
        """
        Check if session is authenticated.

        Returns
        -------
        bool
            True if state is AUTHENTICATED
        """
        return self.state == SessionState.AUTHENTICATED

    def ensure_connected(self) -> None:
        """
        Ensure session is connected (raise if not).

        Use this as a guard before operations that require connection
        but not authentication (e.g., reading telemetry notifications).

        Raises
        ------
        ConnectionError
            If state is DISCONNECTED or ERROR

        Examples
        --------
        >>> session.ensure_connected()
        >>> # Safe to read notifications now
        """
        if not self.is_connected():
            raise ConnectionError(
                f"Not connected. Current state: {self.state.name}. "
                f"Last error: {self._last_error or 'None'}"
            )

    def ensure_authenticated(self) -> None:
        """
        Ensure session is authenticated (raise if not).

        Use this as a guard before control operations that require
        authentication (e.g., mode changes, setpoint writes).

        Raises
        ------
        ConnectionError
            If state is not AUTHENTICATED

        Examples
        --------
        >>> session.ensure_authenticated()
        >>> # Safe to send control commands now
        """
        if not self.is_authenticated():
            raise ConnectionError(
                f"Not authenticated. Current state: {self.state.name}. "
                "Call authenticate() first."
            )

    def get_state_name(self) -> str:
        """
        Get human-readable state name.

        Returns
        -------
        str
            State name (e.g., "AUTHENTICATED")
        """
        return self.state.name

    def get_uptime_seconds(self) -> float | None:
        """
        Get session uptime in seconds.

        Returns
        -------
        float | None
            Seconds since connection, or None if not connected
        """
        if self.connected_at:
            from datetime import UTC, datetime

            return (datetime.now(UTC) - self.connected_at).total_seconds()
        return None

    def __repr__(self) -> str:
        """String representation of session."""
        if self.state == SessionState.AUTHENTICATED and self.authenticated_at:
            uptime = self.get_uptime_seconds()
            return (
                f"Session(state={self.state.name}, "
                f"uptime={uptime:.1f}s, "
                f"authenticated_at={self.authenticated_at})"
            )
        return f"Session(state={self.state.name})"
