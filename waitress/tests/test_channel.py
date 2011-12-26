import unittest

class TestHTTPServerChannel(unittest.TestCase):
    def _makeOne(self, sock, addr, adj=None, map=None):
        from waitress.channel import HTTPServerChannel
        server = DummyServer()
        return HTTPServerChannel(server, sock, addr, adj=adj, map=map)

    def _makeOneWithMap(self, adj=None):
        sock = DummySock()
        map = {}
        inst = self._makeOne(sock, '127.0.0.1', adj=adj, map=map)
        return inst, sock, map

    def test_ctor(self):
        inst, _, map = self._makeOneWithMap()
        self.assertEqual(inst.addr, '127.0.0.1')
        self.assertEqual(map[100], inst)

    def test_handle_close(self):
        inst, sock, map = self._makeOneWithMap()
        def close():
            inst.closed = True
        inst.close = close
        inst.handle_close()
        self.assertEqual(inst.closed, True)

    def test_writable_async_mode_will_close(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = True
        inst.outbuf = ''
        self.assertTrue(inst.writable())

    def test_writable_async_mode_outbuf(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        inst.outbuf ='a'
        self.assertTrue(inst.writable())

    def test_writable_sync_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = False
        self.assertFalse(inst.writable())

    def test_handle_write_sync_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = False
        inst.last_activity = 0
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertEqual(inst.last_activity, 0)

    def test_handle_write_async_mode_with_outbuf(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.outbuf = DummyBuffer(b'abc')
        inst.last_activity = 0
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertNotEqual(inst.last_activity, 0)
        self.assertEqual(sock.sent, b'abc')

    def test_handle_write_async_mode_with_outbuf_raises_socketerror(self):
        import socket
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        L = []
        inst.log_info = lambda *x: L.append(x)
        inst.outbuf = DummyBuffer(b'abc', socket.error)
        inst.last_activity = 0
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertNotEqual(inst.last_activity, 0)
        self.assertEqual(sock.sent, b'')
        self.assertEqual(len(L), 1)

    def test_handle_write_async_mode_no_outbuf_will_close(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.outbuf = None
        inst.will_close = True
        inst.last_activity = 0
        result = inst.handle_write()
        self.assertEqual(result, None)
        self.assertEqual(inst.connected, False)
        self.assertEqual(sock.closed, True)
        self.assertNotEqual(inst.last_activity, 0)

    def test_readable_async_mode_not_will_close(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        self.assertEqual(inst.readable(), True)

    def test_readable_async_mode_will_close(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = True
        self.assertEqual(inst.readable(), False)

    def test_readable_sync_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = False
        self.assertEqual(inst.readable(), False)

    def test_handle_read_sync_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = False
        inst.last_activity = 0
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertEqual(inst.last_activity, 0)

    def test_handle_read_async_mode_will_close(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = True
        inst.last_activity = 0
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertEqual(inst.last_activity, 0)

    def test_handle_read_async_mode_no_error(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        inst.recv = lambda *arg: 'abc'
        L = []
        inst.received = lambda data: L.append(data)
        inst.last_activity = 0
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertNotEqual(inst.last_activity, 0)
        self.assertEqual(L, ['abc'])

    def test_handle_read_async_mode_error(self):
        import socket
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.will_close = False
        def recv(b): raise socket.error
        inst.recv = recv
        L = []
        inst.log_info = lambda *x: L.append(x)
        inst.last_activity = 0
        result = inst.handle_read()
        self.assertEqual(result, None)
        self.assertEqual(inst.last_activity, 0)
        self.assertEqual(len(L), 1)

    def test_set_sync(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.set_sync()
        self.assertEqual(inst.async_mode, False)

    def test_set_async(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = False
        inst.last_activity = 0
        inst.set_async()
        self.assertEqual(inst.async_mode, True)
        self.assertNotEqual(inst.last_activity, 0)
        self.assertTrue(inst.server.trigger_pulled)

    def test_write_empty_byte(self):
        inst, sock, map = self._makeOneWithMap()
        wrote = inst.write(b'')
        self.assertEqual(wrote, 0)

    def test_write_nonempty_byte(self):
        inst, sock, map = self._makeOneWithMap()
        wrote = inst.write(b'a')
        self.assertEqual(wrote, 1)

    def test_write_list_with_empty(self):
        inst, sock, map = self._makeOneWithMap()
        wrote = inst.write([b''])
        self.assertEqual(wrote, 0)

    def test_write_list_with_full(self):
        inst, sock, map = self._makeOneWithMap()
        wrote = inst.write([b'a', b'b'])
        self.assertEqual(wrote, 2)

    def test_write_outbuf_gt_send_bytes_has_data(self):
        from waitress.adjustments import Adjustments
        class DummyAdj(Adjustments):
            send_bytes = 10
        inst, sock, map = self._makeOneWithMap(adj=DummyAdj)
        wrote = inst.write(b'x' * 1024)
        self.assertEqual(wrote, 1024)

    def test_write_outbuf_gt_send_bytes_no_data(self):
        from waitress.adjustments import Adjustments
        class DummyAdj(Adjustments):
            send_bytes = 10
        inst, sock, map = self._makeOneWithMap(adj=DummyAdj)
        inst.outbuf.append(b'x' * 20)
        self.connected = False
        wrote = inst.write(b'')
        self.assertEqual(wrote, 0)

    def test_write_channels_accept_iterables(self):
        inst, sock, map = self._makeOneWithMap()
        self.assertEqual(inst.write(b'First'), 5)
        self.assertEqual(inst.write([b"\n", b"Second", b"\n", b"Third"]), 13)
        def count():
            yield b'\n1\n2\n3\n'
            yield b'I love to count. Ha ha ha.'
        self.assertEqual(inst.write(count()), 33)

    def test__flush_some_notconnected(self):
        inst, sock, map = self._makeOneWithMap()
        inst.outbuf = b'123'
        inst.connected = False
        result = inst._flush_some()
        self.assertEqual(result, False)

    def test__flush_some_empty_outbuf(self):
        inst, sock, map = self._makeOneWithMap()
        inst.connected = True
        result = inst._flush_some()
        self.assertEqual(result, False)

    def test__flush_some_full_outbuf_socket_returns_nonzero(self):
        inst, sock, map = self._makeOneWithMap()
        inst.connected = True
        inst.outbuf.append(b'abc')
        result = inst._flush_some()
        self.assertEqual(result, True)

    def test__flush_some_full_outbuf_socket_returns_zero(self):
        inst, sock, map = self._makeOneWithMap()
        sock.send = lambda x: False
        inst.connected = True
        inst.outbuf.append(b'abc')
        result = inst._flush_some()
        self.assertEqual(result, False)

    def test_close_when_done_async_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.connected = True
        inst.async_mode = True
        inst.outbuf.append(b'abc')
        inst.close_when_done()
        self.assertEqual(inst.will_close, True)

    def test_close_when_done_sync_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.connected = True
        inst.outbuf.append(b'abc')
        inst.async_mode = False
        inst.close_when_done()
        self.assertEqual(inst.will_close, True)
        self.assertEqual(inst.async_mode, True)
        self.assertEqual(inst.server.trigger_pulled, True)

    def test_close_async_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = True
        inst.close()
        self.assertEqual(inst.connected, False)
        self.assertEqual(sock.closed, True)

    def test_close_sync_mode(self):
        inst, sock, map = self._makeOneWithMap()
        inst.async_mode = False
        self.assertRaises(AssertionError, inst.close)

    def test_add_channel(self):
        inst, sock, map = self._makeOneWithMap()
        fileno = inst._fileno
        try:
            inst.add_channel(map)
            self.assertEqual(map[fileno], inst)
            self.assertEqual(inst.__class__.active_channels[fileno], inst)
        finally:
            inst.__class__.active_channels.pop(fileno, None)

    def test_del_channel(self):
        inst, sock, map = self._makeOneWithMap()
        fileno = inst._fileno
        try:
            inst.__class__.active_channels[fileno] = True
            inst.del_channel(map)
            self.assertEqual(map.get(fileno), None)
            self.assertEqual(inst.__class__.active_channels.get(fileno),
                             None)
        finally:
            inst.__class__.active_channels.pop(fileno, None)

    def test_check_maintenance_false(self):
        inst, sock, map = self._makeOneWithMap()
        inst.__class__.next_channel_cleanup = [10]
        result = inst.check_maintenance(5)
        self.assertEqual(result, False)

    def test_check_maintenance_true(self):
        inst, sock, map = self._makeOneWithMap()
        ncc = inst.__class__.next_channel_cleanup
        try:
            inst.__class__.next_channel_cleanup = [10]
            inst.maintenance = lambda *arg: True
            self.assertEqual(inst.check_maintenance(20), True)
            self.assertEqual(inst.__class__.next_channel_cleanup,
                             [inst.adj.cleanup_interval + 20])
        finally:
            inst.__class__.next_channel_cleanup = ncc

    def test_maintenance(self):
        inst, sock, map = self._makeOneWithMap()
        class DummyChannel(object):
            def close(self):
                self.closed = True
        zombie = DummyChannel()
        zombie.last_activity = 0
        zombie.running_tasks = False
        try:
            inst.__class__.active_channels[100] = zombie
            inst.maintenance()
            self.assertEqual(zombie.closed, True)
        finally:
            inst.__class__.active_channels.pop(100, None)

    def test_received(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        inst.received(b'GET / HTTP/1.1\n\n')
        self.assertEqual(inst.server.tasks, [inst])
        self.assertEqual(len(inst.tasks), 1)

    def test_received_preq_not_completed(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        preq = DummyParser()
        inst.proto_request = preq
        preq.completed = False
        preq.empty = True
        inst.received(b'GET / HTTP/1.1\n\n')
        self.assertEqual(inst.server.tasks, [])

    def test_received_preq_completed(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        preq = DummyParser()
        inst.proto_request = preq
        preq.completed = True
        preq.empty = True
        inst.received(b'GET / HTTP/1.1\n\n')
        self.assertEqual(inst.proto_request, None)
        self.assertEqual(inst.server.tasks, [])

    def test_received_preq_completed_n_lt_data(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        preq = DummyParser()
        inst.proto_request = preq
        preq.completed = True
        preq.empty = True
        preq.retval = 1
        inst.received(b'GET / HTTP/1.1\n\n')
        self.assertEqual(inst.proto_request, None)
        self.assertEqual(inst.server.tasks, [inst])

    def test_received_headers_finished_not_expect_continue(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        preq = DummyParser()
        inst.proto_request = preq
        preq.expect_continue = False
        preq.headers_finished = True
        preq.completed = False
        preq.empty = False
        preq.retval = 1
        inst.received(b'GET / HTTP/1.1\n\n')
        self.assertEqual(inst.proto_request, preq)
        self.assertEqual(inst.server.tasks, [])
        self.assertEqual(inst.outbuf.get(100), b'')

    def test_received_headers_finished_expect_continue(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        preq = DummyParser()
        inst.proto_request = preq
        preq.expect_continue = True
        preq.headers_finished = True
        preq.completed = False
        preq.empty = False
        preq.retval = 1
        inst.received(b'GET / HTTP/1.1\n\n')
        self.assertEqual(inst.proto_request, preq)
        self.assertEqual(inst.server.tasks, [])
        self.assertEqual(inst.outbuf.get(100), b'HTTP/1.1 100 Continue\r\n\r\n')

    def test_handle_request(self):
        req = DummyParser()
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        inst.handle_request(req)
        self.assertEqual(inst.server.tasks, [inst])
        self.assertEqual(len(inst.tasks), 1)

    def test_handle_error_reraises_SystemExit(self):
        inst, sock, map = self._makeOneWithMap()
        self.assertRaises(SystemExit,
                          inst.handle_error, (SystemExit, None, None))

    def test_handle_error_reraises_KeyboardInterrupt(self):
        inst, sock, map = self._makeOneWithMap()
        self.assertRaises(KeyboardInterrupt,
                          inst.handle_error, (KeyboardInterrupt, None, None))

    def test_handle_error_noreraise(self):
        inst, sock, map = self._makeOneWithMap()
        # compact_traceback throws an AssertionError without a traceback
        self.assertRaises(AssertionError, inst.handle_error,
                          (ValueError, ValueError('a'), None))

    def test_handle_comm_error_log(self):
        inst, sock, map = self._makeOneWithMap()
        inst.adj.log_socket_errors = True
        # compact_traceback throws an AssertionError without a traceback
        self.assertRaises(AssertionError, inst.handle_comm_error)

    def test_handle_comm_error_no(self):
        inst, sock, map = self._makeOneWithMap()
        inst.adj.log_socket_errors = False
        inst.handle_comm_error()
        self.assertEqual(inst.connected, False)
        self.assertEqual(sock.closed, True)

    def test_queue_task_no_existing_tasks_notrunning(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        task = DummyTask()
        inst.queue_task(task)
        self.assertEqual(inst.tasks, [task])
        self.assertTrue(inst.running_tasks)
        self.assertFalse(inst.async_mode)
        self.assertEqual(inst.server.tasks, [inst])

    def test_queue_task_no_existing_tasks_running(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        inst.running_tasks = True
        task = DummyTask()
        inst.queue_task(task)
        self.assertEqual(inst.tasks, [task])
        self.assertTrue(inst.async_mode)

    def test_service_no_tasks(self):
        inst, sock, map = self._makeOneWithMap()
        inst.running_tasks = True
        inst.async_mode = False
        inst.service()
        self.assertEqual(inst.running_tasks, False)
        self.assertEqual(inst.async_mode, True)

    def test_service_with_task(self):
        inst, sock, map = self._makeOneWithMap()
        task = DummyTask()
        inst.tasks = [task]
        inst.running_tasks = True
        inst.async_mode = False
        inst.service()
        self.assertEqual(inst.running_tasks, False)
        self.assertEqual(inst.async_mode, True)
        self.assertTrue(task.serviced)

    def test_service_with_task_raises(self):
        inst, sock, map = self._makeOneWithMap()
        inst.server = DummyServer()
        task = DummyTask(ValueError)
        inst.tasks = [task]
        inst.running_tasks = True
        inst.async_mode = False
        self.assertRaises(ValueError, inst.service)
        self.assertEqual(inst.running_tasks, True)
        self.assertEqual(inst.async_mode, False)
        self.assertTrue(task.serviced)
        self.assertEqual(inst.server.tasks, [inst])

    def test_cancel_no_tasks(self):
        inst, sock, map = self._makeOneWithMap()
        inst.tasks = None
        inst.async_mode = False
        inst.cancel()
        self.assertTrue(inst.async_mode)

    def test_cancel_with_tasks(self):
        inst, sock, map = self._makeOneWithMap()
        task = DummyTask()
        inst.tasks = [task]
        inst.async_mode = False
        inst.cancel()
        self.assertTrue(inst.async_mode)
        self.assertEqual(inst.tasks, [])
        self.assertEqual(task.cancelled, True)

    def test_defer(self):
        inst, sock, map = self._makeOneWithMap()
        self.assertEqual(inst.defer(), None)

class DummySock(object):
    blocking = False
    closed = False
    def __init__(self):
        self.sent = b''
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
        self.data = b''
        return data

    def skip(self, num, x):
        self.skipped = num

class DummyServer(object):
    trigger_pulled = False
    def __init__(self):
        self.tasks = []
    def addTask(self, task):
        self.tasks.append(task)
    def pull_trigger(self):
        self.trigger_pulled = True

class DummyParser(object):
    version = 1
    data = None
    completed = True
    empty = False
    headers_finished = False
    expect_continue = False
    retval = 1000
    def received(self, data):
        self.data = data
        return self.retval
    
class DummyTask(object):
    serviced = False
    cancelled = False
    def __init__(self, toraise=None):
        self.toraise = toraise
    def service(self):
        self.serviced = True
        if self.toraise:
            raise self.toraise
    def cancel(self):
        self.cancelled = True
