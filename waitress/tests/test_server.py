import errno
import socket
import unittest

class TestHTTPServer(unittest.TestCase):
    def _makeOne(self, ip, port, task_dispatcher=None, adj=None, start=True,
                 hit_log=None, verbose=False, map=None, logger=None, sock=None):
        from waitress.server import HTTPServer
        class TestServer(HTTPServer):
            def bind(self, (ip, port)):
                pass
        return TestServer(
            ip,
            port,
            task_dispatcher=task_dispatcher,
            adj=adj,
            start=start,
            hit_log=hit_log,
            verbose=verbose,
            map=map,
            logger=logger,
            sock=sock)
    
    def _makeOneWithMap(self, adj=None, start=True, verbose=False,
                        ip='127.0.0.1', port=62122):
        sock = DummySock()
        task_dispatcher = DummyTaskDispatcher()
        map = {}
        logger = DummyLogger()
        return self._makeOne(ip, port, task_dispatcher=task_dispatcher,
                             start=start, verbose=verbose, map=map,
                             logger=logger, sock=sock)

    def test_ctor_start_true_verbose(self):
        inst = self._makeOneWithMap(verbose=True, start=True)
        self.assertEqual(len(inst.logger.msgs), 2)

    def test_ctor_start_false(self):
        inst = self._makeOneWithMap(verbose=True, start=False)
        self.assertEqual(len(inst.logger.msgs), 1)

    def test_log(self):
        inst = self._makeOneWithMap(verbose=True, start=False)
        inst.logger = DummyLogger()
        inst.log('msg')
        self.assertEqual(len(inst.logger.msgs), 1)

    def test_computeServerName_empty(self):
        inst = self._makeOneWithMap(verbose=True, start=False)
        inst.logger = DummyLogger()
        result = inst.computeServerName('')
        self.failUnless(result)
        self.assertEqual(len(inst.logger.msgs), 0)

    def test_computeServerName_with_ip(self):
        inst = self._makeOneWithMap(verbose=True, start=False)
        inst.logger = DummyLogger()
        result = inst.computeServerName('127.0.0.1')
        self.failUnless(result)
        self.assertEqual(len(inst.logger.msgs), 1)

    def test_computeServerName_with_hostname(self):
        inst = self._makeOneWithMap(verbose=True, start=False)
        inst.logger = DummyLogger()
        result = inst.computeServerName('fred.flintstone.com')
        self.assertEqual(result, 'fred.flintstone.com')
        self.assertEqual(len(inst.logger.msgs), 0)

    def test_addTask_with_task_dispatcher(self):
        task = DummyTask()
        inst = self._makeOneWithMap()
        inst.addTask(task)
        self.assertEqual(inst.task_dispatcher.tasks, [task])
        self.assertFalse(task.serviced)

    def test_addTask_with_task_dispatcher_None(self):
        task = DummyTask()
        inst = self._makeOneWithMap()
        inst.task_dispatcher = None
        inst.addTask(task)
        self.assertTrue(task.serviced)

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
        inst.logger = DummyLogger()
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, False)
        self.assertEqual(len(inst.logger.msgs), 1)

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
    def service(self):
        self.serviced = True

class DummyLogger(object):
    def __init__(self):
        self.msgs = []
    def log(self, level, msg):
        self.msgs.append(msg)
    def info(self, msg):
        self.msgs.append(msg)

class DummyAdj:
    connection_limit = 1
    log_socket_errors = True
    socket_options = [('level', 'optname', 'value')]

