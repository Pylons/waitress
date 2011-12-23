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
        cwd = os.getcwd()
        os.chdir(dn(dn(here)))
        self.proc = subprocess.Popen(cmd)
        os.chdir(cwd)
        time.sleep(.2)
        if self.proc.returncode is not None:
            raise RuntimeError('%s didnt start' % str(cmd))
        self.conn = httplib.HTTPConnection('%s:%s' % (self.host, self.port))

    def stop_subprocess(self):
        time.sleep(.2)
        if self.proc.returncode is None:
            self.conn.close()
            self.proc.terminate()

    def getresponse(self, status=200):
        resp = self.conn.getresponse()
        self.assertEqual(resp.status, status)
        return resp

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
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        sock.send(s)
        response = httplib.HTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        length = int(response.getheader('Content-Length', '0'))
        response_body = response.read(length)
        self.failUnlessEqual(length, len(data))
        self.failUnlessEqual(response_body, tobytes(data))

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
            self.failUnlessEqual(response.status, 200)
            responses.append(response)
        for response in responses:
            response.read()

    def test_chunking_request_without_content(self):
        h = httplib.HTTPConnection(self.host, self.port)
        h.request("GET", "/", headers={"Accept": "text/plain",
                                       "Transfer-Encoding": "chunked"})
        h.send(b"0\r\n\r\n")
        response = h.getresponse()
        self.failUnlessEqual(int(response.status), 200)
        response_body = response.read()
        self.failUnlessEqual(response_body, b'')

    def test_chunking_request_with_content(self):
        control_line = b"20;\r\n"  # 20 hex = 32 dec
        s = b'This string has 32 characters.\r\n'
        expect = s * 12

        h = httplib.HTTPConnection(self.host, self.port)
        h.request("GET", "/", headers={"Accept": "text/plain",
                                       "Transfer-Encoding": "chunked"})
        for n in range(12):
            h.send(control_line)
            h.send(s)
        h.send(b"0\r\n\r\n")
        response = h.getresponse()
        self.failUnlessEqual(int(response.status), 200)
        response_body = response.read()
        self.failUnlessEqual(response_body, expect)

    def test_keepalive_http_10(self):
        # Handling of Keep-Alive within HTTP 1.0
        data = "Default: Don't keep me alive"
        s = tobytes(
            "GET / HTTP/1.0\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
             )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        sock.send(s)
        response = httplib.HTTPResponse(sock)
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
        s = tobytes(
            "GET / HTTP/1.0\n"
             "Connection: Keep-Alive\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
            )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        sock.send(s)
        response = httplib.HTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        connection = response.getheader('Connection', '')
        self.failUnlessEqual(connection, 'Keep-Alive')

    def test_keepalive_http_11(self):
        # Handling of Keep-Alive within HTTP 1.1

        # All connections are kept alive, unless stated otherwise
        data = "Default: Keep me alive"
        s = tobytes(
            "GET / HTTP/1.1\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        sock.send(s)
        response = httplib.HTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        self.failUnless(response.getheader('connection') != 'close')

        # Explicitly set keep-alive
        data = "Default: Keep me alive"
        s = tobytes(
            "GET / HTTP/1.1\n"
             "Connection: keep-alive\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
             )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        sock.send(s)
        response = httplib.HTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        self.failUnless(response.getheader('connection') != 'close')

        # specifying Connection: close explicitly
        data = "Don't keep me alive"
        s = tobytes(
            "GET / HTTP/1.1\n"
             "Connection: close\n"
             "Content-Length: %d\n"
             "\n"
             "%s" % (len(data), data)
             )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        sock.send(s)
        response = httplib.HTTPResponse(sock)
        response.begin()
        self.failUnlessEqual(int(response.status), 200)
        self.failUnlessEqual(response.getheader('connection'), 'close')

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

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        sock.send(to_send)
        for n in range(count):
            expect_body = tobytes("Response #%d\r\n" % (n + 1))
            response = httplib.HTTPResponse(sock)
            response.begin()
            self.failUnlessEqual(int(response.status), 200)
            length = int(response.getheader('Content-Length', '0'))
            response_body = response.read(length)
            self.failUnlessEqual(length, len(response_body))
            self.failUnlessEqual(response_body, expect_body)

