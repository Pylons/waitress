import unittest

class TestFixedStreamReceiver(unittest.TestCase):
    def _makeOne(self, buf, cl):
        from waitress.fixedstreamreceiver import FixedStreamReceiver
        return FixedStreamReceiver(buf, cl)

    def test_received_remain_lt_1(self):
        buf = DummyBuffer()
        inst = self._makeOne(0, buf)
        result = inst.received('a')
        self.assertEqual(result, 0)
        self.assertEqual(inst.completed, True)

    def test_received_remain_lte_datalen(self):
        buf = DummyBuffer()
        inst = self._makeOne(1, buf)
        result = inst.received('aa')
        self.assertEqual(result, 1)
        self.assertEqual(inst.completed, True)
        self.assertEqual(inst.completed, 1)
        self.assertEqual(inst.remain, 0)
        self.assertEqual(buf.data, ['a'])

    def test_received_remain_gt_datalen(self):
        buf = DummyBuffer()
        inst = self._makeOne(10, buf)
        result = inst.received('aa')
        self.assertEqual(result, 2)
        self.assertEqual(inst.completed, False)
        self.assertEqual(inst.remain, 8)
        self.assertEqual(buf.data, ['aa'])

    def test_getfile(self):
        buf = DummyBuffer()
        inst = self._makeOne(10, buf)
        self.assertEqual(inst.getfile(), buf)

class DummyBuffer(object):
    def __init__(self):
        self.data = []
    def append(self, s):
        self.data.append(s)
    def getfile(self):
        return self
    
