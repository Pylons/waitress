import unittest
import StringIO

class TestThreadedTaskDispatcher(unittest.TestCase):
    def _makeOne(self):
        from waitress.task import ThreadedTaskDispatcher
        return ThreadedTaskDispatcher()

    def test_handlerThread_task_is_None(self):
        inst = self._makeOne()
        inst.threads[0] = True
        inst.queue.put(None)
        inst.handlerThread(0)
        self.assertEqual(inst.stop_count, -1)
        self.assertEqual(inst.threads, {})

    def test_handlerThread_task_raises(self):
        from waitress.task import JustTesting
        inst = self._makeOne()
        inst.threads[0] = True
        inst.stderr = StringIO.StringIO()
        task = DummyTask(JustTesting)
        inst.queue.put(task)
        inst.handlerThread(0)
        self.assertEqual(inst.stop_count, -1)
        self.assertEqual(inst.threads, {})
        self.assertTrue(inst.stderr.getvalue())

    def test_setThread_count_increase(self):
        inst = self._makeOne()
        L = []
        inst.start_new_thread = lambda *x: L.append(x)
        inst.setThreadCount(1)
        self.assertEqual(L, [(inst.handlerThread, (0,))])

    def test_setThread_count_increase_with_existing(self):
        inst = self._makeOne()
        L = []
        inst.threads = {0:1}
        inst.start_new_thread = lambda *x: L.append(x)
        inst.setThreadCount(2)
        self.assertEqual(L, [(inst.handlerThread, (1,))])

    def test_setThread_count_decrease(self):
        inst = self._makeOne()
        inst.threads = {'a':1, 'b':2}
        inst.setThreadCount(1)
        self.assertEqual(inst.queue.qsize(), 1)
        self.assertEqual(inst.queue.get(), None)

    def test_setThread_count_same(self):
        inst = self._makeOne()
        L = []
        inst.start_new_thread = lambda *x: L.append(x)
        inst.threads = {0:1}
        inst.setThreadCount(1)
        self.assertEqual(L, [])

    def test_addTask(self):
        task = DummyTask()
        inst = self._makeOne()
        inst.addTask(task)
        self.assertEqual(inst.queue.qsize(), 1)
        self.assertTrue(task.deferred)

    def test_addTask_defer_raises(self):
        task = DummyTask(ValueError)
        inst = self._makeOne()
        self.assertRaises(ValueError, inst.addTask, task)
        self.assertEqual(inst.queue.qsize(), 0)
        self.assertTrue(task.deferred)
        self.assertTrue(task.cancelled)

    def test_shutdown_one_thread(self):
        inst = self._makeOne()
        inst.threads[0] = 1
        inst.stderr = StringIO.StringIO()
        task = DummyTask()
        inst.queue.put(task)
        self.assertEqual(inst.shutdown(timeout=.01), True)
        self.assertEqual(inst.stderr.getvalue(), '1 thread(s) still running')
        self.assertEqual(task.cancelled, True)

    def test_shutdown_no_threads(self):
        inst = self._makeOne()
        self.assertEqual(inst.shutdown(timeout=.01), True)

    def test_shutdown_no_cancel_pending(self):
        inst = self._makeOne()
        self.assertEqual(inst.shutdown(cancel_pending=False, timeout=.01),
                         False)

class TestHTTPTask(unittest.TestCase):
    def _makeOne(self, channel=None, request_data=None):
        if channel is None:
            channel = DummyChannel()
        if request_data is None:
            request_data = DummyParser()
        from waitress.task import HTTPTask
        return HTTPTask(channel, request_data)

    def test_service(self):
        inst = self._makeOne()
        inst.service()
        self.assertTrue(inst.start_time)
        self.assertTrue(inst.channel.closed_when_done)
        self.assertTrue(inst.channel.written)
        self.assertEqual(inst.channel.server.executed, [inst])

    def test_service_server_raises_socket_error(self):
        import socket
        server = DummyServer(socket.error)
        channel = DummyChannel(server)
        inst = self._makeOne(channel=channel)
        self.assertRaises(socket.error, inst.service)
        self.assertTrue(inst.start_time)
        self.assertTrue(inst.channel.closed_when_done)
        self.assertFalse(inst.channel.written)

    def test_cancel(self):
        inst = self._makeOne()
        inst.cancel()
        self.assertTrue(inst.channel.closed_when_done)

    def test_defer(self):
        inst = self._makeOne()
        self.assertEqual(inst.defer(), None)

    def test_setResponseStatus(self):
        inst = self._makeOne()
        inst.setResponseStatus('one', 'two')
        self.assertEqual(inst.status, 'one')
        self.assertEqual(inst.reason, 'two')

    def test_appendResponseHeaders(self):
        inst = self._makeOne()
        inst.appendResponseHeaders([('a', '1')])
        self.assertEqual(inst.accumulated_headers, [('a', '1')])

class DummyTask(object):
    serviced = False
    deferred = False
    cancelled = False
    def __init__(self, toraise=None):
        self.toraise = toraise

    def service(self):
        self.serviced = True
        if self.toraise:
            raise self.toraise

    def defer(self):
        self.deferred = True
        if self.toraise:
            raise self.toraise

    def cancel(self):
        self.cancelled = True

class DummyServer(object):
    SERVER_IDENT = 'hithere'
    def __init__(self, toraise=None):
        self.toraise = toraise
        self.executed = []
    def executeRequest(self, task):
        self.executed.append(task)
        if self.toraise:
            raise self.toraise

class DummyAdj(object):
    log_socket_errors = True

class DummyChannel(object):
    closed_when_done = False
    adj = DummyAdj()
    def __init__(self, server=None):
        if server is None:
            server = DummyServer()
        self.server = server
        self.written = ''
    def close_when_done(self):
        self.closed_when_done = True
    def write(self, data):
        self.written += data

class DummyParser(object):
    version = '1.0'
    def __init__(self):
        self.headers = {}
