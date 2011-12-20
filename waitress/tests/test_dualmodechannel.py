import unittest

class TestDualModeChannel(unittest.TestCase):
    def _makeOne(self, conn, addr, adj=None, map=None):
        from waitress.dualmodechannel import DualModeChannel
        return DualModeChannel(conn, addr, adj=adj, map=map)

    def _makeOneWithMap(self, adj=None):
        conn = DummyConn()
        map = {}
        inst = self._makeOne(conn, '127.0.0.1', adj=adj, map=map)
        return inst, conn, map

    def test_ctor(self):
        inst, _, map = self._makeOneWithMap()
        self.assertEqual(inst.addr, '127.0.0.1')
        self.assertEqual(map[100], inst)

    def test_handle_close(self):
        inst, conn, map = self._makeOneWithMap()
        def close():
            inst.closed = True
        inst.close = close
        inst.handle_close()
        self.assertEqual(inst.closed, True)

    def test_writable_async_mode_will_close(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = True
        inst.outbuf = ''
        self.assertTrue(inst.writable())

    def test_writable_async_mode_outbuf(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        inst.outbuf ='a'
        self.assertTrue(inst.writable())

    def test_writable_sync_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = False
        self.assertFalse(inst.writable())

    def test_handle_write_sync_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = False
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertEqual(inst.last_activity, None)

    def test_handle_write_async_mode_with_outbuf(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.outbuf = DummyBuffer('abc')
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertTrue(inst.last_activity)
        self.assertEqual(conn.sent, 'abc')

    def test_handle_write_async_mode_with_outbuf_raises_socketerror(self):
        import socket
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        L = []
        inst.log_info = lambda *x: L.append(x)
        inst.outbuf = DummyBuffer('abc', socket.error)
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertTrue(inst.last_activity)
        self.assertEqual(conn.sent, '')
        self.assertEqual(len(L), 1)

    def test_handle_write_async_mode_no_outbuf_will_close(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.outbuf = None
        inst.will_close = True
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertEqual(inst.connected, False)
        self.assertEqual(conn.closed, True)
        self.assertTrue(inst.last_activity)

    def test_readable_async_mode_not_will_close(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        self.assertEqual(inst.readable(), True)

    def test_readable_async_mode_will_close(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = True
        self.assertEqual(inst.readable(), False)

    def test_readable_sync_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = False
        self.assertEqual(inst.readable(), False)

    def test_handle_read_sync_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = False
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertFalse(inst.last_activity)

    def test_handle_read_async_mode_will_close(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = True
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertFalse(inst.last_activity)

    def test_handle_read_async_mode_no_error(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        inst.recv = lambda *arg: 'abc'
        L = []
        inst.received = lambda data: L.append(data)
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertTrue(inst.last_activity)
        self.assertEqual(L, ['abc'])

    def test_handle_read_async_mode_error(self):
        import socket
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        def recv(b): raise socket.error
        inst.recv = recv
        L = []
        inst.log_info = lambda *x: L.append(x)
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertFalse(inst.last_activity)
        self.assertEqual(len(L), 1)

    def test_received(self):
        inst, conn, map = self._makeOneWithMap()
        self.assertEqual(inst.received('a'), None)

    def test_set_sync(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.set_sync()
        self.assertEqual(inst.async_mode, False)

    def test_set_async(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = False
        inst.trigger = DummyTrigger()
        inst.set_async()
        self.assertEqual(inst.async_mode, True)
        self.assertTrue(inst.last_activity)
        self.assertTrue(inst.trigger.pulled)

    def test_write_empty_byte(self):
        inst, conn, map = self._makeOneWithMap()
        wrote = inst.write('')
        self.assertEqual(wrote, 0)

    def test_write_nonempty_byte(self):
        inst, conn, map = self._makeOneWithMap()
        wrote = inst.write('a')
        self.assertEqual(wrote, 1)

    def test_write_list_with_empty(self):
        inst, conn, map = self._makeOneWithMap()
        wrote = inst.write([''])
        self.assertEqual(wrote, 0)

    def test_write_list_with_full(self):
        inst, conn, map = self._makeOneWithMap()
        wrote = inst.write(['a', 'b'])
        self.assertEqual(wrote, 2)

    def test_write_outbuf_gt_send_bytes_has_data(self):
        from waitress.adjustments import Adjustments
        class DummyAdj(Adjustments):
            send_bytes = 10
        inst, conn, map = self._makeOneWithMap(adj=DummyAdj)
        wrote = inst.write('x' * 1024)
        self.assertEqual(wrote, 1024)

    def test_write_outbuf_gt_send_bytes_no_data(self):
        from waitress.adjustments import Adjustments
        class DummyAdj(Adjustments):
            send_bytes = 10
        inst, conn, map = self._makeOneWithMap(adj=DummyAdj)
        inst.outbuf.append('x' * 20)
        self.connected = False
        wrote = inst.write('')
        self.assertEqual(wrote, 0)

    def test_pull_trigger(self):
        inst, conn, map = self._makeOneWithMap()
        trigger = DummyTrigger()
        inst.trigger = trigger
        inst.pull_trigger()
        self.assertEqual(trigger.pulled, True)

    def test__flush_some_notconnected(self):
        inst, conn, map = self._makeOneWithMap()
        inst.outbuf = '123'
        inst.connected = False
        result = inst._flush_some()
        self.assertEqual(result, False)

    def test__flush_some_empty_outbuf(self):
        inst, conn, map = self._makeOneWithMap()
        inst.connected = True
        result = inst._flush_some()
        self.assertEqual(result, False)

    def test__flush_some_full_outbuf_socket_returns_nonzero(self):
        inst, conn, map = self._makeOneWithMap()
        inst.connected = True
        inst.outbuf.append('abc')
        result = inst._flush_some()
        self.assertEqual(result, True)

    def test__flush_some_full_outbuf_socket_returns_zero(self):
        inst, conn, map = self._makeOneWithMap()
        conn.send = lambda x: False
        inst.connected = True
        inst.outbuf.append('abc')
        result = inst._flush_some()
        self.assertEqual(result, False)

    def test_close_when_done_async_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.connected = True
        inst.async_mode = True
        inst.outbuf.append('abc')
        inst.close_when_done()
        self.assertEqual(inst.will_close, True)

    def test_close_when_done_sync_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.connected = True
        inst.outbuf.append('abc')
        inst.async_mode = False
        inst.trigger = DummyTrigger()
        inst.close_when_done()
        self.assertEqual(inst.will_close, True)
        self.assertEqual(inst.async_mode, True)
        self.assertEqual(inst.trigger.pulled, True)

    def test_close_async_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.close()
        self.assertEqual(inst.connected, False)
        self.assertEqual(conn.closed, True)

    def test_close_sync_mode(self):
        inst, conn, map = self._makeOneWithMap()
        inst.async_mode = False
        self.assertRaises(AssertionError, inst.close)

class DummyConn(object):
    blocking = False
    closed = False
    def __init__(self):
        self.sent = ''
    def setblocking(self, *arg):
        self.blocking = True
    def fileno(self):
        return 100
    def getpeername(self):
        return '127.0.0.1'
    def close(self):
        self.closed = True
    def send(self, data):
        self.sent += data
        return len(data)

class DummyBuffer(object):
    def __init__(self, data, toraise=None):
        self.data = data
        self.toraise = toraise

    def get(self, *arg):
        if self.toraise:
            raise self.toraise
        data = self.data
        self.data = ''
        return data

    def skip(self, num, x):
        self.skipped = num

class DummyTrigger(object):
    pulled = False
    def pull_trigger(self):
        self.pulled = True
