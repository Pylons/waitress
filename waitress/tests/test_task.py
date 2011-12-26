import unittest

class TestThreadedTaskDispatcher(unittest.TestCase):
    def _makeOne(self):
        from waitress.task import ThreadedTaskDispatcher
        return ThreadedTaskDispatcher()

    def test_handler_thread_task_is_None(self):
        inst = self._makeOne()
        inst.threads[0] = True
        inst.queue.put(None)
        inst.handler_thread(0)
        self.assertEqual(inst.stop_count, -1)
        self.assertEqual(inst.threads, {})

    def test_handler_thread_task_raises(self):
        from waitress.compat import NativeIO
        from waitress.task import JustTesting
        inst = self._makeOne()
        inst.threads[0] = True
        inst.stderr = NativeIO()
        task = DummyTask(JustTesting)
        inst.queue.put(task)
        inst.handler_thread(0)
        self.assertEqual(inst.stop_count, -1)
        self.assertEqual(inst.threads, {})
        self.assertTrue(inst.stderr.getvalue())

    def test_set_thread_count_increase(self):
        inst = self._makeOne()
        L = []
        inst.start_new_thread = lambda *x: L.append(x)
        inst.set_thread_count(1)
        self.assertEqual(L, [(inst.handler_thread, (0,))])

    def test_set_thread_count_increase_with_existing(self):
        inst = self._makeOne()
        L = []
        inst.threads = {0:1}
        inst.start_new_thread = lambda *x: L.append(x)
        inst.set_thread_count(2)
        self.assertEqual(L, [(inst.handler_thread, (1,))])

    def test_set_thread_count_decrease(self):
        inst = self._makeOne()
        inst.threads = {'a':1, 'b':2}
        inst.set_thread_count(1)
        self.assertEqual(inst.queue.qsize(), 1)
        self.assertEqual(inst.queue.get(), None)

    def test_set_thread_count_same(self):
        inst = self._makeOne()
        L = []
        inst.start_new_thread = lambda *x: L.append(x)
        inst.threads = {0:1}
        inst.set_thread_count(1)
        self.assertEqual(L, [])

    def test_add_task(self):
        task = DummyTask()
        inst = self._makeOne()
        inst.add_task(task)
        self.assertEqual(inst.queue.qsize(), 1)
        self.assertTrue(task.deferred)

    def test_add_task_defer_raises(self):
        task = DummyTask(ValueError)
        inst = self._makeOne()
        self.assertRaises(ValueError, inst.add_task, task)
        self.assertEqual(inst.queue.qsize(), 0)
        self.assertTrue(task.deferred)
        self.assertTrue(task.cancelled)

    def test_shutdown_one_thread(self):
        from waitress.compat import NativeIO
        inst = self._makeOne()
        inst.threads[0] = 1
        inst.stderr = NativeIO()
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
        def execute():
            inst.executed = True
        inst.execute = execute
        inst.start_response_called = True
        inst.service()
        self.assertTrue(inst.start_time)
        self.assertTrue(inst.channel.closed_when_done)
        self.assertTrue(inst.channel.written)
        self.assertEqual(inst.executed, True)

    def test_service_server_raises_socket_error(self):
        import socket
        inst = self._makeOne()
        def execute():
            raise socket.error
        inst.execute = execute
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

    def test_build_response_header_v10_keepalive_no_content_length(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.request_data.headers['CONNECTION'] = 'keep-alive'
        inst.version = '1.0'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/1.0 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')
        self.assertEqual(inst.close_on_finish, True)
        self.assertTrue(('Connection', 'close') in inst.response_headers)

    def test_build_response_header_v10_keepalive_with_content_length(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.request_data.headers['CONNECTION'] = 'keep-alive'
        inst.response_headers = [('Content-Length', '10')]
        inst.version = '1.0'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b'HTTP/1.0 200 OK')
        self.assertEqual(lines[1], b'Connection: Keep-Alive')
        self.assertEqual(lines[2], b'Content-Length: 10')
        self.assertTrue(lines[3].startswith(b'Date:'))
        self.assertEqual(lines[4], b'Server: hithere')
        self.assertEqual(inst.close_on_finish, False)

    def test_build_response_header_v11_connection_closed_by_app(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.version = '1.1'
        inst.response_headers = [('Connection', 'close')]
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/1.1 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')
        self.assertTrue(('Connection', 'close') in inst.response_headers)
        self.assertEqual(inst.close_on_finish, True)

    def test_build_response_header_v11_connection_closed_by_client(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.version = '1.1'
        inst.request_data.headers['CONNECTION'] = 'close'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/1.1 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')
        self.assertTrue(('Connection', 'close') in inst.response_headers)
        self.assertEqual(inst.close_on_finish, True)

    def test_build_response_header_v11_connection_keepalive_by_client(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.request_data.headers['CONNECTION'] = 'keep-alive'
        inst.version = '1.1'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/1.1 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')
        self.assertTrue(('Connection', 'close') in inst.response_headers)
        self.assertEqual(inst.close_on_finish, True)

    def test_build_response_header_v11_transfer_encoding_nonchunked(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.response_headers = [('Transfer-Encoding', 'notchunked')]
        inst.version = '1.1'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b'HTTP/1.1 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')
        self.assertEqual(lines[4], b'Transfer-Encoding: notchunked')
        self.assertTrue(('Connection', 'close') in inst.response_headers)
        self.assertEqual(inst.close_on_finish, True)

    def test_build_response_header_v11_transfer_encoding_chunked(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.response_headers = [('Transfer-Encoding', 'chunked')]
        inst.version = '1.1'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/1.1 200 OK')
        self.assertTrue(lines[1].startswith(b'Date:'))
        self.assertEqual(lines[2], b'Server: hithere')
        self.assertEqual(lines[3], b'Transfer-Encoding: chunked')
        self.assertEqual(inst.close_on_finish, False)

    def test_build_response_header_v11_304_headersonly(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.status = '304 OK'
        inst.version = '1.1'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], b'HTTP/1.1 304 OK')
        self.assertTrue(lines[1].startswith(b'Date:'))
        self.assertEqual(lines[2], b'Server: hithere')
        self.assertEqual(inst.close_on_finish, False)

    def test_build_response_header_v11_200_no_content_length(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.version = '1.1'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/1.1 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')
        self.assertEqual(inst.close_on_finish, True)
        self.assertTrue(('Connection', 'close') in inst.response_headers)

    def test_build_response_header_unrecognized_http_version(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.version = '8.1'
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/8.1 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')
        self.assertEqual(inst.close_on_finish, True)
        self.assertTrue(('Connection', 'close') in inst.response_headers)

    def test_build_response_header_via_added(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.version = '1.0'
        inst.response_headers = [('Server',  'abc')]
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b'HTTP/1.0 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: abc')
        self.assertEqual(lines[4], b'Via: hithere')

    def test_build_response_header_date_exists(self):
        inst = self._makeOne()
        inst.request_data = DummyParser()
        inst.version = '1.0'
        inst.response_headers = [('Date',  'date')]
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b'HTTP/1.0 200 OK')
        self.assertEqual(lines[1], b'Connection: close')
        self.assertTrue(lines[2].startswith(b'Date:'))
        self.assertEqual(lines[3], b'Server: hithere')

    def test_get_environment_already_cached(self):
        inst = self._makeOne()
        inst.environ = object()
        self.assertEqual(inst.get_environment(), inst.environ)

    def test_get_environment_path_startswith_more_than_one_slash(self):
        inst = self._makeOne()
        request_data = DummyParser()
        request_data.path = '///abc'
        inst.request_data = request_data
        environ = inst.get_environment()
        self.assertEqual(environ['PATH_INFO'], '/abc')

    def test_get_environment_path_empty(self):
        inst = self._makeOne()
        request_data = DummyParser()
        request_data.path = ''
        inst.request_data = request_data
        environ = inst.get_environment()
        self.assertEqual(environ['PATH_INFO'], '/')

    def test_get_environment_no_query(self):
        inst = self._makeOne()
        request_data = DummyParser()
        inst.request_data = request_data
        environ = inst.get_environment()
        self.assertFalse('QUERY_STRING' in environ)

    def test_get_environment_with_query(self):
        inst = self._makeOne()
        request_data = DummyParser()
        request_data.query = 'abc'
        inst.request_data = request_data
        environ = inst.get_environment()
        self.assertEqual(environ['QUERY_STRING'], 'abc')

    def test_get_environment_values(self):
        import sys
        inst = self._makeOne()
        request_data = DummyParser()
        request_data.headers = {'CONTENT_TYPE':'abc', 'CONTENT_LENGTH':'10',
                                'X_FOO':'BAR'}
        request_data.query = 'abc'
        inst.request_data = request_data
        environ = inst.get_environment()
        self.assertEqual(environ['REQUEST_METHOD'], 'GET')
        self.assertEqual(environ['SERVER_PORT'], '80')
        self.assertEqual(environ['SERVER_NAME'], 'localhost')
        self.assertEqual(environ['SERVER_SOFTWARE'], 'hithere')
        self.assertEqual(environ['SERVER_PROTOCOL'], 'HTTP/1.0')
        self.assertEqual(environ['SCRIPT_NAME'], '')
        self.assertEqual(environ['PATH_INFO'], '/')
        self.assertEqual(environ['QUERY_STRING'], 'abc')
        self.assertEqual(environ['REMOTE_ADDR'], '127.0.0.1')
        self.assertEqual(environ['CONTENT_TYPE'], 'abc')
        self.assertEqual(environ['CONTENT_LENGTH'], '10')
        self.assertEqual(environ['HTTP_X_FOO'], 'BAR')
        self.assertEqual(environ['wsgi.version'], (1, 0))
        self.assertEqual(environ['wsgi.url_scheme'], 'http')
        self.assertEqual(environ['wsgi.errors'], sys.stderr)
        self.assertEqual(environ['wsgi.multithread'], True)
        self.assertEqual(environ['wsgi.multiprocess'], False)
        self.assertEqual(environ['wsgi.run_once'], False)
        self.assertEqual(environ['wsgi.input'], 'stream')
        self.assertEqual(inst.environ, environ)

    def test_start(self):
        inst = self._makeOne()
        inst.start()
        self.assertTrue(inst.start_time)

    def test_finish_didnt_write_header(self):
        inst = self._makeOne()
        inst.wrote_header = False
        inst.start_response_called = True
        inst.finish()
        self.assertTrue(inst.channel.written)

    def test_finish_wrote_header(self):
        inst = self._makeOne()
        inst.wrote_header = True
        inst.finish()
        self.assertFalse(inst.channel.written)

    def test_write_wrote_header(self):
        inst = self._makeOne()
        inst.wrote_header = True
        inst.start_response_called = True
        inst.write(b'abc')
        self.assertEqual(inst.channel.written, b'abc')

    def test_write_header_not_written(self):
        inst = self._makeOne()
        inst.wrote_header = False
        inst.start_response_called = True
        inst.write(b'abc')
        self.assertTrue(inst.channel.written)
        self.assertEqual(inst.wrote_header, True)

    def test_write_start_response_uncalled(self):
        inst = self._makeOne()
        self.assertRaises(RuntimeError, inst.write, b'')


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
    server_name = 'localhost'
    port = 80
    def __init__(self, toraise=None):
        self.toraise = toraise
        self.executed = []
    def executeRequest(self, task):
        self.executed.append(task)
        if self.toraise:
            raise self.toraise

    def application(self, environ, start_response):
        start_response('200 OK', [])
        return [b'abc']

class DummyAdj(object):
    log_socket_errors = True

class DummyChannel(object):
    closed_when_done = False
    adj = DummyAdj()
    creation_time = 0
    addr = ['127.0.0.1']
    def __init__(self, server=None):
        if server is None:
            server = DummyServer()
        self.server = server
        self.written = b''
    def close_when_done(self):
        self.closed_when_done = True
    def write(self, data):
        self.written += data
        return len(data)

class DummyParser(object):
    version = '1.0'
    command = 'GET'
    path = '/'
    query = None
    url_scheme = 'http'
    expect_continue = False
    headers_finished = False
    def __init__(self):
        self.headers = {}
    def getBodyStream(self):
        return 'stream'

def filter_lines(s):
    return list(filter(None, s.split(b'\r\n')))

