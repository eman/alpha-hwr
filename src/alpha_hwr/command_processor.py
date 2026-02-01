"""
Command Processor Module for Grundfos ALPHA HWR.

This module provides a robust command execution engine driven by the GENI profile XML.
It handles command validation, parameter conversion, and transactional execution.
"""

import asyncio
import logging
import struct
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, Union
from pathlib import Path

from .client import AlphaHWRClient
from .protocol import FrameBuilder
from .profile_parser import GeniProfileParser, Parameter

logger = logging.getLogger(__name__)


class CommandState(Enum):
    """State of a command transaction."""

    PENDING = auto()
    VALIDATING = auto()
    SENDING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class CommandResult:
    """Result of a command execution."""

    success: bool
    message: str
    data: Optional[bytes] = None


@dataclass
class CommandTransaction:
    """Tracks a single command execution lifecycle."""

    id: str
    command_name: str
    params: Any
    state: CommandState = CommandState.PENDING
    result: Optional[CommandResult] = None
    _future: asyncio.Future = field(default_factory=asyncio.Future)

    def wait(self):
        """Return the future to await completion."""
        return self._future


class CommandProcessor:
    """
    Executes commands based on GENI profile definitions.
    """

    _ALIASES: Dict[str, str] = {
        "START": "AUTO",
        "RESET": "RESET_ALARM",  # Common alias if RESET exists in profile as something else
    }

    def __init__(self, client: AlphaHWRClient, profile_path: Union[str, Path]):
        self.client = client
        self.parser = GeniProfileParser(profile_path)
        self.transactions: Dict[str, CommandTransaction] = {}
        self._initialized = False

    def initialize(self):
        """Load and parse the profile."""
        if not self._initialized:
            self.parser.parse()
            logger.info(
                f"CommandProcessor initialized. Loaded {len(self.parser.parameters)} parameters."
            )
            self._initialized = True

    async def submit(self, name: str, value: Any = None) -> CommandResult:
        """
        Submit a command for execution.

        Args:
            name: The name of the parameter/command as defined in the profile (e.g. "set_head", "Stop").
            value: The value to write (for SET commands). None for simple triggers if allowed.

        Returns:
            CommandResult indicating success/failure and raw response.
        """
        if not self._initialized:
            self.initialize()

        # Check aliases
        input_name = name.upper()
        if input_name in self._ALIASES:
            logger.info(
                f"Mapping alias '{name}' -> '{self._ALIASES[input_name]}'"
            )
            name = self._ALIASES[input_name]

        tx_id = f"TX-{len(self.transactions) + 1}"
        tx = CommandTransaction(id=tx_id, command_name=name, params=value)
        self.transactions[tx_id] = tx

        try:
            # 1. Validation
            tx.state = CommandState.VALIDATING
            param = self.parser.get_by_name(name)
            if not param:
                # Try case-insensitive search if exact match fails
                found = self.parser.search(name)
                if len(found) == 1:
                    param = found[0]
                else:
                    raise ValueError(f"Unknown command/parameter: '{name}'")

            # 2. Value Conversion & Packet Construction
            tx.state = CommandState.SENDING
            packet = self._build_packet(param, value)

            # 3. Execution
            # Ensure client is connected
            if (
                not self.client.session
                or not self.client.session.is_connected()
            ):
                logger.info("Client not connected, attempting connection...")
                await self.client.connect()
                # Re-enable remote mode if needed
                await self.client.authenticate()

            # Send via transport layer
            if not self.client.transport:
                raise RuntimeError("Transport not initialized")
            resp = await self.client.transport.send_with_response(packet)

            tx.state = CommandState.COMPLETED
            tx.result = CommandResult(True, "Command sent successfully", resp)
            tx._future.set_result(tx.result)
            return tx.result

        except Exception as e:
            tx.state = CommandState.FAILED
            tx.result = CommandResult(False, str(e))
            tx._future.set_result(tx.result)
            logger.error(f"Command processing failed for '{name}': {e}")
            return tx.result

    def _build_packet(self, param: Parameter, value: Any) -> bytes:
        """Construct the appropriate GENI packet based on parameter type."""

        # Check permissions
        if param.rw_type == "ReadOnly":
            raise ValueError(f"Parameter '{param.name}' is ReadOnly")

        # Handle Class 3 (Commands/Actions)
        if param.geni_class == 3:
            # Typically these are ID-only commands (Start, Stop, Remote, etc.)
            # If value is explicitly provided, we might interpret it, but usually ignored for Class 3 triggers.
            return FrameBuilder.build_command_info(
                param.geni_class, param.geni_id
            )

        # Handle Parameters (Write Request)
        if value is None:
            raise ValueError(f"Value required for parameter '{param.name}'")

        payload = self._convert_value(param, value)
        return FrameBuilder.build_write_request(param.register_address, payload)

    def _convert_value(self, param: Parameter, value: Any) -> bytes:
        """Convert input value to bytes based on profile data type."""

        # Handle Enums (lookup by name or value)
        if param.enum_values:
            # If string provided, try to find enum value
            if isinstance(value, str):
                for e in param.enum_values:
                    if e.name.lower() == value.lower():
                        value = e.value
                        break
                else:
                    # Not found in names, check if it's a digit string
                    if not value.isdigit():
                        raise ValueError(
                            f"Invalid enum name '{value}' for '{param.name}'"
                        )

        # Numeric conversion
        if param.data_type == "Float":
            try:
                val_f = float(value)
            except ValueError:
                raise ValueError(
                    f"Expected float for '{param.name}', got '{value}'"
                )

            if param.min_value is not None and val_f < param.min_value:
                raise ValueError(f"Value {val_f} below min {param.min_value}")
            if param.max_value is not None and val_f > param.max_value:
                raise ValueError(f"Value {val_f} above max {param.max_value}")
            return struct.pack(">f", val_f)

        else:
            # Assume Integer-like (Integer, Unsigned, Enum)
            try:
                val_i = int(value)
            except ValueError:
                raise ValueError(
                    f"Expected integer for '{param.name}', got '{value}'"
                )

            # Size handling (naive - profile usually specifies data_type like 'Unsigned16')
            # If data_type string contains '16', usage 2 bytes, etc.
            dt = (param.data_type or "").lower()

            if "32" in dt:
                return struct.pack(">I", val_i)
            elif "16" in dt:
                return struct.pack(">H", val_i)
            else:
                # Default to 1 byte (Unsigned8/Integer8/Enum)
                return bytes([val_i & 0xFF])
