import unittest

from app import FrameStream, checksum_valid, decode_cells, decode_status, make_read_request


STATUS_FRAME = bytes.fromhex(
    "AA 21 1A B2 34 00 00 0E 2E 00 00 58 64 8A 56 01 00 "
    "A0 86 01 00 00 00 1B 1A 1A 1A 1D 1A C1 04"
)
CELLS_FRAME = bytes.fromhex(
    "AA 22 30 2E 0D 2D 0D 2F 0D 2C 0D "
    + "00 " * 40
    + "3C 01"
)


class ParserTests(unittest.TestCase):
    def test_status(self):
        self.assertTrue(checksum_valid(STATUS_FRAME))
        status = decode_status(STATUS_FRAME[3:-2])
        self.assertEqual(status.state_of_charge, 88)
        self.assertAlmostEqual(status.voltage_v, 13.490)
        self.assertAlmostEqual(status.current_a, 11.790)
        self.assertEqual(status.temperature_t1_c, 27)
        self.assertEqual(status.temperature_mos_c, 29)

    def test_cells(self):
        self.assertTrue(checksum_valid(CELLS_FRAME))
        self.assertEqual(decode_cells(CELLS_FRAME[3:-2]), [3.374, 3.373, 3.375, 3.372])

    def test_stream_handles_fragmentation(self):
        frames = []
        stream = FrameStream(frames.append)
        stream.feed(STATUS_FRAME[:7])
        stream.feed(STATUS_FRAME[7:] + CELLS_FRAME)
        self.assertEqual(frames, [STATUS_FRAME, CELLS_FRAME])

    def test_read_requests(self):
        self.assertEqual(make_read_request(0x21), bytes.fromhex("AA 21 00 21 00"))
        self.assertEqual(make_read_request(0x22), bytes.fromhex("AA 22 00 22 00"))


if __name__ == "__main__":
    unittest.main()
