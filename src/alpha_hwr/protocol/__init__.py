"""
Protocol package for GENI frame handling.

This package contains modules for building and parsing GENI protocol frames:

- codec: Primitive encoding/decoding (float, int, etc.)
- frame_builder: Frame construction for requests
- frame_parser: Frame parsing for responses
- telemetry_decoder: Telemetry-specific decoding
"""

from .codec import (
    decode_float_be,
    decode_uint16_be,
    encode_float_be,
    encode_uint16_be,
)
from .frame_builder import FrameBuilder
from .frame_parser import FrameParser, ParsedFrame
from .telemetry_decoder import TelemetryDecoder

__all__ = [
    "FrameBuilder",
    "FrameParser",
    "ParsedFrame",
    "TelemetryDecoder",
    "decode_float_be",
    "decode_uint16_be",
    "encode_float_be",
    "encode_uint16_be",
]
