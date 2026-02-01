"""
Core modules for Alpha HWR BLE communication.

This package contains the foundational components for BLE communication
with Grundfos ALPHA HWR pumps:

- authentication: Authentication handshake sequences
- transport: Low-level BLE packet transport
- session: Connection state management
"""

from .authentication import AuthenticationHandler
from .session import Session, SessionState
from .transport import Transport

__all__ = ["AuthenticationHandler", "Session", "SessionState", "Transport"]
