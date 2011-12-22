import errno
import socket
import unittest

class TestWSGIHTTPServer(unittest.TestCase):
    def _makeOne(self, application, ip, port, task_dispatcher=None, adj=None,
                 start=True, map=None, sock=None):
        from waitress.server import WSGIHTTPServer
        class TestServer(WSGIHTTPServer):
            def bind(self, (ip, port)):
                pass
        return TestServer(
            application,
            ip,
            port,
            task_dispatcher=task_dispatcher,
            adj=adj,
            start=start,
            map=map,
            sock=sock)
    
    def _makeOneWithMap(self, adj=None, start=True, ip='127.0.0.1', port=62122,
                        app=None):
        sock = DummySock()
        task_dispatcher = DummyTaskDispatcher()
        map = {}
        return self._makeOne(app, ip, port, task_dispatcher=task_dispatcher,
                             start=start, map=map, sock=sock)

    def test_ctor_start_true(self):
        inst = self._makeOneWithMap(start=True)
        self.assertEqual(inst.accepting, True)
        self.assertEqual(inst.socket.listened, 1024)

    def test_ctor_start_false(self):
        inst = self._makeOneWithMap(start=False)
        self.assertEqual(inst.accepting, False)

    def test_computeServerName_empty(self):
        inst = self._makeOneWithMap(start=False)
        result = inst.computeServerName('')
        self.failUnless(result)

    def test_computeServerName_with_ip(self):
        inst = self._makeOneWithMap(start=False)
        result = inst.computeServerName('127.0.0.1')
        self.failUnless(result)

    def test_computeServerName_with_hostname(self):
        inst = self._makeOneWithMap(start=False)
        result = inst.computeServerName('fred.flintstone.com')
        self.assertEqual(result, 'fred.flintstone.com')

    def test_addTask(self):
        task = DummyTask()
        inst = self._makeOneWithMap()
        inst.addTask(task)
        self.assertEqual(inst.task_dispatcher.tasks, [task])
        self.assertFalse(task.serviced)

    def test_readable_not_accepting(self):
        inst = self._makeOneWithMap()
        inst.accepting = False
        self.assertFalse(inst.readable())
        
    def test_readable_maplen_gt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {'a':1, 'b':2}
        self.assertFalse(inst.readable())

    def test_readable_maplen_lt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {}
        self.assertTrue(inst.readable())

    def test_writable(self):
        inst = self._makeOneWithMap()
        self.assertFalse(inst.writable())
        
    def test_handle_read(self):
        inst = self._makeOneWithMap()
        self.assertEqual(inst.handle_read(), None)

    def test_handle_connect(self):
        inst = self._makeOneWithMap()
        self.assertEqual(inst.handle_connect(), None)

    def test_handle_accept_wouldblock_socket_error(self):
        inst = self._makeOneWithMap()
        ewouldblock = socket.error(errno.EWOULDBLOCK)
        inst.socket = DummySock(toraise=ewouldblock)
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, False)

    def test_handle_accept_other_socket_error(self):
        inst = self._makeOneWithMap()
        eaborted = socket.error(errno.ECONNABORTED)
        inst.socket = DummySock(toraise=eaborted)
        inst.adj = DummyAdj
        L = []
        def log_info(msg, type):
            L.append(msg)
        inst.log_info = log_info
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, False)
        self.assertEqual(len(L), 1)

    def test_handle_accept_noerror(self):
        inst = self._makeOneWithMap()
        innersock = DummySock()
        inst.socket = DummySock(acceptresult=(innersock, None))
        inst.adj = DummyAdj
        L = []
        inst.channel_class = lambda *arg: L.append(arg)
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, True)
        self.assertEqual(innersock.opts, [('level', 'optname', 'value')])
        self.assertEqual(L, [(inst, innersock, None, inst.adj)])

class DummySock(object):
    accepted = False
    blocking = False
    def __init__(self, toraise=None, acceptresult=(None, None)):
        self.toraise = toraise
        self.acceptresult = acceptresult
        self.opts = []
    def accept(self):
        if self.toraise:
            raise self.toraise
        self.accepted = True
        return self.acceptresult
    def setblocking(self, x):
        self.blocking = True
    def fileno(self):
        return 10
    def getpeername(self):
        return '127.0.0.1'
    def setsockopt(self, *arg):
        self.opts.append(arg)
    def getsockopt(self, *arg):
        return 1
    def listen(self, num):
        self.listened = num

class DummyTaskDispatcher(object):
    def __init__(self):
        self.tasks = []
    def addTask(self, task):
        self.tasks.append(task)

class DummyTask(object):
    serviced = False
    def service(self): # pragma: no cover
        self.serviced = True

class DummyAdj:
    connection_limit = 1
    log_socket_errors = True
    socket_options = [('level', 'optname', 'value')]

