from alpha_hwr.protocol.frame_builder import FrameBuilder
from alpha_hwr.protocol.frame_parser import FrameParser
from alpha_hwr.utils import calc_crc16_read


def test_build_set_command_structure():
    """Test that build_set_command produces the correct APDU structure."""
    # Class 3, Op 2, ID 1, Value 1
    # APDU: [Class][OpSpec+Len][ID][Value]
    # OpSpec+Len = (2 << 6) | 2 = 0x82
    # Expected: 27 06 E7 F8 03 82 01 01 [CRC_HI] [CRC_LO]

    cmd = FrameBuilder.build_set_command(0x03, 0x02, 0x01, 0x01)

    # Check length (Start + Len + Dest + Src + APDU(4) + CRC = 10 bytes)
    assert len(cmd) == 10

    # Check Header
    assert cmd[0] == 0x27  # Start
    assert cmd[1] == 0x06  # Length (Dest + Src + APDU)
    assert cmd[2] == 0xE7  # Destination
    assert cmd[3] == 0xF8  # Source (Remote Master)

    # Check APDU
    assert cmd[4] == 0x03  # Class
    assert cmd[5] == 0x82  # OpSpec+Length (0x02 << 6 | 2)
    assert cmd[6] == 0x01  # ID
    assert cmd[7] == 0x01  # Value

    # Verify CRC (excludes Start byte, includes Length)
    payload = cmd[1:-2]
    expected_crc = calc_crc16_read(payload)
    actual_crc = (cmd[8] << 8) | cmd[9]
    assert actual_crc == expected_crc


def test_build_command_info_structure():
    """Test that build_command_info produces the correct APDU structure for commands."""
    # AUTO command: Class 3, ID 6
    # APDU: [Class][OpSpec+Len][ID]
    # OpSpec+Len = (0 << 6) | 1 = 0x01 (INFO operation, 1-byte register)
    # Expected: 27 05 E7 F8 03 01 06 [CRC_HI] [CRC_LO]

    cmd = FrameBuilder.build_command_info(0x03, 0x06)

    # Check length
    assert len(cmd) == 9

    # Check Header
    assert cmd[0] == 0x27  # Start
    assert cmd[1] == 0x05  # Length (Dest + Src + APDU)
    assert cmd[2] == 0xE7  # Destination
    assert cmd[3] == 0xF8  # Source (Remote Master)

    # Check APDU
    assert cmd[4] == 0x03  # Class
    assert cmd[5] == 0x01  # OpSpec+Length (0x00 << 6 | 1)
    assert cmd[6] == 0x06  # ID (AUTO)

    # Verify CRC
    payload = cmd[1:-2]
    expected_crc = calc_crc16_read(payload)
    actual_crc = (cmd[7] << 8) | cmd[8]
    assert actual_crc == expected_crc


def test_build_command_info_remote():
    """Test REMOTE command structure."""
    # REMOTE command: Class 3, ID 7
    cmd = FrameBuilder.build_command_info(0x03, 0x07)

    assert cmd[0] == 0x27
    assert cmd[4] == 0x03  # Class
    assert cmd[5] == 0x01  # OpSpec+Length (INFO operation)
    assert cmd[6] == 0x07  # ID (REMOTE)


def test_build_command_info_stop():
    """Test STOP command structure."""
    # STOP command: Class 3, ID 5
    cmd = FrameBuilder.build_command_info(0x03, 0x05)

    assert cmd[0] == 0x27
    assert cmd[4] == 0x03  # Class
    assert cmd[5] == 0x01  # OpSpec+Length (INFO operation)
    assert cmd[6] == 0x05  # ID (STOP)


def test_command_info_vs_set_command():
    """Verify that command_info (OS_INFO) differs from set_command (OS_SET)."""
    # Command: Class 3, ID 6 (AUTO) - uses OS_INFO
    cmd_info = FrameBuilder.build_command_info(0x03, 0x06)

    # Parameter: Class 3, Op 2, ID 6, Value 1 - uses OS_SET
    cmd_set = FrameBuilder.build_set_command(0x03, 0x02, 0x06, 0x01)

    # Should be different
    assert cmd_info != cmd_set

    # Command is shorter (no value byte)
    assert len(cmd_info) < len(cmd_set)

    # OpSpec+Len differs: INFO=0x01, SET=0x82
    assert cmd_info[5] == 0x01  # OS_INFO (0) << 6 | 1
    assert cmd_set[5] == 0x82  # OS_SET (2) << 6 | 2


def test_frame_parser_class10_response():
    """Test that FrameParser correctly handles Class 10 response frames (OpSpec 0x2B, etc)."""
    # Flow response (OpSpec 0x2B)
    # [Start][Len][Dst][Src][Class=0x0A][OpSpec=0x2B][Seq=0002][Id=3502][Res=0000][DataLen=24][Data...][CRC]
    packet = bytes.fromhex(
        "242ff8e70a2b00023502000024390aa42646e58ac27fffffff7fffffff7fffffff7fffffff3ef3b48b403fccd43f609fc2bc06"
    )

    frame = FrameParser.parse_frame(packet)
    assert frame.valid
    assert frame.crc_valid
    assert frame.class_byte == 0x0A
    # Bytes 6-9 are the object's type, not the register that was read.
    assert frame.type_high == 0x0002
    assert frame.type_low_ver == 0x3502
    # Byte 5 declares 43 payload bytes, which is exactly len - 8.
    assert packet[5] == len(packet) - 8

    # The payload opens with the object's own [00][00][size] header;
    # object_body strips it. Selecting offset 13 by matching byte 5
    # against {0x30, 0x2B, 0x14, ...} worked only because those values are
    # the payload *lengths* of three telemetry registers.
    assert frame.payload.hex().startswith("000024")
    assert frame.object_body.hex().startswith("390aa426")


def test_frame_parser_class10_notification():
    """
    A Class 10 data reply, as recorded from the pump.

    The frame this replaced declared a length of 25 while carrying 24
    bytes, and put the addresses in request order on a response. Both
    make it a frame the pump cannot send, so the parser now rejects it -
    correctly.
    """
    # Object 86 Sub 7, captured 2026-08-20.
    packet = bytes.fromhex("2412f8e70a0e00012f0100000701001b39678ac3f7dd")

    frame = FrameParser.parse_frame(packet)
    assert frame.valid
    assert frame.crc_valid
    assert frame.class_byte == 0x0A
    assert frame.type_high == 0x0001
    assert frame.type_low_ver == 0x2F01
    assert packet[1] + 4 == len(packet)
