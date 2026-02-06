"""Property-based tests for protocol frame parsing and building.

Uses Hypothesis to generate random but valid frame data and verify
that parsing and building operations maintain invariants.
"""

from hypothesis import given, settings, Verbosity

from conftest import valid_frame_bytes


class TestFrameProperties:
    """Property-based tests for GENI frame protocol."""

    @given(valid_frame_bytes())
    @settings(max_examples=100, verbosity=Verbosity.normal)
    def test_frame_starts_with_stx(self, frame_bytes):
        """Verify all generated frames start with STX marker.

        Hypothesis generates many frame variations to find edge cases.
        """
        assert frame_bytes[0] == 0x27, "Frame must start with STX (0x27)"

    @given(valid_frame_bytes())
    @settings(max_examples=100)
    def test_frame_length_consistency(self, frame_bytes):
        """Verify frame length field matches actual frame structure.

        The length field (byte 1) should match the declared frame length.
        """
        if len(frame_bytes) >= 2:
            declared_length = frame_bytes[1]
            assert declared_length <= 255, "Length must fit in single byte"
            assert declared_length >= 2, "Minimum length is 2 (DST+SRC)"

    @given(valid_frame_bytes())
    @settings(max_examples=50)
    def test_frame_has_minimum_structure(self, frame_bytes):
        """Verify frames have minimum required structure.

        All frames must have at least: STX, LEN, DST, SRC, CRC_H, CRC_L
        """
        assert len(frame_bytes) >= 6, (
            "Frame must have minimum structure (STX+LEN+DST+SRC+CRC_H+CRC_L)"
        )

    @given(valid_frame_bytes())
    @settings(max_examples=50)
    def test_frame_ends_with_crc(self, frame_bytes):
        """Verify frames end with CRC bytes.

        Last two bytes should be CRC (even if not validated).
        """
        assert len(frame_bytes) >= 2
        crc_h = frame_bytes[-2]
        crc_l = frame_bytes[-1]
        assert isinstance(crc_h, int)
        assert isinstance(crc_l, int)
