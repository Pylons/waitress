import os
import socket
import subprocess
import sys
import time
import unittest
from waitress.compat import (
    httplib,
    tobytes
    )

dn = os.path.dirname
here = dn(__file__)

class SubprocessTests(object):
    exe = sys.executable
    port = 61523
    host = 'localhost'
    def start_subprocess(self, cmd):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cwd = os.getcwd()
        os.chdir(dn(dn(here)))
        self.proc = subprocess.Popen(cmd)
        os.chdir(cwd)
        time.sleep(.2)
        if self.proc.returncode is not None: # pragma: no cover
            raise RuntimeError('%s didnt start' % str(cmd))
        self.conn = httplib.HTTPConnection('%s:%s' % (self.host, self.port))

    def stop_subprocess(self):
        time.sleep(.2)
        if self.proc.returncode is None:
            self.conn.close()
            self.proc.terminate()
        self.sock.close()

    def getresponse(self, status=200):
        resp = self.conn.getresponse()
        self.assertEqual(resp.status, status)
        return resp

    def assertline(self, line, status, reason, version):
        v, s, r = (x.strip() for x in line.split(None, 2))
        self.assertEqual(s, tobytes(status))
        self.assertEqual(r, tobytes(reason))
        self.assertEqual(v, tobytes(version))

class EchoTests(SubprocessTests, unittest.TestCase):
    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'echo.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()

    def test_date_and_server(self):
        self.conn.request('GET', '/')
        resp = self.getresponse()
        resp.read()
        self.assertEqual(resp.getheader('Server'), 'waitress')
        self.assertTrue(resp.getheader('Date'))

    def test_send_with_body(self):
        self.conn.request('GET', '/', b'hello')
        resp = self.getresponse()
        self.assertEqual(resp.getheader('Content-Length'), '5')
        body = resp.read()
        self.assertEqual(body, b'hello')

    def test_send_empty_body(self):
        self.conn.request('GET', '/')
        resp = self.getresponse()
        self.assertEqual(resp.getheader('Content-Length'), '0')
        body = resp.read()
        self.assertEqual(body, b'')

    def test_multiple_requests_with_body(self):
        for x in range(3):
            self.test_send_with_body()

    def test_multiple_requests_without_body(self):
        for x in range(3):
            self.test_send_empty_body()

    def test_without_crlf(self):
        data = "Echo\nthis\r\nplease"
        s = tobytes(
            "GET / HTTP/1.0\n"
            "Connection: close\n"
            "Content-Length: %d\n"
            "\n"
            "%s" % (len(data), data)
            )
        self.sock.connect((self.host, self.port))
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        length = int(response.getheader('Content-Length', '0'))
        response_body = response.read(length)
        self.assertEqual(length, len(data))
        self.assertEqual(response_body, tobytes(data))

    def test_large_body(self):
        # 1024 characters.
        s = tobytes('This string has 32 characters.\r\n' * 32)  
        self.conn.request('GET', '/', s)
        resp = self.getresponse()
        self.assertEqual(resp.getheader('Content-Length'), '1024')
        body = resp.read()
        self.assertEqual(body, s)

    def test_many_clients(self):
        conns = []
        for n in range(50):
            #print 'open', n, clock()
            h = httplib.HTTPConnection(self.host, self.port)
            h.request("GET", "/", headers={"Accept": "text/plain"})
            conns.append(h)
        responses = []
        for h in conns:
            response = h.getresponse()
            self.assertEqual(response.status, 200)
            responses.append(response)
        for response in responses:
            response.read()

    def test_chunking_request_without_content(self):
        self.conn.request("GET", "/", headers={"Accept": "text/plain",
                                               "Transfer-Encoding": "chunked"})
        self.conn.send(b"0\r\n\r\n")
        response = self.conn.getresponse()
        self.assertEqual(int(response.status), 200)
        response_body = response.read()
        self.assertEqual(response_body, b'')

    def test_chunking_request_with_content(self):
        control_line = b"20;\r\n"  # 20 hex = 32 dec
        s = b'This string has 32 characters.\r\n'
        expect = s * 12

        self.conn.request("GET", "/", headers={"Accept": "text/plain",
                                               "Transfer-Encoding": "chunked"})
        for n in range(12):
            self.conn.send(control_line)
            self.conn.send(s)
        self.conn.send(b"0\r\n\r\n")
        response = self.conn.getresponse()
        self.assertEqual(int(response.status), 200)
        response_body = response.read()
        self.assertEqual(response_body, expect)

    def test_broken_chunked_encoding(self):
        control_line = "20;\r\n"  # 20 hex = 32 dec
        s = 'This string has 32 characters.\r\n'
        to_send = "GET / HTTP/1.1\nTransfer-Encoding: chunked\n\n"
        to_send += (control_line + s)
        # garbage in input
        to_send += "GET / HTTP/1.1\nTransfer-Encoding: chunked\n\n"
        to_send += (control_line + s)
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        # receiver caught garbage and turned it into a 400
        self.assertline(line, '400', 'Bad Request', 'HTTP/1.1')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        self.assertEqual(headers['content-type'], 'text/plain')
        self.assertEqual(headers['connection'], 'close')
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_keepalive_http_10(self):
        # Handling of Keep-Alive within HTTP 1.0
        data = "Default: Don't keep me alive"
        s = tobytes(
            "GET / HTTP/1.0\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        connection = response.getheader('Connection', '')
        # We sent no Connection: Keep-Alive header
        # Connection: close (or no header) is default.
        self.assertTrue(connection != 'Keep-Alive')

    def test_keepalive_http10_explicit(self):
        # If header Connection: Keep-Alive is explicitly sent,
        # we want to keept the connection open, we also need to return
        # the corresponding header
        data = "Keep me alive"
        s = tobytes(
            "GET / HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
            )
        self.sock.connect((self.host, self.port))
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        connection = response.getheader('Connection', '')
        self.assertEqual(connection, 'Keep-Alive')

    def test_keepalive_http_11(self):
        # Handling of Keep-Alive within HTTP 1.1

        # All connections are kept alive, unless stated otherwise
        data = "Default: Keep me alive"
        s = tobytes(
            "GET / HTTP/1.1\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data))
        self.sock.connect((self.host, self.port))
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        self.assertTrue(response.getheader('connection') != 'close')

    def test_keepalive_http11_explicit(self):
        # Explicitly set keep-alive
        data = "Default: Keep me alive"
        s = tobytes(
            "GET / HTTP/1.1\n"
             "Connection: keep-alive\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        self.assertTrue(response.getheader('connection') != 'close')

    def test_keepalive_http11_connclose(self):
        # specifying Connection: close explicitly
        data = "Don't keep me alive"
        s = tobytes(
            "GET / HTTP/1.1\n"
             "Connection: close\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        self.assertEqual(response.getheader('connection'), 'close')

class PipeliningTests(SubprocessTests, unittest.TestCase):
    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'echo.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()

    def test_pipelining(self):
        s = ("GET / HTTP/1.0\r\n"
             "Connection: %s\r\n"
             "Content-Length: %d\r\n"
             "\r\n"
             "%s")
        to_send = b''
        count = 25
        for n in range(count):
            body = "Response #%d\r\n" % (n + 1)
            if n + 1 < count:
                conn = 'keep-alive'
            else:
                conn = 'close'
            to_send += tobytes(s % (conn, len(body), body))

        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        for n in range(count):
            expect_body = tobytes("Response #%d\r\n" % (n + 1))
            line = fp.readline() # status line
            version, status, reason = (x.strip() for x in line.split(None, 2))
            headers = parse_headers(fp)
            length = int(headers.get('content-length')) or None
            response_body = fp.read(length)
            self.assertEqual(int(status), 200)
            self.assertEqual(length, len(response_body))
            self.assertEqual(response_body, expect_body)

class ExpectContinueTests(SubprocessTests, unittest.TestCase):
    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'echo.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()

    def test_expect_continue(self):
        # specifying Connection: close explicitly
        data = "I have expectations"
        to_send = tobytes(
            "GET / HTTP/1.1\n"
             "Connection: close\n"
             "Content-Length: %d\n"
             "Expect: 100-continue\n"
             "\n"
             "%s" % (len(data), data)
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line = fp.readline() # continue status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        self.assertEqual(int(status), 100)
        self.assertEqual(reason, b'Continue')
        self.assertEqual(version, b'HTTP/1.1')
        fp.readline() # blank line
        line = fp.readline() # next status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        length = int(headers.get('content-length')) or None
        response_body = fp.read(length)
        self.assertEqual(int(status), 200)
        self.assertEqual(length, len(response_body))
        self.assertEqual(response_body, tobytes(data))

class BadContentLengthTests(SubprocessTests, unittest.TestCase):
    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'badcl.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()

    def test_short_body(self):
        # check to see if server closes connection when body is too short
        # for cl header
        to_send = tobytes(
            "GET /short_body HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: 0\n"
             "\n"
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line = fp.readline() # status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        content_length = int(headers.get('content-length'))
        response_body = fp.read(content_length)
        self.assertEqual(int(status), 200)
        self.assertNotEqual(content_length, len(response_body))
        self.assertEqual(len(response_body), content_length-1)
        self.assertEqual(response_body, tobytes('abcdefghi'))
        # remote closed connection (despite keepalive header); not sure why
        # first send succeeds
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_long_body(self):
        # check server doesnt close connection when body is too short
        # for cl header
        to_send = tobytes(
            "GET /long_body HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: 0\n"
             "\n"
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line = fp.readline() # status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        content_length = int(headers.get('content-length')) or None
        response_body = fp.read(content_length)
        self.assertEqual(int(status), 200)
        self.assertEqual(content_length, len(response_body))
        self.assertEqual(response_body, tobytes('abcdefgh'))
        # remote does not close connection (keepalive header)
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line = fp.readline() # status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        content_length = int(headers.get('content-length')) or None
        response_body = fp.read(content_length)
        self.assertEqual(int(status), 200)

class NoContentLengthTests(SubprocessTests, unittest.TestCase):
    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'nocl.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()

    def test_generator(self):
        self.conn.request("GET", "/generator",
                          headers={"Connection": "Keep-Alive",
                                   "Content-Length": "0"})
        resp = self.getresponse()
        self.assertEqual(resp.getheader('Content-Length'), None)
        self.assertEqual(resp.getheader('Connection'), 'close')
        self.assertEqual(resp.read(), b'abcdefghi')

    def test_list(self):
        self.conn.request("GET", "/list",
                          headers={"Connection": "Keep-Alive",
                                   "Content-Length": "0"})
        resp = self.getresponse()
        self.assertEqual(resp.getheader('Content-Length'), '9')
        self.assertEqual(resp.getheader('Connection'), None)
        self.assertEqual(resp.read(), b'abcdefghi')

class WriteCallbackTests(SubprocessTests, unittest.TestCase):
    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'writecb.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()

    def test_short_body(self):
        # check to see if server closes connection when body is too short
        # for cl header
        to_send = tobytes(
            "GET /short_body HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: 0\n"
             "\n"
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (5)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, 9)
        self.assertNotEqual(cl, len(response_body))
        self.assertEqual(len(response_body), cl-1)
        self.assertEqual(response_body, tobytes('abcdefgh'))
        # remote closed connection (despite keepalive header)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_long_body(self):
        # check server doesnt close connection when body is too long
        # for cl header
        to_send = tobytes(
            "GET /long_body HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: 0\n"
             "\n"
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        content_length = int(headers.get('content-length')) or None
        self.assertEqual(content_length, 9)
        self.assertEqual(content_length, len(response_body))
        self.assertEqual(response_body, tobytes('abcdefghi'))
        # remote does not close connection (keepalive header)
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')

    def test_equal_body(self):
        # check server doesnt close connection when body is equal to
        # cl header
        to_send = tobytes(
            "GET /equal_body HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: 0\n"
             "\n"
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        content_length = int(headers.get('content-length')) or None
        self.assertEqual(content_length, 9)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')
        self.assertEqual(content_length, len(response_body))
        self.assertEqual(response_body, tobytes('abcdefghi'))
        # remote does not close connection (keepalive header)
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')

    def test_no_content_length(self):
        # wtf happens when there's no content-length
        to_send = tobytes(
            "GET /no_content_length HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: 0\n"
             "\n"
             )
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line = fp.readline() # status line
        line, headers, response_body = read_http(fp)
        content_length = headers.get('content-length')
        self.assertEqual(content_length, None)
        self.assertEqual(response_body, tobytes('abcdefghi'))
        # remote closed connection (despite keepalive header); not sure why
        # first send succeeds
        self.assertRaises(ConnectionClosed, read_http, fp)

class TooLargeTests(SubprocessTests, unittest.TestCase):

    toobig = 1050

    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'toolarge.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()

    def test_request_body_too_large_with_wrong_cl_http10(self):
        body = 'a' * self.toobig
        to_send = ("GET / HTTP/1.0\n"
                   "Content-Length: 5\n\n")
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb')
        # first request succeeds (content-length 5)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # server trusts the content-length header; no pipelining,
        # so request fulfilled, extra bytes are thrown away
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_wrong_cl_http10_keepalive(self):
        body = 'a' * self.toobig
        to_send = ("GET / HTTP/1.0\n"
                   "Content-Length: 5\n"
                   "Connection: Keep-Alive\n\n")
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb')
        # first request succeeds (content-length 5)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        line, headers, response_body = read_http(fp)
        self.assertline(line, '431', 'Request Header Fields Too Large',
                        'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http10(self):
        body = 'a' * self.toobig
        to_send = "GET / HTTP/1.0\n\n"
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # extra bytes are thrown away (no pipelining), connection closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http10_keepalive(self):
        body = 'a' * self.toobig
        to_send = "GET / HTTP/1.0\nConnection: Keep-Alive\n\n"
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (assumed zero)
        self.assertline(line, '200', 'OK', 'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        line, headers, response_body = read_http(fp)
        # next response overruns because the extra data appears to be
        # header data
        self.assertline(line, '431', 'Request Header Fields Too Large',
                        'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_wrong_cl_http11(self):
        body = 'a' * self.toobig
        to_send = ("GET / HTTP/1.1\n"
                   "Content-Length: 5\n\n")
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb')
        # first request succeeds (content-length 5)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.1')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # second response is an error response
        line, headers, response_body = read_http(fp)
        self.assertline(line, '431', 'Request Header Fields Too Large', 
                             'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_wrong_cl_http11_connclose(self):
        body = 'a' * self.toobig
        to_send = "GET / HTTP/1.1\nContent-Length: 5\nConnection: close\n\n"
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (5)
        self.assertline(line, '200', 'OK', 'HTTP/1.1')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http11(self):
        body = 'a' * self.toobig
        to_send = "GET / HTTP/1.1\n\n"
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb')
        # server trusts the content-length header (assumed 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.1')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # server assumes pipelined requests due to http/1.1, and the first
        # request was assumed c-l 0 because it had no content-length header,
        # so entire body looks like the header of the subsequent request
        # second response is an error response
        line, headers, response_body = read_http(fp)
        self.assertline(line, '431', 'Request Header Fields Too Large', 
                             'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http11_connclose(self):
        body = 'a' * self.toobig
        to_send = "GET / HTTP/1.1\nConnection: close\n\n"
        to_send += body
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (assumed 0)
        self.assertline(line, '200', 'OK', 'HTTP/1.1')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_chunked_encoding(self):
        control_line = "20;\r\n"  # 20 hex = 32 dec
        s = 'This string has 32 characters.\r\n'
        to_send = "GET / HTTP/1.1\nTransfer-Encoding: chunked\n\n"
        repeat = control_line + s
        to_send += repeat * ((self.toobig // len(repeat)) + 1)
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        # body bytes counter caught a max_request_body_size overrun
        self.assertline(line, '413', 'Request Entity Too Large', 'HTTP/1.1')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        self.assertEqual(headers['content-type'], 'text/plain')
        self.assertEqual(headers['connection'], 'close')
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

class TestInternalServerError(SubprocessTests, unittest.TestCase):
    def setUp(self):
        echo = os.path.join(here, 'fixtureapps', 'error.py')
        self.start_subprocess([self.exe, echo])

    def tearDown(self):
        self.stop_subprocess()
    
    def test_before_start_response(self):
        to_send = "GET /before_start_response HTTP/1.1\n\n"
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '500', 'Internal Server Error', 'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b'Internal Server Error'))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_after_start_response(self):
        to_send = "GET /after_start_response HTTP/1.1\n\n"
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '500', 'Internal Server Error', 'HTTP/1.0')
        cl = int(headers['content-length'])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b'Internal Server Error'))
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_after_write_cb(self):
        to_send = "GET /after_write_cb HTTP/1.1\n\n"
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.1')
        self.assertEqual(response_body, b'')
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_in_generator(self):
        to_send = "GET /in_generator HTTP/1.1\n\n"
        to_send = tobytes(to_send)
        self.sock.connect((self.host, self.port))
        self.sock.send(to_send)
        fp = self.sock.makefile('rb', 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, '200', 'OK', 'HTTP/1.1')
        self.assertEqual(response_body, b'')
        # connection has been closed
        self.assertRaises(ConnectionClosed, read_http, fp)

def parse_headers(fp):
    """Parses only RFC2822 headers from a file pointer.
    """
    headers = {}
    while True:
        line = fp.readline()
        if line in (b'\r\n', b'\n', b''):
            break
        line = line.decode('iso-8859-1')
        name, value = line.strip().split(':', 1)
        headers[name.lower().strip()] = value.lower().strip()
    return headers

class ConnectionClosed(Exception):
    pass

# stolen from gevent
def read_http(fp): # pragma: no cover
    try:
        response_line = fp.readline()
    except socket.error as exc:
        if get_errno(exc) == 10053:
            raise ConnectionClosed
        raise
    if not response_line:
        raise ConnectionClosed
  
    header_lines = []
    while True:
        line = fp.readline()
        if line in (b'\r\n', b'\n', b''):
            break
        else:
            header_lines.append(line)
    headers = dict()
    for x in header_lines:
        x = x.strip()
        if not x:
            continue
        key, value = x.split(b': ', 1)
        key = key.decode('iso-8859-1').lower()
        value = value.decode('iso-8859-1')
        assert key not in headers, "%s header duplicated" % key
        headers[key] = value
  
    if 'content-length' in headers:
        num = int(headers['content-length'])
        body = fp.read(num)
    else:
        # read until EOF
        body = fp.read()
  
    return response_line, headers, body

# stolen from gevent
def get_errno(exc): # pragma: no cover
    """ Get the error code out of socket.error objects.
    socket.error in <2.5 does not have errno attribute
    socket.error in 3.x does not allow indexing access
    e.args[0] works for all.
    There are cases when args[0] is not errno.
    i.e. http://bugs.python.org/issue6471
    Maybe there are cases when errno is set, but it is not the first argument?
    """
  
    try:
        if exc.errno is not None: return exc.errno
    except AttributeError:
        pass
    try:
        return exc.args[0]
    except IndexError:
        return None
