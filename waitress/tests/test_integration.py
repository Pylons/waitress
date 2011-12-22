import unittest
from asyncore import socket_map, poll
from time import sleep, time
import StringIO
import socket
import sys
from threading import Thread, Event
from httplib import HTTPConnection
from httplib import HTTPResponse as ClientHTTPResponse

from zope.component.testing import PlacelessSetup
import zope.component

from zope.i18n.interfaces import IUserPreferredCharsets

from zope.publisher.publish import publish
from zope.publisher.http import IHTTPRequest
from zope.publisher.http import HTTPCharsets
from zope.publisher.browser import BrowserRequest

from waitress.tests.asyncerror import AsyncoreErrorHook

from zope.publisher.base import DefaultPublication
from zope.publisher.interfaces import Redirect, Retry
from zope.publisher.http import HTTPRequest

from waitress.task import ThreadedTaskDispatcher
from waitress.adjustments import Adjustments


td = ThreadedTaskDispatcher()

LOCALHOST = '127.0.0.1'

HTTPRequest.STAGGER_RETRIES = 0  # Don't pause.

LOCALHOST = '127.0.0.1'
SERVER_PORT = 0      # Set these port numbers to 0 to auto-bind, or
CONNECT_TO_PORT = 0  # use specific numbers to inspect using TCPWatch.

my_adj = Adjustments()
# Reduce overflows to make testing easier.
my_adj.outbuf_overflow = 10000
my_adj.inbuf_overflow = 10000


class TestWSGIHTTPEchoServer(unittest.TestCase, AsyncoreErrorHook):

    def setUp(self):
        # import only now to prevent the testrunner from importing it too early
        # Otherwise dualmodechannel.the_trigger is closed by the ZEO tests
        from waitress.server import WSGIHTTPServer
        class EchoHTTPServer(WSGIHTTPServer):

            def executeRequest(self, task):
                headers = task.request_data.headers
                if 'CONTENT_LENGTH' in headers:
                    cl = headers['CONTENT_LENGTH']
                    task.response_headers['Content-Length'] = cl
                instream = task.request_data.getBodyStream()
                while 1:
                    data = instream.read(8192)
                    if not data:
                        break
                    task.write(data)

        td.setThreadCount(4)
        if len(socket_map) != 1:
            # Let sockets die off.
            # TODO tests should be more careful to clear the socket map.
            poll(0.1)
        self.orig_map_size = len(socket_map)
        self.hook_asyncore_error()
        self.server = EchoHTTPServer(None, LOCALHOST, SERVER_PORT,
                                     task_dispatcher=td, adj=my_adj)
        if CONNECT_TO_PORT == 0:
            self.port = self.server.socket.getsockname()[1]
        else:
            self.port = CONNECT_TO_PORT
        self.run_loop = 1
        self.counter = 0
        self.thread_started = Event()
        self.thread = Thread(target=self.loop)
        self.thread.setDaemon(True)
        self.thread.start()
        self.thread_started.wait(10.0)
        self.assert_(self.thread_started.isSet())

    def tearDown(self):
        self.run_loop = 0
        self.thread.join()
        td.shutdown()
        self.server.close()
        # Make sure all sockets get closed by asyncore normally.
        timeout = time() + 5
        while 1:
            if len(socket_map) == self.orig_map_size:
                # Clean!
                break
            if time() >= timeout:
                self.fail('Leaked a socket: %s' % `socket_map`)
            poll(0.1)
        self.unhook_asyncore_error()

    def loop(self):
        self.thread_started.set()
        while self.run_loop:
            self.counter = self.counter + 1
            #print 'loop', self.counter
            poll(0.1)

    def testEchoResponse(self, h=None, add_headers=None, body=''):
        if h is None:
            h = HTTPConnection(LOCALHOST, self.port)
        headers = {}
        if add_headers:
            headers.update(add_headers)
        headers["Accept"] = "text/plain"
        # Content-Length header automatically added by HTTPConnection.request
        #if body:
        #    headers["Content-Length"] = str(int(len(body)))
        h.request("GET", "/", body, headers)
        response = h.getresponse()
        self.failUnlessEqual(int(response.status), 200)
        length = int(response.getheader('Content-Length', '0'))
        response_body = response.read()
        self.failUnlessEqual(length, len(response_body))
        self.failUnlessEqual(response_body, body)
        # HTTP 1.1 requires the server and date header.
        self.assertEqual(response.getheader('server'), 'waitress.http')
        self.assert_(response.getheader('date') is not None)

    def testMultipleRequestsWithoutBody(self):
        # Tests the use of multiple requests in a single connection.
        h = HTTPConnection(LOCALHOST, self.port)
        for n in range(3):
            self.testEchoResponse(h)
        self.testEchoResponse(h, {'Connection': 'close'})

    def testMultipleRequestsWithBody(self):
        # Tests the use of multiple requests in a single connection.
        h = HTTPConnection(LOCALHOST, self.port)
        for n in range(3):
            self.testEchoResponse(h, body='Hello, world!')
        self.testEchoResponse(h, {'Connection': 'close'})

    def testPipelining(self):
        # Tests the use of several requests issued at once.
        s = ("GET / HTTP/1.0\r\n"
             "Connection: %s\r\n"
             "Content-Length: %d\r\n"
             "\r\n"
             "%s")
        to_send = ''
        count = 25
        for n in range(count):
            body = "Response #%d\r\n" % (n + 1)
            if n + 1 < count:
                conn = 'keep-alive'
            else:
                conn = 'close'
            to_send += s % (conn, len(body), body)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, self.port))
        sock.send(to_send)
        for n in range(count):
            expect_body = "Response #%d\r\n" % (n + 1)
            response = ClientHTTPResponse(sock)
            response.begin()
            self.failUnlessEqual(int(response.status), 200)
            length = int(response.getheader('Content-Length', '0'))
            response_body = response.read(length)
            self.failUnlessEqual(length, len(response_body))
            self.failUnlessEqual(response_body, expect_body)

    def testWithoutCRLF(self):
        # Tests the use of just newlines rather than CR/LFs.
        data = "Echo\nthis\r\nplease"
        s = ("GET / HTTP/1.0\n"
             "Connection: close\n"
             "Content-Length: %d\n"
             "\n"
             "%s") % (len(data), data)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, self.port))
        sock.send(s)
        response = ClientHTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        length = int(response.getheader('Content-Length', '0'))
        response_body = response.read(length)
        self.failUnlessEqual(length, len(data))
        self.failUnlessEqual(response_body, data)

    def testLargeBody(self):
        # Tests the use of multiple requests in a single connection.
        h = HTTPConnection(LOCALHOST, self.port)
        s = 'This string has 32 characters.\r\n' * 32  # 1024 characters.
        self.testEchoResponse(h, body=(s * 1024))  # 1 MB
        self.testEchoResponse(h, {'Connection': 'close'},
                              body=(s * 100))  # 100 KB

    def testManyClients(self):
        # Set the number of connections to make.  A previous comment said
        # Linux kernel (2.4.8) doesn't like > 128.
        # The test used to use 50.  Win98SE can't handle that many, dying
        # with
        #      File "C:\PYTHON23\Lib\httplib.py", line 548, in connect
        #          raise socket.error, msg
        #      error: (10055, 'No buffer space available')
        nconn = 50
        if sys.platform == 'win32':
            platform = sys.getwindowsversion()[3]
            if platform < 2:
                # 0 is Win32s on Windows 3.1
                # 1 is 95/98/ME
                # 2 is NT/2000/XP

                # Pre-NT.  20 should work.  The exact number you can get away
                # with depends on what you're running at the same time (e.g.,
                # browsers and AIM and email delivery consume sockets too).
                nconn = 20

        conns = []
        for n in range(nconn):
            #print 'open', n, clock()
            h = HTTPConnection(LOCALHOST, self.port)
            #h.debuglevel = 1
            h.request("GET", "/", headers={"Accept": "text/plain"})
            conns.append(h)
            # If you uncomment the next line, you can raise the
            # number of connections much higher without running
            # into delays.
            #sleep(0.01)
        responses = []
        for h in conns:
            response = h.getresponse()
            self.failUnlessEqual(response.status, 200)
            responses.append(response)
        for response in responses:
            response.read()

    def testThreading(self):
        # Ensures the correct number of threads keep running.
        for n in range(4):
            td.addTask(SleepingTask())
        # Try to confuse the task manager.
        td.setThreadCount(2)
        td.setThreadCount(1)
        sleep(0.5)
        # There should be 1 still running.
        self.failUnlessEqual(len(td.threads), 1)

    def testChunkingRequestWithoutContent(self):
        h = HTTPConnection(LOCALHOST, self.port)
        h.request("GET", "/", headers={"Accept": "text/plain",
                                       "Transfer-Encoding": "chunked"})
        h.send("0\r\n\r\n")
        response = h.getresponse()
        self.failUnlessEqual(int(response.status), 200)
        response_body = response.read()
        self.failUnlessEqual(response_body, '')

    def testChunkingRequestWithContent(self):
        control_line="20;\r\n"  # 20 hex = 32 dec
        s = 'This string has 32 characters.\r\n'
        expect = s * 12

        h = HTTPConnection(LOCALHOST, self.port)
        h.request("GET", "/", headers={"Accept": "text/plain",
                                       "Transfer-Encoding": "chunked"})
        for n in range(12):
            h.send(control_line)
            h.send(s)
        h.send("0\r\n\r\n")
        response = h.getresponse()
        self.failUnlessEqual(int(response.status), 200)
        response_body = response.read()
        self.failUnlessEqual(response_body, expect)

    def testKeepaliveHttp10(self):
        # Handling of Keep-Alive within HTTP 1.0
        data = "Default: Don't keep me alive"
        s = ("GET / HTTP/1.0\n"
             "Content-Length: %d\n"
             "\n"
             "%s") % (len(data), data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, self.port))
        sock.send(s)
        response = ClientHTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        connection = response.getheader('Connection', '')
        # We sent no Connection: Keep-Alive header
        # Connection: close (or no header) is default.
        self.failUnless(connection != 'Keep-Alive')

        # If header Connection: Keep-Alive is explicitly sent,
        # we want to keept the connection open, we also need to return
        # the corresponding header
        data = "Keep me alive"
        s = ("GET / HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: %d\n"
             "\n"
             "%s") % (len(data), data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, self.port))
        sock.send(s)
        response = ClientHTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        connection = response.getheader('Connection', '')
        self.failUnlessEqual(connection, 'Keep-Alive')

    def testKeepaliveHttp11(self):
        # Handling of Keep-Alive within HTTP 1.1

        # All connections are kept alive, unless stated otherwise
        data = "Default: Keep me alive"
        s = ("GET / HTTP/1.1\n"
             "Content-Length: %d\n"
             "\n"
             "%s") % (len(data), data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, self.port))
        sock.send(s)
        response = ClientHTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        self.failUnless(response.getheader('connection') != 'close')

        # Explicitly set keep-alive
        data = "Default: Keep me alive"
        s = ("GET / HTTP/1.1\n"
             "Connection: keep-alive\n"
             "Content-Length: %d\n"
             "\n"
             "%s") % (len(data), data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, self.port))
        sock.send(s)
        response = ClientHTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        self.failUnless(response.getheader('connection') != 'close')

        # no idea why the test publisher handles this request incorrectly
        # it would be less typing in the test :)
        # h = HTTPConnection(LOCALHOST, self.port)
        # h.request("GET", "/")
        # response = h.getresponse()
        # self.failUnlessEqual(int(response.status), 200)
        # self.failUnless(response.getheader('connection') != 'close')

        # specifying Connection: close explicitly
        data = "Don't keep me alive"
        s = ("GET / HTTP/1.1\n"
             "Connection: close\n"
             "Content-Length: %d\n"
             "\n"
             "%s") % (len(data), data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, self.port))
        sock.send(s)
        response = ClientHTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        self.failUnlessEqual(response.getheader('connection'), 'close')

class TestWSGIHTTPServerWithPublisher(PlacelessSetup, unittest.TestCase):

    def _getServerClass(self):
        # import only now to prevent the testrunner from importing it too early
        # Otherwise dualmodechannel.the_trigger is closed by the ZEO tests
        from waitress.server import WSGIHTTPServer
        return WSGIHTTPServer

    def setUp(self):
        super(TestWSGIHTTPServerWithPublisher, self).setUp()
        zope.component.provideAdapter(HTTPCharsets, [IHTTPRequest],
                                      IUserPreferredCharsets, '')
        obj = tested_object()
        obj.folder = tested_object()
        obj.folder.item = tested_object()
        obj._protected = tested_object()
        obj.wsgi = WSGIInfo()

        pub = PublicationWithConflict(obj)

        def application(environ, start_response):
            request = BrowserRequest(environ['wsgi.input'], environ)
            request.setPublication(pub)
            request = publish(request)
            response = request.response
            start_response(response.getStatusString(), response.getHeaders())
            return response.consumeBodyIter()

        td.setThreadCount(4)
        # Bind to any port on localhost.
        ServerClass = self._getServerClass()
        self.server = ServerClass(application,
                                  LOCALHOST, 0, task_dispatcher=td,
                                  sub_protocol='Browser')

        self.port = self.server.socket.getsockname()[1]
        self.run_loop = 1
        self.thread = Thread(target=self.loop)
        self.thread.start()
        sleep(0.1)  # Give the thread some time to start.

    def tearDown(self):
        self.run_loop = 0
        self.thread.join()
        td.shutdown()
        self.server.close()
        super(TestWSGIHTTPServerWithPublisher, self).tearDown()

    def loop(self):
        while self.run_loop:
            poll(0.1, socket_map)

    def invokeRequest(self, path='/', add_headers=None, request_body='',
                      return_response=False):
        h = HTTPConnection(LOCALHOST, self.port)
        h.putrequest('GET', path)
        h.putheader('Accept', 'text/plain')
        if add_headers:
            for k, v in add_headers.items():
                h.putheader(k, v)
        if request_body:
            h.putheader('Content-Length', str(int(len(request_body))))
        h.endheaders()
        if request_body:
            h.send(request_body)
        response = h.getresponse()
        if return_response:
            return response
        length = int(response.getheader('Content-Length', '0'))
        if length:
            response_body = response.read(length)
        else:
            response_body = ''

        self.assertEqual(length, len(response_body))

        return response.status, response_body


    def testDeeperPath(self):
        status, response_body = self.invokeRequest('/folder/item')
        self.assertEqual(status, 200)
        expect_response = 'URL invoked: http://%s:%d/folder/item' % (
            LOCALHOST, self.port)
        self.assertEqual(response_body, expect_response)

    def testNotFound(self):
        status, response_body = self.invokeRequest('/foo/bar')
        self.assertEqual(status, 404)

    def testUnauthorized(self):
        status, response_body = self.invokeRequest('/_protected')
        self.assertEqual(status, 401)

    def testRedirectMethod(self):
        status, response_body = self.invokeRequest('/redirect_method')
        self.assertEqual(status, 303)

    def testRedirectException(self):
        status, response_body = self.invokeRequest('/redirect_exception')
        self.assertEqual(status, 303)
        status, response_body = self.invokeRequest('/folder/redirect_exception')
        self.assertEqual(status, 303)

    def testConflictRetry(self):
        status, response_body = self.invokeRequest('/conflict?wait_tries=2')
        # Expect the "Accepted" response since the retries will succeed.
        self.assertEqual(status, 202)

    def testFailedConflictRetry(self):
        status, response_body = self.invokeRequest('/conflict?wait_tries=10')
        # Expect a "Conflict" response since there will be too many
        # conflicts.
        self.assertEqual(status, 409)

    def testServerAsProxy(self):
        response = self.invokeRequest(
            '/proxy', return_response=True)
        # The headers set by the proxy are honored,
        self.assertEqual(
            response.getheader('Server'), 'Fake/1.0')
        self.assertEqual(
            response.getheader('Date'), 'Thu, 01 Apr 2010 12:00:00 GMT')
        # The server adds a Via header.
        self.assertEqual(
            response.getheader('Via'), 'waitress.http (Browser)')
        # And the content got here too.
        self.assertEqual(response.read(), 'Proxied Content')

    def testWSGIVariables(self):
        # Assert that the environment contains all required WSGI variables
        status, response_body = self.invokeRequest('/wsgi')
        wsgi_variables = set(response_body.split())
        self.assertEqual(wsgi_variables,
                         set(['wsgi.version', 'wsgi.url_scheme', 'wsgi.input',
                              'wsgi.errors', 'wsgi.multithread',
                              'wsgi.multiprocess', 'wsgi.run_once']))

    def testWSGIVersion(self):
        status, response_body = self.invokeRequest('/wsgi/version')
        self.assertEqual("(1, 0)", response_body)

    def testWSGIURLScheme(self):
        status, response_body = self.invokeRequest('/wsgi/url_scheme')
        self.assertEqual('http', response_body)

    def testWSGIMultithread(self):
        status, response_body = self.invokeRequest('/wsgi/multithread')
        self.assertEqual('True', response_body)

    def testWSGIMultiprocess(self):
        status, response_body = self.invokeRequest('/wsgi/multiprocess')
        self.assertEqual('True', response_body)

    def testWSGIRunOnce(self):
        status, response_body = self.invokeRequest('/wsgi/run_once')
        self.assertEqual('False', response_body)

    def testWSGIProxy(self):
        status, response_body = self.invokeRequest(
            'https://zope.org:8080/wsgi/proxy_scheme')
        self.assertEqual('https', response_body)
        status, response_body = self.invokeRequest(
            'https://zope.org:8080/wsgi/proxy_host')
        self.assertEqual('zope.org:8080', response_body)

    def test_ensure_multiple_task_write_calls(self):
        # In order to get data out as fast as possible, the WSGI server needs
        # to call task.write() multiple times.
        orig_app = self.server.application
        def app(eviron, start_response):
            start_response('200 Ok', [])
            return ['This', 'is', 'my', 'response.']
        self.server.application = app

        class FakeTask:
            wrote_header = 0
            counter = 0
            getCGIEnvironment = lambda _: {}
            class request_data:
                getBodyStream = lambda _: StringIO.StringIO()
            request_data = request_data()
            setResponseStatus = appendResponseHeaders = lambda *_: None
            def wroteResponseHeader(self):
                return self.wrote_header
            def write(self, v):
                self.counter += 1

        task = FakeTask()
        self.server.executeRequest(task)
        self.assertEqual(task.counter, 4)

        self.server.application = orig_app

    def _getFakeAppAndTask(self):

        def app(environ, start_response):
            try:
                raise DummyException()
            except DummyException:
                start_response(
                    '500 Internal Error',
                    [('Content-type', 'text/plain')],
                    sys.exc_info())
                return ERROR_RESPONSE.split()
            return RESPONSE.split()

        class FakeTask:
            wrote_header = 0
            status = None
            reason = None
            response = []
            accumulated_headers = None
            def __init__(self):
                self.accumulated_headers = []
                self.response_headers = {}
            getCGIEnvironment = lambda _: {}
            class request_data:
                getBodyStream = lambda _: StringIO.StringIO()
            request_data = request_data()
            def appendResponseHeaders(self, lst):
                accum = self.accumulated_headers
                if accum is None:
                    self.accumulated_headers = accum = []
                accum.extend(lst)
            def setResponseStatus(self, status, reason):
                self.status = status
                self.reason = reason
            def wroteResponseHeader(self):
                return self.wrote_header
            def write(self, v):
                self.response.append(v)

        return app, FakeTask()


    def test_start_response_with_no_headers_sent(self):
        # start_response exc_info if no headers have been sent
        orig_app = self.server.application
        self.server.application, task = self._getFakeAppAndTask()
        task.accumulated_headers = ['header1', 'header2']
        task.accumulated_headers = {'key1': 'value1', 'key2': 'value2'}

        self.server.executeRequest(task)

        self.assertEqual(task.status, "500")
        self.assertEqual(task.response, ERROR_RESPONSE.split())
        # any headers written before are cleared and
        # only the most recent one is added.
        self.assertEqual(task.accumulated_headers, ['Content-type: text/plain'])
        # response headers are cleared. They'll be rebuilt from
        # accumulated_headers in the prepareResponseHeaders method
        self.assertEqual(task.response_headers, {})

        self.server.application = orig_app


    def test_multiple_start_response_calls(self):
        # if start_response is called more than once with no exc_info
        ignore, task = self._getFakeAppAndTask()
        task.wrote_header = 1

        self.assertRaises(AssertionError, self.server.executeRequest, task)


    def test_start_response_with_headers_sent(self):
        # If headers have been sent it raises the exception
        orig_app = self.server.application
        self.server.application, task = self._getFakeAppAndTask()

        # If headers have already been written an exception is raised
        task.wrote_header = 1
        self.assertRaises(DummyException, self.server.executeRequest, task)

        self.server.application = orig_app

class TestWSGIHTTPServer(PlacelessSetup, unittest.TestCase):

    def _getServerClass(self):
        # import only now to prevent the testrunner from importing it too early
        # Otherwise dualmodechannel.the_trigger is closed by the ZEO tests
        from waitress.server import WSGIHTTPServer
        return WSGIHTTPServer

    def setUp(self):
        super(TestWSGIHTTPServer, self).setUp()
        zope.component.provideAdapter(HTTPCharsets, [IHTTPRequest],
                                      IUserPreferredCharsets, '')
        obj = tested_object()
        obj.folder = tested_object()
        obj.folder.item = tested_object()
        obj._protected = tested_object()
        obj.wsgi = WSGIInfo()

        pub = PublicationWithConflict(obj)

        def application(environ, start_response):
            request = BrowserRequest(environ['wsgi.input'], environ)
            request.setPublication(pub)
            request = publish(request)
            response = request.response
            start_response(response.getStatusString(), response.getHeaders())
            return response.consumeBodyIter()

        td.setThreadCount(4)
        # Bind to any port on localhost.
        ServerClass = self._getServerClass()
        self.server = ServerClass(application, LOCALHOST, 0, task_dispatcher=td,
                                  sub_protocol='Browser')

        self.port = self.server.socket.getsockname()[1]
        self.run_loop = 1
        self.thread = Thread(target=self.loop)
        self.thread.start()
        sleep(0.1)  # Give the thread some time to start.

    def tearDown(self):
        self.run_loop = 0
        self.thread.join()
        td.shutdown()
        self.server.close()
        super(TestWSGIHTTPServer, self).tearDown()

    def loop(self):
        while self.run_loop:
            poll(0.1, socket_map)

    def invokeRequest(self, path='/', add_headers=None, request_body='',
                      return_response=False):
        h = HTTPConnection(LOCALHOST, self.port)
        h.putrequest('GET', path)
        h.putheader('Accept', 'text/plain')
        if add_headers:
            for k, v in add_headers.items():
                h.putheader(k, v)
        if request_body:
            h.putheader('Content-Length', str(int(len(request_body))))
        h.endheaders()
        if request_body:
            h.send(request_body)
        response = h.getresponse()
        if return_response:
            return response
        length = int(response.getheader('Content-Length', '0'))
        if length:
            response_body = response.read(length)
        else:
            response_body = ''

        self.assertEqual(length, len(response_body))

        return response.status, response_body


    def testDeeperPath(self):
        status, response_body = self.invokeRequest('/folder/item')
        self.assertEqual(status, 200)
        expect_response = 'URL invoked: http://%s:%d/folder/item' % (
            LOCALHOST, self.port)
        self.assertEqual(response_body, expect_response)

    def testNotFound(self):
        status, response_body = self.invokeRequest('/foo/bar')
        self.assertEqual(status, 404)

    def testUnauthorized(self):
        status, response_body = self.invokeRequest('/_protected')
        self.assertEqual(status, 401)

    def testRedirectMethod(self):
        status, response_body = self.invokeRequest('/redirect_method')
        self.assertEqual(status, 303)

    def testRedirectException(self):
        status, response_body = self.invokeRequest('/redirect_exception')
        self.assertEqual(status, 303)
        status, response_body = self.invokeRequest('/folder/redirect_exception')
        self.assertEqual(status, 303)

    def testConflictRetry(self):
        status, response_body = self.invokeRequest('/conflict?wait_tries=2')
        # Expect the "Accepted" response since the retries will succeed.
        self.assertEqual(status, 202)

    def testFailedConflictRetry(self):
        status, response_body = self.invokeRequest('/conflict?wait_tries=10')
        # Expect a "Conflict" response since there will be too many
        # conflicts.
        self.assertEqual(status, 409)

    def testServerAsProxy(self):
        response = self.invokeRequest(
            '/proxy', return_response=True)
        # The headers set by the proxy are honored,
        self.assertEqual(
            response.getheader('Server'), 'Fake/1.0')
        self.assertEqual(
            response.getheader('Date'), 'Thu, 01 Apr 2010 12:00:00 GMT')
        # The server adds a Via header.
        self.assertEqual(
            response.getheader('Via'), 'waitress.http (Browser)')
        # And the content got here too.
        self.assertEqual(response.read(), 'Proxied Content')

    def testWSGIVariables(self):
        # Assert that the environment contains all required WSGI variables
        status, response_body = self.invokeRequest('/wsgi')
        wsgi_variables = set(response_body.split())
        self.assertEqual(wsgi_variables,
                         set(['wsgi.version', 'wsgi.url_scheme', 'wsgi.input',
                              'wsgi.errors', 'wsgi.multithread',
                              'wsgi.multiprocess', 'wsgi.run_once']))

    def testWSGIVersion(self):
        status, response_body = self.invokeRequest('/wsgi/version')
        self.assertEqual("(1, 0)", response_body)

    def testWSGIURLScheme(self):
        status, response_body = self.invokeRequest('/wsgi/url_scheme')
        self.assertEqual('http', response_body)

    def testWSGIMultithread(self):
        status, response_body = self.invokeRequest('/wsgi/multithread')
        self.assertEqual('True', response_body)

    def testWSGIMultiprocess(self):
        status, response_body = self.invokeRequest('/wsgi/multiprocess')
        self.assertEqual('True', response_body)

    def testWSGIRunOnce(self):
        status, response_body = self.invokeRequest('/wsgi/run_once')
        self.assertEqual('False', response_body)

    def testWSGIProxy(self):
        status, response_body = self.invokeRequest(
            'https://zope.org:8080/wsgi/proxy_scheme')
        self.assertEqual('https', response_body)
        status, response_body = self.invokeRequest(
            'https://zope.org:8080/wsgi/proxy_host')
        self.assertEqual('zope.org:8080', response_body)

    def test_ensure_multiple_task_write_calls(self):
        # In order to get data out as fast as possible, the WSGI server needs
        # to call task.write() multiple times.
        orig_app = self.server.application
        def app(eviron, start_response):
            start_response('200 Ok', [])
            return ['This', 'is', 'my', 'response.']
        self.server.application = app

        class FakeTask:
            wrote_header = 0
            counter = 0
            getCGIEnvironment = lambda _: {}
            class request_data:
                getBodyStream = lambda _: StringIO.StringIO()
            request_data = request_data()
            setResponseStatus = appendResponseHeaders = lambda *_: None
            def wroteResponseHeader(self):
                return self.wrote_header
            def write(self, v):
                self.counter += 1

        task = FakeTask()
        self.server.executeRequest(task)
        self.assertEqual(task.counter, 4)

        self.server.application = orig_app

    def _getFakeAppAndTask(self):

        def app(environ, start_response):
            try:
                raise DummyException()
            except DummyException:
                start_response(
                    '500 Internal Error',
                    [('Content-type', 'text/plain')],
                    sys.exc_info())
                return ERROR_RESPONSE.split()
            return RESPONSE.split()

        class FakeTask:
            wrote_header = 0
            status = None
            reason = None
            response = []
            accumulated_headers = None
            def __init__(self):
                self.accumulated_headers = []
                self.response_headers = {}
            getCGIEnvironment = lambda _: {}
            class request_data:
                getBodyStream = lambda _: StringIO.StringIO()
            request_data = request_data()
            def appendResponseHeaders(self, lst):
                accum = self.accumulated_headers
                if accum is None:
                    self.accumulated_headers = accum = []
                accum.extend(lst)
            def setResponseStatus(self, status, reason):
                self.status = status
                self.reason = reason
            def wroteResponseHeader(self):
                return self.wrote_header
            def write(self, v):
                self.response.append(v)

        return app, FakeTask()


    def test_start_response_with_no_headers_sent(self):
        # start_response exc_info if no headers have been sent
        orig_app = self.server.application
        self.server.application, task = self._getFakeAppAndTask()
        task.accumulated_headers = ['header1', 'header2']
        task.accumulated_headers = {'key1': 'value1', 'key2': 'value2'}

        self.server.executeRequest(task)

        self.assertEqual(task.status, "500")
        self.assertEqual(task.response, ERROR_RESPONSE.split())
        # any headers written before are cleared and
        # only the most recent one is added.
        self.assertEqual(task.accumulated_headers, ['Content-type: text/plain'])
        # response headers are cleared. They'll be rebuilt from
        # accumulated_headers in the prepareResponseHeaders method
        self.assertEqual(task.response_headers, {})

        self.server.application = orig_app


    def test_multiple_start_response_calls(self):
        # if start_response is called more than once with no exc_info
        ignore, task = self._getFakeAppAndTask()
        task.wrote_header = 1

        self.assertRaises(AssertionError, self.server.executeRequest, task)


    def test_start_response_with_headers_sent(self):
        # If headers have been sent it raises the exception
        orig_app = self.server.application
        self.server.application, task = self._getFakeAppAndTask()

        # If headers have already been written an exception is raised
        task.wrote_header = 1
        self.assertRaises(DummyException, self.server.executeRequest, task)

        self.server.application = orig_app

class SleepingTask(object):

    def service(self):
        sleep(0.2)

    def cancel(self):
        pass

    def defer(self):
        pass


class Conflict(Exception):
    """
    Pseudo ZODB conflict error.
    """

ERROR_RESPONSE = "error occurred"
RESPONSE = "normal response"

class DummyException(Exception):
    value = "Dummy Exception to test start_response"
    def __str__(self):
        return repr(self.value)

class PublicationWithConflict(DefaultPublication):

    def handleException(self, object, request, exc_info, retry_allowed=1):
        if exc_info[0] is Conflict and retry_allowed:
            # This simulates a ZODB retry.
            raise Retry(exc_info)
        else:
            DefaultPublication.handleException(self, object, request, exc_info,
                                               retry_allowed)

class Accepted(Exception):
    pass

class tested_object(object):
    """Docstring required by publisher."""
    tries = 0

    def __call__(self, REQUEST):
        return 'URL invoked: %s' % REQUEST.URL

    def redirect_method(self, REQUEST):
        "Generates a redirect using the redirect() method."
        REQUEST.response.redirect("/redirect")

    def redirect_exception(self):
        "Generates a redirect using an exception."
        raise Redirect("/exception")

    def conflict(self, REQUEST, wait_tries):
        """
        Returns 202 status only after (wait_tries) tries.
        """
        if self.tries >= int(wait_tries):
            raise Accepted
        else:
            self.tries += 1
            raise Conflict

    def proxy(self, REQUEST):
        """Behaves like a real proxy response."""
        REQUEST.response.addHeader('Server', 'Fake/1.0')
        REQUEST.response.addHeader('Date', 'Thu, 01 Apr 2010 12:00:00 GMT')
        return 'Proxied Content'

class WSGIInfo(object):
    """Docstring required by publisher"""

    def __call__(self, REQUEST):
        """Return a list of variables beginning with 'wsgi.'"""
        r = []
        for name in REQUEST.keys():
            if name.startswith('wsgi.'):
                r.append(name)
        return ' '.join(r)

    def version(self, REQUEST):
        """Return WSGI version"""
        return str(REQUEST['wsgi.version'])

    def url_scheme(self, REQUEST):
        """Return WSGI URL scheme"""
        return REQUEST['wsgi.url_scheme']

    def multithread(self, REQUEST):
        """Return WSGI multithreadedness"""
        return str(bool(REQUEST['wsgi.multithread']))

    def multiprocess(self, REQUEST):
        """Return WSGI multiprocessedness"""
        return str(bool(REQUEST['wsgi.multiprocess']))

    def run_once(self, REQUEST):
        """Return whether WSGI app is invoked only once or not"""
        return str(bool(REQUEST['wsgi.run_once']))

    def proxy_scheme(self, REQUEST):
        """Return the proxy scheme."""
        return REQUEST['waitress.proxy.scheme']

    def proxy_host(self, REQUEST):
        """Return the proxy host."""
        return REQUEST['waitress.proxy.host']

