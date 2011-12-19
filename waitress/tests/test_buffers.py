import unittest
import StringIO

class TestFileBasedBuffer(unittest.TestCase):
    def _makeOne(self, file=None, from_buffer=None):
        from waitress.buffers import FileBasedBuffer
        return FileBasedBuffer(file, from_buffer=from_buffer)
        
    def test_ctor_from_buffer_None(self):
        inst = self._makeOne('file')
        self.assertEqual(inst.file, 'file')
        
    def test_ctor_from_buffer(self):
        from_buffer = StringIO.StringIO('data')
        from_buffer.getfile = lambda *x: from_buffer
        f = StringIO.StringIO()
        inst = self._makeOne(f, from_buffer)
        self.assertEqual(inst.file, f)
        del from_buffer.getfile
        self.assertEqual(inst.remain, 4)

    def test___len__(self):
        inst = self._makeOne()
        inst.remain = 10
        self.assertEqual(len(inst), 10)

    def test_append(self):
        f = StringIO.StringIO('data')
        inst = self._makeOne(f)
        inst.append('data2')
        self.assertEqual(f.getvalue(), 'datadata2')
        self.assertEqual(inst.remain, 5)
        
    def test_get_skip_true(self):
        f = StringIO.StringIO('data')
        inst = self._makeOne(f)
        result = inst.get(100, skip=True)
        self.assertEqual(result, 'data')
        self.assertEqual(inst.remain, -4)
        
    def test_get_skip_false(self):
        f = StringIO.StringIO('data')
        inst = self._makeOne(f)
        result = inst.get(100, skip=False)
        self.assertEqual(result, 'data')
        self.assertEqual(inst.remain, 0)

    def test_get_skip_bytes_less_than_zero(self):
        f = StringIO.StringIO('data')
        inst = self._makeOne(f)
        result = inst.get(-1, skip=False)
        self.assertEqual(result, 'data')
        self.assertEqual(inst.remain, 0)

    def test_skip_remain_gt_bytes(self):
        f = StringIO.StringIO('d')
        inst = self._makeOne(f)
        inst.remain = 1
        inst.skip(1)
        self.assertEqual(inst.remain, 0)

    def test_skip_remain_lt_bytes(self):
        f = StringIO.StringIO('d')
        inst = self._makeOne(f)
        inst.remain = 1
        self.assertRaises(ValueError, inst.skip, 2)

    def test_newfile(self):
        inst = self._makeOne()
        self.assertRaises(NotImplementedError, inst.newfile)

    def test_prune_remain_notzero(self):
        f = StringIO.StringIO('d')
        inst = self._makeOne(f)
        inst.remain = 1
        nf = StringIO.StringIO()
        inst.newfile = lambda *x: nf
        inst.prune()
        self.assertTrue(inst.file is not f)
        self.assertEqual(nf.getvalue(), 'd')
        
    def test_prune_remain_zero_tell_notzero(self):
        f = StringIO.StringIO('d')
        inst = self._makeOne(f)
        nf = StringIO.StringIO('d')
        inst.newfile = lambda *x: nf
        inst.remain = 0
        inst.prune()
        self.assertTrue(inst.file is not f)
        self.assertEqual(nf.getvalue(), 'd')
        
    def test_prune_remain_zero_tell_zero(self):
        f = StringIO.StringIO()
        inst = self._makeOne(f)
        inst.remain = 0
        inst.prune()
        self.assertTrue(inst.file is f)

class TestTempfileBasedBuffer(unittest.TestCase):
    def _makeOne(self, from_buffer=None):
        from waitress.buffers import TempfileBasedBuffer
        return TempfileBasedBuffer(from_buffer=from_buffer)

    def test_newfile(self):
        inst = self._makeOne()
        r = inst.newfile()
        self.assertTrue(isinstance(r, file))

class TestStringIOBasedBuffer(unittest.TestCase):
    def _makeOne(self, from_buffer=None):
        from waitress.buffers import StringIOBasedBuffer
        return StringIOBasedBuffer(from_buffer=from_buffer)

    def test_ctor_from_buffer_not_None(self):
        f = StringIO.StringIO()
        f.getfile = lambda *x: f
        inst = self._makeOne(f)
        self.assertTrue(hasattr(inst.file, 'read'))

    def test_ctor_from_buffer_None(self):
        inst = self._makeOne()
        self.assertTrue(hasattr(inst.file, 'read'))

    def test_newfile(self):
        inst = self._makeOne()
        r = inst.newfile()
        self.assertTrue(hasattr(r, 'read'))

class TestOverflowableBuffer(unittest.TestCase):
    def _makeOne(self, overflow=10):
        from waitress.buffers import OverflowableBuffer
        return OverflowableBuffer(overflow)

    def test___len__buf_is_None(self):
        inst = self._makeOne()
        self.assertEqual(len(inst), 0)

    def test___len__buf_is_not_None(self):
        inst = self._makeOne()
        inst.buf = 'abc'
        self.assertEqual(len(inst), 3)
        
    def test__create_buffer_large(self):
        from waitress.buffers import TempfileBasedBuffer
        inst = self._makeOne()
        inst.strbuf = 'x' * 11
        inst._create_buffer()
        self.assertEqual(inst.buf.__class__, TempfileBasedBuffer)
        self.assertEqual(inst.buf.get(100), 'x' * 11)
        self.assertEqual(inst.strbuf, '')
        
    def test__create_buffer_small(self):
        from waitress.buffers import StringIOBasedBuffer
        inst = self._makeOne()
        inst.strbuf = 'x' * 5
        inst._create_buffer()
        self.assertEqual(inst.buf.__class__, StringIOBasedBuffer)
        self.assertEqual(inst.buf.get(100), 'x' * 5)
        self.assertEqual(inst.strbuf, '')

    def test_append_buf_None_not_longer_than_srtfbuf_limit(self):
        inst = self._makeOne()
        inst.strbuf = 'x' * 5
        inst.append('hello')
        self.assertEqual(inst.strbuf, 'xxxxxhello')
        
    def test_append_buf_None_longer_than_strbuf_limit(self):
        inst = self._makeOne(10000)
        inst.strbuf = 'x' * 8192
        inst.append('hello')
        self.assertEqual(inst.strbuf, '')
        self.assertEqual(len(inst.buf), 8197)
        
    def test_append_overflow(self):
        inst = self._makeOne(10)
        inst.strbuf = 'x' * 8192
        inst.append('hello')
        self.assertEqual(inst.strbuf, '')
        self.assertEqual(len(inst.buf), 8197)
        
    def test_get_buf_None_skip_False(self):
        inst = self._makeOne()
        inst.strbuf = 'x' * 5
        r = inst.get(5)
        self.assertEqual(r, 'xxxxx')
        
    def test_get_buf_None_skip_True(self):
        inst = self._makeOne()
        inst.strbuf = 'x' * 5
        r = inst.get(5, skip=True)
        self.assertFalse(inst.buf is None)
        self.assertEqual(r, 'xxxxx')

    def test_skip_buf_None(self):
        inst = self._makeOne()
        inst.strbuf = 'data'
        inst.skip(4)
        self.assertEqual(inst.strbuf, '')
        self.assertNotEqual(inst.buf, None)

    def test_skip_buf_None_allow_prune_True(self):
        inst = self._makeOne()
        inst.strbuf = 'data'
        inst.skip(4, True)
        self.assertEqual(inst.strbuf, '')
        self.assertEqual(inst.buf, None)

    def test_prune_buf_None(self):
        inst = self._makeOne()
        inst.prune()
        self.assertEqual(inst.strbuf, '')

    def test_prune_with_buf(self):
        inst = self._makeOne()
        class Buf(object):
            def prune(self):
                self.pruned = True
        inst.buf = Buf()
        inst.prune()
        self.assertEqual(inst.buf.pruned, True)
        
    def test_prune_with_buf_overflow(self):
        inst = self._makeOne()
        buf = StringIO.StringIO('data')
        buf.getfile = lambda *x: buf
        buf.prune = lambda *x: True
        buf.__len__ = lambda *x: 5
        inst.buf = buf
        inst.overflowed = True
        inst.overflow = 10
        inst.prune()
        self.assertNotEqual(inst.buf, buf)

    def test_getfile_buf_None(self):
        inst = self._makeOne()
        f = inst.getfile()
        self.assertTrue(hasattr(f, 'read'))
        
    def test_getfile_buf_not_None(self):
        inst = self._makeOne()
        buf = StringIO.StringIO()
        buf.getfile = lambda *x: buf
        inst.buf = buf
        f = inst.getfile()
        self.assertEqual(f, buf)
        
        
        
