import io
import unittest


class TestFileBasedBuffer(unittest.TestCase):
    def _makeOne(self, file=None, from_buffer=None):
        from waitress.buffers import FileBasedBuffer

        buf = FileBasedBuffer(file, from_buffer=from_buffer)
        self.buffers_to_close.append(buf)
        return buf

    def setUp(self):
        self.buffers_to_close = []

    def tearDown(self):
        for buf in self.buffers_to_close:
            buf.close()

    def test_ctor_from_buffer_None(self):
        inst = self._makeOne("file")
        self.assertEqual(inst.file, "file")

    def test_ctor_from_buffer(self):
        from_buffer = io.BytesIO(b"data")
        from_buffer.getfile = lambda *x: from_buffer
        f = io.BytesIO()
        inst = self._makeOne(f, from_buffer)
        self.assertEqual(inst.file, f)
        del from_buffer.getfile
        self.assertEqual(inst.remain, 4)
        from_buffer.close()

    def test___len__(self):
        inst = self._makeOne()
        inst.remain = 10
        self.assertEqual(len(inst), 10)

    def test___nonzero__(self):
        inst = self._makeOne()
        inst.remain = 10
        self.assertTrue(bool(inst))
        inst.remain = 0
        self.assertTrue(bool(inst))

    def test_append(self):
        f = io.BytesIO(b"data")
        inst = self._makeOne(f)
        inst.append(b"data2")
        self.assertEqual(f.getvalue(), b"datadata2")
        self.assertEqual(inst.remain, 5)

    def test_get_skip_true(self):
        f = io.BytesIO(b"data")
        inst = self._makeOne(f)
        result = inst.get(100, skip=True)
        self.assertEqual(result, b"data")
        self.assertEqual(inst.remain, -4)

    def test_get_skip_false(self):
        f = io.BytesIO(b"data")
        inst = self._makeOne(f)
        result = inst.get(100, skip=False)
        self.assertEqual(result, b"data")
        self.assertEqual(inst.remain, 0)

    def test_get_skip_bytes_less_than_zero(self):
        f = io.BytesIO(b"data")
        inst = self._makeOne(f)
        result = inst.get(-1, skip=False)
        self.assertEqual(result, b"data")
        self.assertEqual(inst.remain, 0)

    def test_skip_remain_gt_bytes(self):
        f = io.BytesIO(b"d")
        inst = self._makeOne(f)
        inst.remain = 1
        inst.skip(1)
        self.assertEqual(inst.remain, 0)

    def test_skip_remain_lt_bytes(self):
        f = io.BytesIO(b"d")
        inst = self._makeOne(f)
        inst.remain = 1
        self.assertRaises(ValueError, inst.skip, 2)

    def test_newfile(self):
        inst = self._makeOne()
        self.assertRaises(NotImplementedError, inst.newfile)

    def test_prune_remain_notzero(self):
        f = io.BytesIO(b"d")
        inst = self._makeOne(f)
        inst.remain = 1
        nf = io.BytesIO()
        inst.newfile = lambda *x: nf
        inst.prune()
        self.assertIsNot(inst.file, f)
        self.assertEqual(nf.getvalue(), b"d")

    def test_prune_remain_zero_tell_notzero(self):
        f = io.BytesIO(b"d")
        inst = self._makeOne(f)
        nf = io.BytesIO(b"d")
        inst.newfile = lambda *x: nf
        inst.remain = 0
        inst.prune()
        self.assertIsNot(inst.file, f)
        self.assertEqual(nf.getvalue(), b"d")

    def test_prune_remain_zero_tell_zero(self):
        f = io.BytesIO()
        inst = self._makeOne(f)
        inst.remain = 0
        inst.prune()
        self.assertIs(inst.file, f)

    def test_close(self):
        f = io.BytesIO()
        inst = self._makeOne(f)
        inst.close()
        self.assertTrue(f.closed)
        self.buffers_to_close.remove(inst)


class TestTempfileBasedBuffer(unittest.TestCase):
    def _makeOne(self, from_buffer=None):
        from waitress.buffers import TempfileBasedBuffer

        buf = TempfileBasedBuffer(from_buffer=from_buffer)
        self.buffers_to_close.append(buf)
        return buf

    def setUp(self):
        self.buffers_to_close = []

    def tearDown(self):
        for buf in self.buffers_to_close:
            buf.close()

    def test_newfile(self):
        inst = self._makeOne()
        r = inst.newfile()
        self.assertTrue(hasattr(r, "fileno"))  # file
        r.close()


class TestBytesIOBasedBuffer(unittest.TestCase):
    def _makeOne(self, from_buffer=None):
        from waitress.buffers import BytesIOBasedBuffer

        return BytesIOBasedBuffer(from_buffer=from_buffer)

    def test_ctor_from_buffer_not_None(self):
        f = io.BytesIO()
        f.getfile = lambda *x: f
        inst = self._makeOne(f)
        self.assertTrue(hasattr(inst.file, "read"))

    def test_ctor_from_buffer_None(self):
        inst = self._makeOne()
        self.assertTrue(hasattr(inst.file, "read"))

    def test_newfile(self):
        inst = self._makeOne()
        r = inst.newfile()
        self.assertTrue(hasattr(r, "read"))


class TestReadOnlyFileBasedBuffer(unittest.TestCase):
    def _makeOne(self, file, block_size=8192):
        from waitress.buffers import ReadOnlyFileBasedBuffer

        buf = ReadOnlyFileBasedBuffer(file, block_size)
        self.buffers_to_close.append(buf)
        return buf

    def setUp(self):
        self.buffers_to_close = []

    def tearDown(self):
        for buf in self.buffers_to_close:
            buf.close()

    def test_prepare_not_seekable(self):
        f = KindaFilelike(b"abc")
        inst = self._makeOne(f)
        self.assertFalse(hasattr(inst, "seek"))
        self.assertFalse(hasattr(inst, "tell"))
        result = inst.prepare()
        self.assertFalse(result)
        self.assertEqual(inst.remain, 0)

    def test_prepare_not_seekable_closeable(self):
        f = KindaFilelike(b"abc", close=1)
        inst = self._makeOne(f)
        result = inst.prepare()
        self.assertFalse(result)
        self.assertEqual(inst.remain, 0)
        self.assertTrue(hasattr(inst, "close"))

    def test_prepare_seekable_closeable(self):
        f = Filelike(b"abc", close=1, tellresults=[0, 10])
        inst = self._makeOne(f)
        self.assertEqual(inst.seek, f.seek)
        self.assertEqual(inst.tell, f.tell)
        result = inst.prepare()
        self.assertEqual(result, 10)
        self.assertEqual(inst.remain, 10)
        self.assertEqual(inst.file.seeked, 0)
        self.assertTrue(hasattr(inst, "close"))

    def test_get_numbytes_neg_one(self):
        f = io.BytesIO(b"abcdef")
        inst = self._makeOne(f)
        inst.remain = 2
        result = inst.get(-1)
        self.assertEqual(result, b"ab")
        self.assertEqual(inst.remain, 2)
        self.assertEqual(f.tell(), 0)

    def test_get_numbytes_gt_remain(self):
        f = io.BytesIO(b"abcdef")
        inst = self._makeOne(f)
        inst.remain = 2
        result = inst.get(3)
        self.assertEqual(result, b"ab")
        self.assertEqual(inst.remain, 2)
        self.assertEqual(f.tell(), 0)

    def test_get_numbytes_lt_remain(self):
        f = io.BytesIO(b"abcdef")
        inst = self._makeOne(f)
        inst.remain = 2
        result = inst.get(1)
        self.assertEqual(result, b"a")
        self.assertEqual(inst.remain, 2)
        self.assertEqual(f.tell(), 0)

    def test_get_numbytes_gt_remain_withskip(self):
        f = io.BytesIO(b"abcdef")
        inst = self._makeOne(f)
        inst.remain = 2
        result = inst.get(3, skip=True)
        self.assertEqual(result, b"ab")
        self.assertEqual(inst.remain, 0)
        self.assertEqual(f.tell(), 2)

    def test_get_numbytes_lt_remain_withskip(self):
        f = io.BytesIO(b"abcdef")
        inst = self._makeOne(f)
        inst.remain = 2
        result = inst.get(1, skip=True)
        self.assertEqual(result, b"a")
        self.assertEqual(inst.remain, 1)
        self.assertEqual(f.tell(), 1)

    def test___iter__(self):
        data = b"a" * 10000
        f = io.BytesIO(data)
        inst = self._makeOne(f)
        r = b""
        for val in inst:
            r += val
        self.assertEqual(r, data)

    def test_append(self):
        inst = self._makeOne(None)
        self.assertRaises(NotImplementedError, inst.append, "a")


class TestOverflowableBuffer(unittest.TestCase):
    def _makeOne(self, overflow=10):
        from waitress.buffers import OverflowableBuffer

        buf = OverflowableBuffer(overflow)
        self.buffers_to_close.append(buf)
        return buf

    def setUp(self):
        self.buffers_to_close = []

    def tearDown(self):
        for buf in self.buffers_to_close:
            buf.close()

    def test___len__buf_is_None(self):
        inst = self._makeOne()
        self.assertEqual(len(inst), 0)

    def test___len__buf_is_not_None(self):
        inst = self._makeOne()
        inst.buf = b"abc"
        self.assertEqual(len(inst), 3)
        self.buffers_to_close.remove(inst)

    def test___nonzero__(self):
        inst = self._makeOne()
        inst.buf = b"abc"
        self.assertTrue(bool(inst))
        inst.buf = b""
        self.assertFalse(bool(inst))
        self.buffers_to_close.remove(inst)

    def test___nonzero___on_int_overflow_buffer(self):
        inst = self._makeOne()

        class int_overflow_buf(bytes):
            def __len__(self):
                # maxint + 1
                return 0x7FFFFFFFFFFFFFFF + 1

        inst.buf = int_overflow_buf()
        self.assertTrue(bool(inst))
        inst.buf = b""
        self.assertFalse(bool(inst))
        self.buffers_to_close.remove(inst)

    def test__create_buffer_large(self):
        from waitress.buffers import TempfileBasedBuffer

        inst = self._makeOne()
        inst.strbuf = b"x" * 11
        inst._create_buffer()
        self.assertIsInstance(inst.buf, TempfileBasedBuffer)
        self.assertEqual(inst.buf.get(100), b"x" * 11)
        self.assertEqual(inst.strbuf, b"")

    def test__create_buffer_small(self):
        from waitress.buffers import BytesIOBasedBuffer

        inst = self._makeOne()
        inst.strbuf = b"x" * 5
        inst._create_buffer()
        self.assertIsInstance(inst.buf, BytesIOBasedBuffer)
        self.assertEqual(inst.buf.get(100), b"x" * 5)
        self.assertEqual(inst.strbuf, b"")

    def test_append_with_len_more_than_max_int(self):
        from waitress.compat import MAXINT

        inst = self._makeOne()
        inst.overflowed = True
        buf = DummyBuffer(length=MAXINT)
        inst.buf = buf
        result = inst.append(b"x")
        # we don't want this to throw an OverflowError on Python 2 (see
        # https://github.com/Pylons/waitress/issues/47)
        self.assertIsNone(result)
        self.buffers_to_close.remove(inst)

    def test_append_buf_None_not_longer_than_srtbuf_limit(self):
        inst = self._makeOne()
        inst.strbuf = b"x" * 5
        inst.append(b"hello")
        self.assertEqual(inst.strbuf, b"xxxxxhello")

    def test_append_buf_None_longer_than_strbuf_limit(self):
        inst = self._makeOne(10000)
        inst.strbuf = b"x" * 8192
        inst.append(b"hello")
        self.assertEqual(inst.strbuf, b"")
        self.assertEqual(len(inst.buf), 8197)

    def test_append_overflow(self):
        inst = self._makeOne(10)
        inst.strbuf = b"x" * 8192
        inst.append(b"hello")
        self.assertEqual(inst.strbuf, b"")
        self.assertEqual(len(inst.buf), 8197)

    def test_append_sz_gt_overflow(self):
        from waitress.buffers import BytesIOBasedBuffer

        f = io.BytesIO(b"data")
        inst = self._makeOne(f)
        buf = BytesIOBasedBuffer()
        inst.buf = buf
        inst.overflow = 2
        inst.append(b"data2")
        self.assertEqual(f.getvalue(), b"data")
        self.assertTrue(inst.overflowed)
        self.assertNotEqual(inst.buf, buf)

    def test_get_buf_None_skip_False(self):
        inst = self._makeOne()
        inst.strbuf = b"x" * 5
        r = inst.get(5)
        self.assertEqual(r, b"xxxxx")

    def test_get_buf_None_skip_True(self):
        inst = self._makeOne()
        inst.strbuf = b"x" * 5
        r = inst.get(5, skip=True)
        self.assertIsNotNone(inst.buf)
        self.assertEqual(r, b"xxxxx")

    def test_skip_buf_None(self):
        inst = self._makeOne()
        inst.strbuf = b"data"
        inst.skip(4)
        self.assertEqual(inst.strbuf, b"")
        self.assertIsNotNone(inst.buf)

    def test_skip_buf_None_allow_prune_True(self):
        inst = self._makeOne()
        inst.strbuf = b"data"
        inst.skip(4, True)
        self.assertEqual(inst.strbuf, b"")
        self.assertIsNone(inst.buf)

    def test_prune_buf_None(self):
        inst = self._makeOne()
        inst.prune()
        self.assertEqual(inst.strbuf, b"")

    def test_prune_with_buf(self):
        inst = self._makeOne()

        class Buf:
            def prune(self):
                self.pruned = True

        inst.buf = Buf()
        inst.prune()
        self.assertTrue(inst.buf.pruned)
        self.buffers_to_close.remove(inst)

    def test_prune_with_buf_overflow(self):
        inst = self._makeOne()

        class DummyBuffer(io.BytesIO):
            def getfile(self):
                return self

            def prune(self):
                return True

            def __len__(self):
                return 5

            def close(self):
                pass

        buf = DummyBuffer(b"data")
        inst.buf = buf
        inst.overflowed = True
        inst.overflow = 10
        inst.prune()
        self.assertNotEqual(inst.buf, buf)

    def test_prune_with_buflen_more_than_max_int(self):
        from waitress.compat import MAXINT

        inst = self._makeOne()
        inst.overflowed = True
        buf = DummyBuffer(length=MAXINT + 1)
        inst.buf = buf
        result = inst.prune()
        # we don't want this to throw an OverflowError on Python 2 (see
        # https://github.com/Pylons/waitress/issues/47)
        self.assertIsNone(result)

    def test_getfile_buf_None(self):
        inst = self._makeOne()
        f = inst.getfile()
        self.assertTrue(hasattr(f, "read"))

    def test_getfile_buf_not_None(self):
        inst = self._makeOne()
        buf = io.BytesIO()
        buf.getfile = lambda *x: buf
        inst.buf = buf
        f = inst.getfile()
        self.assertEqual(f, buf)

    def test_close_nobuf(self):
        inst = self._makeOne()
        inst.buf = None
        self.assertIsNone(inst.close())  # doesnt raise
        self.buffers_to_close.remove(inst)

    def test_close_withbuf(self):
        class Buffer:
            def close(self):
                self.closed = True

        buf = Buffer()
        inst = self._makeOne()
        inst.buf = buf
        inst.close()
        self.assertTrue(buf.closed)
        self.buffers_to_close.remove(inst)


class KindaFilelike:
    def __init__(self, bytes, close=None, tellresults=None):
        self.bytes = bytes
        self.tellresults = tellresults
        if close is not None:
            self.close = lambda: close


class Filelike(KindaFilelike):
    def seek(self, v, whence=0):
        self.seeked = v

    def tell(self):
        v = self.tellresults.pop(0)
        return v


class DummyBuffer:
    def __init__(self, length=0):
        self.length = length

    def __len__(self):
        return self.length

    def append(self, s):
        self.length = self.length + len(s)

    def prune(self):
        pass

    def close(self):
        pass
