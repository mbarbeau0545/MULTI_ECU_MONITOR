import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MULTI_ECU_MONITOR_ROOT = REPO_ROOT / "tools" / "MultiEcuMonitor"
if str(MULTI_ECU_MONITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MULTI_ECU_MONITOR_ROOT))

from Protocole.CAN.Drivers.WaveShare.Src.waveshare import (  # noqa: E402
    UsbCanAdapter,
    CANUSB_FRAME,
    CANUSB_MODE,
)
from Protocole.CAN.Mngmt.AbstractCAN import MsgType, StructCANMsg  # noqa: E402
from Protocole.CAN.Mngmt.WaveShareCanMngmt import WaveshareCanMngmt  # noqa: E402


class WaveShareProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = UsbCanAdapter()
        self.mngmt = WaveshareCanMngmt()

    def test_build_fixed_standard_frame_uses_big_endian_id(self) -> None:
        frame = self.mngmt._build_fixed_20b_frame(
            StructCANMsg(
                id=0x123,
                msgType=MsgType.CAN_MNGMT_MSG_STANDARD,
                length=2,
                data=[0x11, 0x22],
            )
        )

        self.assertEqual(frame[3], 0x01)
        self.assertEqual(list(frame[5:9]), [0x00, 0x00, 0x01, 0x23])

    def test_build_fixed_extended_frame_uses_big_endian_id(self) -> None:
        frame = self.mngmt._build_fixed_20b_frame(
            StructCANMsg(
                id=0x18FFE956,
                msgType=MsgType.CAN_MNGMT_MSG_EXTENDED,
                length=3,
                data=[0xAA, 0xBB, 0xCC],
            )
        )

        self.assertEqual(frame[3], 0x02)
        self.assertEqual(list(frame[5:9]), [0x18, 0xFF, 0xE9, 0x56])

    def test_parse_fixed_standard_frame_recovers_expected_id(self) -> None:
        frame = bytearray(20)
        frame[0] = 0xAA
        frame[1] = 0x55
        frame[2] = 0x01
        frame[3] = 0x01
        frame[4] = 0x01
        frame[5:9] = bytes([0x00, 0x00, 0x01, 0x23])
        frame[9] = 2
        frame[10:12] = bytes([0xDE, 0xAD])
        frame[18] = 0x00
        frame[19] = self.adapter.generate_checksum(frame[2:19])

        msg = self.mngmt._parse_fixed_20b_frame(frame)

        self.assertEqual(msg.id, 0x123)
        self.assertEqual(msg.msgType, MsgType.CAN_MNGMT_MSG_STANDARD)
        self.assertEqual(msg.length, 2)
        self.assertEqual(msg.data, [0xDE, 0xAD])

    def test_parse_fixed_extended_frame_recovers_expected_id(self) -> None:
        frame = bytearray(20)
        frame[0] = 0xAA
        frame[1] = 0x55
        frame[2] = 0x01
        frame[3] = 0x02
        frame[4] = 0x01
        frame[5:9] = bytes([0x18, 0xFF, 0xE9, 0x56])
        frame[9] = 3
        frame[10:13] = bytes([0x01, 0x02, 0x03])
        frame[18] = 0x00
        frame[19] = self.adapter.generate_checksum(frame[2:19])

        msg = self.mngmt._parse_fixed_20b_frame(frame)

        self.assertEqual(msg.id, 0x18FFE956)
        self.assertEqual(msg.msgType, MsgType.CAN_MNGMT_MSG_EXTENDED)
        self.assertEqual(msg.length, 3)
        self.assertEqual(msg.data, [0x01, 0x02, 0x03])

    def test_fixed_frame_round_trip_preserves_id_type_length_and_data(self) -> None:
        original = StructCANMsg(
            id=0x18FFF956,
            msgType=MsgType.CAN_MNGMT_MSG_EXTENDED,
            length=4,
            data=[0x10, 0x20, 0x30, 0x40],
        )

        frame = self.mngmt._build_fixed_20b_frame(original)
        parsed = self.mngmt._parse_fixed_20b_frame(frame)

        self.assertEqual(parsed.id, original.id)
        self.assertEqual(parsed.msgType, original.msgType)
        self.assertEqual(parsed.length, original.length)
        self.assertEqual(parsed.data, original.data)

    def test_command_settings_builds_explicit_filter_and_mask(self) -> None:
        captured = {}

        def fake_send(frame: bytearray) -> int:
            captured["frame"] = bytearray(frame)
            return len(frame)

        self.adapter.frame_send = fake_send

        status = self.adapter.command_settings(
            speed=250000,
            mode=CANUSB_MODE.NORMAL,
            frame=CANUSB_FRAME.EXTENDED,
            filter_id=0x11223344,
            mask_id=0x55667788,
        )

        self.assertEqual(status, 0)
        self.assertIn("frame", captured)
        self.assertEqual(len(captured["frame"]), 20)
        self.assertEqual(captured["frame"][0:3], bytearray([0xAA, 0x55, 0x12]))
        self.assertEqual(captured["frame"][3], self.adapter.speed.value)
        self.assertEqual(captured["frame"][4], CANUSB_FRAME.EXTENDED.value)
        self.assertEqual(list(captured["frame"][5:9]), [0x11, 0x22, 0x33, 0x44])
        self.assertEqual(list(captured["frame"][9:13]), [0x55, 0x66, 0x77, 0x88])
        self.assertEqual(
            captured["frame"][19],
            self.adapter.generate_checksum(captured["frame"][2:19]),
        )

    def test_command_settings_default_accept_all_filter_values(self) -> None:
        captured = {}

        def fake_send(frame: bytearray) -> int:
            captured["frame"] = bytearray(frame)
            return len(frame)

        self.adapter.frame_send = fake_send

        status = self.adapter.command_settings(speed=250000)

        self.assertEqual(status, 0)
        self.assertEqual(list(captured["frame"][5:13]), [0x00] * 8)


if __name__ == "__main__":
    unittest.main()
