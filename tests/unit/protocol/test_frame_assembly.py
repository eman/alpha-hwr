"""
Tests for the shared GENI frame assembly.

Three hand-rolled copies of this used to exist across the services, so a
byte-level test of one proved nothing about the others. These pin the
header layout and CRC convention against frames whose bytes are known
independently - the authentication packets, which are captured constants
the pump accepts.
"""

from __future__ import annotations

import pytest

from alpha_hwr.core.authentication import AuthenticationHandler
from alpha_hwr.protocol import FrameBuilder


@pytest.mark.parametrize(
    ("apdu", "expected"),
    [
        # The two extension packets from the handshake. Their bytes come
        # from packet captures, so reproducing them exactly is evidence the
        # length field and CRC are right rather than merely self-consistent.
        (bytes([0x05, 0xC1, 0x4B]), AuthenticationHandler.EXTEND_1),
        (bytes([0x0B, 0xC1, 0x0F]), AuthenticationHandler.EXTEND_2),
        (
            bytes([0x02, 0x03, 0x94, 0x95, 0x96]),
            AuthenticationHandler.LEGACY_MAGIC,
        ),
        (
            bytes([0x0A, 0x03, 0x56, 0x00, 0x06]),
            AuthenticationHandler.CLASS10_UNLOCK,
        ),
    ],
)
def test_builder_reproduces_captured_frames(
    apdu: bytes, expected: bytes
) -> None:
    assert FrameBuilder.build_geni_frame(apdu) == expected


def test_frame_header_layout() -> None:
    frame = FrameBuilder.build_geni_frame(bytes([0x03, 0x81, 0x06]))

    assert frame[0] == 0x27, "start byte"
    assert frame[1] == 5, "length counts ServiceID + Source + APDU"
    assert frame[2] == 0xE7, "service id"
    assert frame[3] == 0xF8, "source address"
    assert len(frame) == frame[1] + 4, "total = length + start + len + CRC"


def test_class10_object_read_addresses_object_as_one_byte() -> None:
    """A configuration object is a single-byte Object ID plus a 16-bit Sub."""
    frame = FrameBuilder.build_class10_object_read(86, 7)

    assert frame[4] == 0x0A, "class 10"
    assert frame[5] == 0x03, "OpSpec INFO"
    assert frame[6] == 86, "object id, one byte"
    assert frame[7:9] == bytes([0x00, 0x07]), "sub id, big-endian"


def test_object_read_and_register_read_are_the_same_encoding() -> None:
    """
    The Object/Sub pair and the 24-bit register are two spellings of one
    address, not two addressing modes. Both builders exist to match how
    callers think about the address; the pump sees the same bytes.
    """
    assert FrameBuilder.build_class10_object_read(
        0x57, 0x0045
    ) == FrameBuilder.build_class10_read(0x570045)


def test_base_service_builder_agrees_with_frame_builder() -> None:
    """The services' helper must not drift from the shared builder."""
    from unittest.mock import MagicMock

    from alpha_hwr.services.base import BaseService

    service = BaseService(MagicMock(), MagicMock())
    apdu = bytes([0x0A, 0x84, 0x00, 0x0F, 0x00, 0x56, 0x45, 0x65, 0x70, 0x00])

    assert service._build_geni_packet(
        0xF8, 0xE7, apdu
    ) == FrameBuilder.build_geni_frame(apdu)
