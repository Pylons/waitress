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
        
