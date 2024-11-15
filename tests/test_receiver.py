import unittest

import pytest


class TestFixedStreamReceiver(unittest.TestCase):
    def _makeOne(self, cl, buf):
        from waitress.receiver import FixedStreamReceiver

        return FixedStreamReceiver(cl, buf)

    def test_received_remain_lt_1(self):
        buf = DummyBuffer()
        inst = self._makeOne(0, buf)
        result = inst.received("a")
        self.assertEqual(result, 0)
        self.assertTrue(inst.completed)

    def test_received_remain_lte_datalen(self):
        buf = DummyBuffer()
        inst = self._makeOne(1, buf)
        result = inst.received("aa")
        self.assertEqual(result, 1)
        self.assertTrue(inst.completed)
        self.assertEqual(inst.completed, 1)
        self.assertEqual(inst.remain, 0)
        self.assertListEqual(buf.data, ["a"])

    def test_received_remain_gt_datalen(self):
        buf = DummyBuffer()
        inst = self._makeOne(10, buf)
        result = inst.received("aa")
        self.assertEqual(result, 2)
        self.assertFalse(inst.completed)
        self.assertEqual(inst.remain, 8)
        self.assertListEqual(buf.data, ["aa"])

    def test_getfile(self):
        buf = DummyBuffer()
        inst = self._makeOne(10, buf)
        self.assertEqual(inst.getfile(), buf)

    def test_getbuf(self):
        buf = DummyBuffer()
        inst = self._makeOne(10, buf)
        self.assertEqual(inst.getbuf(), buf)

    def test___len__(self):
        buf = DummyBuffer(["1", "2"])
        inst = self._makeOne(10, buf)
        self.assertEqual(inst.__len__(), 2)


class TestChunkedReceiver(unittest.TestCase):
    def _makeOne(self, buf):
        from waitress.receiver import ChunkedReceiver

        return ChunkedReceiver(buf)

    def test_alreadycompleted(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        inst.completed = True
        result = inst.received(b"a")
        self.assertEqual(result, 0)
        self.assertTrue(inst.completed)

    def test_received_remain_gt_zero(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        inst.chunk_remainder = 100
        result = inst.received(b"a")
        self.assertEqual(inst.chunk_remainder, 99)
        self.assertEqual(result, 1)
        self.assertFalse(inst.completed)

    def test_received_control_line_notfinished(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        result = inst.received(b"a")
        self.assertEqual(inst.control_line, b"a")
        self.assertEqual(result, 1)
        self.assertFalse(inst.completed)

    def test_received_control_line_finished_garbage_in_input(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        result = inst.received(b"garbage\r\n")
        self.assertEqual(result, 9)
        self.assertTrue(inst.error)

    def test_received_control_line_finished_all_chunks_not_received(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        result = inst.received(b"a;discard\r\n")
        self.assertEqual(inst.control_line, b"")
        self.assertEqual(inst.chunk_remainder, 10)
        self.assertFalse(inst.all_chunks_received)
        self.assertEqual(result, 11)
        self.assertFalse(inst.completed)

    def test_received_control_line_finished_all_chunks_received(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        result = inst.received(b"0;discard\r\n")
        self.assertEqual(inst.control_line, b"")
        self.assertTrue(inst.all_chunks_received)
        self.assertEqual(result, 11)
        self.assertFalse(inst.completed)

    def test_received_trailer_startswith_crlf(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        inst.all_chunks_received = True
        result = inst.received(b"\r\n")
        self.assertEqual(result, 2)
        self.assertTrue(inst.completed)

    def test_received_trailer_startswith_lf(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        inst.all_chunks_received = True
        result = inst.received(b"\n")
        self.assertEqual(result, 1)
        self.assertFalse(inst.completed)

    def test_received_trailer_not_finished(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        inst.all_chunks_received = True
        result = inst.received(b"a")
        self.assertEqual(result, 1)
        self.assertFalse(inst.completed)

    def test_received_trailer_finished(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        inst.all_chunks_received = True
        result = inst.received(b"abc\r\n\r\n")
        self.assertEqual(inst.trailer, b"abc\r\n\r\n")
        self.assertEqual(result, 7)
        self.assertTrue(inst.completed)

    def test_getfile(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        self.assertEqual(inst.getfile(), buf)

    def test_getbuf(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        self.assertEqual(inst.getbuf(), buf)

    def test___len__(self):
        buf = DummyBuffer(["1", "2"])
        inst = self._makeOne(buf)
        self.assertEqual(len(inst), 2)

    def test_received_chunk_is_properly_terminated(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        data = b"4\r\nWiki\r\n"
        result = inst.received(data)
        self.assertEqual(result, len(data))
        self.assertFalse(inst.completed)
        self.assertEqual(buf.data[0], b"Wiki")

    def test_received_chunk_not_properly_terminated(self):
        from waitress.utilities import BadRequest

        buf = DummyBuffer()
        inst = self._makeOne(buf)
        data = b"4\r\nWikibadchunk\r\n"
        result = inst.received(data)
        self.assertEqual(result, len(data))
        self.assertFalse(inst.completed)
        self.assertEqual(buf.data[0], b"Wiki")
        self.assertIsInstance(inst.error, BadRequest)

    def test_received_multiple_chunks(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        data = (
            b"4\r\n"
            b"Wiki\r\n"
            b"5\r\n"
            b"pedia\r\n"
            b"E\r\n"
            b" in\r\n"
            b"\r\n"
            b"chunks.\r\n"
            b"0\r\n"
            b"\r\n"
        )
        result = inst.received(data)
        self.assertEqual(result, len(data))
        self.assertTrue(inst.completed)
        self.assertEqual(b"".join(buf.data), b"Wikipedia in\r\n\r\nchunks.")
        self.assertIsNone(inst.error)

    def test_received_multiple_chunks_split(self):
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        data1 = b"4\r\nWiki\r"
        result = inst.received(data1)
        self.assertEqual(result, len(data1))

        data2 = (
            b"\n5\r\n"
            b"pedia\r\n"
            b"E\r\n"
            b" in\r\n"
            b"\r\n"
            b"chunks.\r\n"
            b"0\r\n"
            b"\r\n"
        )

        result = inst.received(data2)
        self.assertEqual(result, len(data2))

        self.assertTrue(inst.completed)
        self.assertEqual(b"".join(buf.data), b"Wikipedia in\r\n\r\nchunks.")
        self.assertIsNone(inst.error)


class TestChunkedReceiverParametrized:
    def _makeOne(self, buf):
        from waitress.receiver import ChunkedReceiver

        return ChunkedReceiver(buf)

    @pytest.mark.parametrize(
        "invalid_extension", [b"\n", b"invalid=", b"\r", b"invalid = true"]
    )
    def test_received_invalid_extensions(self, invalid_extension):
        from waitress.utilities import BadRequest

        buf = DummyBuffer()
        inst = self._makeOne(buf)
        data = b"4;" + invalid_extension + b"\r\ntest\r\n"
        result = inst.received(data)
        assert result == len(data)
        assert isinstance(inst.error, BadRequest)
        assert inst.error.body == "Invalid chunk extension"

    @pytest.mark.parametrize(
        "valid_extension", [b"test", b"valid=true", b"valid=true;other=true"]
    )
    def test_received_valid_extensions(self, valid_extension):
        # While waitress may ignore extensions in Chunked Encoding, we do want
        # to make sure that we don't fail when we do encounter one that is
        # valid
        buf = DummyBuffer()
        inst = self._makeOne(buf)
        data = b"4;" + valid_extension + b"\r\ntest\r\n"
        result = inst.received(data)
        assert result == len(data)
        assert inst.error is None

    @pytest.mark.parametrize(
        "invalid_size", [b"0x04", b"+0x04", b"x04", b"+04", b" 04", b" 0x04"]
    )
    def test_received_invalid_size(self, invalid_size):
        from waitress.utilities import BadRequest

        buf = DummyBuffer()
        inst = self._makeOne(buf)
        data = invalid_size + b"\r\ntest\r\n"
        result = inst.received(data)
        assert result == len(data)
        assert isinstance(inst.error, BadRequest)
        assert inst.error.body == "Invalid chunk size"


class DummyBuffer:
    def __init__(self, data=None):
        if data is None:
            data = []
        self.data = data

    def append(self, s):
        self.data.append(s)

    def getfile(self):
        return self

    def __len__(self):
        return len(self.data)
