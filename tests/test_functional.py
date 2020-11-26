import errno
from http import client as httplib
import logging
import multiprocessing
import os
import signal
import socket
import string
import subprocess
import sys
import time
import unittest

from waitress import server
from waitress.compat import WIN
from waitress.utilities import cleanup_unix_socket

dn = os.path.dirname
here = dn(__file__)


class NullHandler(logging.Handler):  # pragma: no cover
    """A logging handler that swallows all emitted messages."""

    def emit(self, record):
        pass


def start_server(app, svr, queue, **kwargs):  # pragma: no cover
    """Run a fixture application."""
    logging.getLogger("waitress").addHandler(NullHandler())
    try_register_coverage()
    svr(app, queue, **kwargs).run()


def try_register_coverage():  # pragma: no cover
    # Hack around multiprocessing exiting early and not triggering coverage's
    # atexit handler by always registering a signal handler

    if "COVERAGE_PROCESS_START" in os.environ:

        def sigterm(*args):
            sys.exit(0)

        signal.signal(signal.SIGTERM, sigterm)


class FixtureTcpWSGIServer(server.TcpWSGIServer):
    """A version of TcpWSGIServer that relays back what it's bound to."""

    family = socket.AF_INET  # Testing

    def __init__(self, application, queue, **kw):  # pragma: no cover
        # Coverage doesn't see this as it's ran in a separate process.
        kw["port"] = 0  # Bind to any available port.
        super().__init__(application, **kw)
        host, port = self.socket.getsockname()

        if os.name == "nt":
            host = "127.0.0.1"
        queue.put((host, port))


class SubprocessTests:

    # For nose: all tests may be ran in separate processes.
    _multiprocess_can_split_ = True

    exe = sys.executable

    server = None

    def start_subprocess(self, target, **kw):
        # Spawn a server process.
        self.queue = multiprocessing.Queue()

        if "COVERAGE_RCFILE" in os.environ:
            os.environ["COVERAGE_PROCESS_START"] = os.environ["COVERAGE_RCFILE"]

        if not WIN:
            ctx = multiprocessing.get_context("fork")
        else:
            ctx = multiprocessing.get_context("spawn")

        self.proc = ctx.Process(
            target=start_server,
            args=(target, self.server, self.queue),
            kwargs=kw,
        )
        self.proc.start()

        if self.proc.exitcode is not None:  # pragma: no cover
            raise RuntimeError("%s didn't start" % str(target))
        # Get the socket the server is listening on.
        self.bound_to = self.queue.get(timeout=5)
        self.sock = self.create_socket()

    def stop_subprocess(self):
        if self.proc.exitcode is None:
            self.proc.terminate()
        self.sock.close()
        # This give us one FD back ...
        self.queue.close()
        self.proc.join()

    def assertline(self, line, status, reason, version):
        v, s, r = (x.strip() for x in line.split(None, 2))
        self.assertEqual(s, status.encode("latin-1"))
        self.assertEqual(r, reason.encode("latin-1"))
        self.assertEqual(v, version.encode("latin-1"))

    def create_socket(self):
        return socket.socket(self.server.family, socket.SOCK_STREAM)

    def connect(self):
        self.sock.connect(self.bound_to)

    def make_http_connection(self):
        raise NotImplementedError  # pragma: no cover

    def send_check_error(self, to_send):
        self.sock.send(to_send)


class TcpTests(SubprocessTests):

    server = FixtureTcpWSGIServer

    def make_http_connection(self):
        return httplib.HTTPConnection(*self.bound_to)


class SleepyThreadTests(TcpTests, unittest.TestCase):
    # test that sleepy thread doesnt block other requests

    def setUp(self):
        from tests.fixtureapps import sleepy

        self.start_subprocess(sleepy.app)

    def tearDown(self):
        self.stop_subprocess()

    def test_it(self):
        getline = os.path.join(here, "fixtureapps", "getline.py")
        cmds = (
            [self.exe, getline, "http://%s:%d/sleepy" % self.bound_to],
            [self.exe, getline, "http://%s:%d/" % self.bound_to],
        )
        r, w = os.pipe()
        procs = []

        for cmd in cmds:
            procs.append(subprocess.Popen(cmd, stdout=w))
        time.sleep(3)

        for proc in procs:
            if proc.returncode is not None:  # pragma: no cover
                proc.terminate()
            proc.wait()
        # the notsleepy response should always be first returned (it sleeps
        # for 2 seconds, then returns; the notsleepy response should be
        # processed in the meantime)
        result = os.read(r, 10000)
        os.close(r)
        os.close(w)
        self.assertEqual(result, b"notsleepy returnedsleepy returned")


class EchoTests:
    def setUp(self):
        from tests.fixtureapps import echo

        self.start_subprocess(
            echo.app,
            trusted_proxy="*",
            trusted_proxy_count=1,
            trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"},
            clear_untrusted_proxy_headers=True,
        )

    def tearDown(self):
        self.stop_subprocess()

    def _read_echo(self, fp):
        from tests.fixtureapps import echo

        line, headers, body = read_http(fp)

        return line, headers, echo.parse_response(body)

    def test_date_and_server(self):
        to_send = b"GET / HTTP/1.0\r\nContent-Length: 0\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(headers.get("server"), "waitress")
        self.assertTrue(headers.get("date"))

    def test_bad_host_header(self):
        # https://corte.si/posts/code/pathod/pythonservers/index.html
        to_send = b"GET / HTTP/1.0\r\n Host: 0\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "400", "Bad Request", "HTTP/1.0")
        self.assertEqual(headers.get("server"), "waitress")
        self.assertTrue(headers.get("date"))

    def test_send_with_body(self):
        to_send = b"GET / HTTP/1.0\r\nContent-Length: 5\r\n\r\n"
        to_send += b"hello"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(echo.content_length, "5")
        self.assertEqual(echo.body, b"hello")

    def test_send_empty_body(self):
        to_send = b"GET / HTTP/1.0\r\nContent-Length: 0\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(echo.content_length, "0")
        self.assertEqual(echo.body, b"")

    def test_multiple_requests_with_body(self):
        orig_sock = self.sock

        for x in range(3):
            self.sock = self.create_socket()
            self.test_send_with_body()
            self.sock.close()
        self.sock = orig_sock

    def test_multiple_requests_without_body(self):
        orig_sock = self.sock

        for x in range(3):
            self.sock = self.create_socket()
            self.test_send_empty_body()
            self.sock.close()
        self.sock = orig_sock

    def test_without_crlf(self):
        data = b"Echo\r\nthis\r\nplease"
        s = (
            b"GET / HTTP/1.0\r\n"
            b"Connection: close\r\n"
            b"Content-Length: %d\r\n"
            b"\r\n"
            b"%s" % (len(data), data)
        )
        self.connect()
        self.sock.send(s)
        fp = self.sock.makefile("rb", 0)
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(int(echo.content_length), len(data))
        self.assertEqual(len(echo.body), len(data))
        self.assertEqual(echo.body, (data))

    def test_large_body(self):
        # 1024 characters.
        body = b"This string has 32 characters.\r\n" * 32
        s = b"GET / HTTP/1.0\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
        self.connect()
        self.sock.send(s)
        fp = self.sock.makefile("rb", 0)
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(echo.content_length, "1024")
        self.assertEqual(echo.body, body)

    def test_many_clients(self):
        conns = []

        for n in range(50):
            h = self.make_http_connection()
            h.request("GET", "/", headers={"Accept": "text/plain"})
            conns.append(h)
        responses = []

        for h in conns:
            response = h.getresponse()
            self.assertEqual(response.status, 200)
            responses.append(response)

        for response in responses:
            response.read()

        for h in conns:
            h.close()

    def test_chunking_request_without_content(self):
        header = b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"
        self.connect()
        self.sock.send(header)
        self.sock.send(b"0\r\n\r\n")
        fp = self.sock.makefile("rb", 0)
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        self.assertEqual(echo.body, b"")
        self.assertEqual(echo.content_length, "0")
        self.assertFalse("transfer-encoding" in headers)

    def test_chunking_request_with_content(self):
        control_line = b"20;\r\n"  # 20 hex = 32 dec
        s = b"This string has 32 characters.\r\n"
        expected = s * 12
        header = b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"
        self.connect()
        self.sock.send(header)
        fp = self.sock.makefile("rb", 0)

        for n in range(12):
            self.sock.send(control_line)
            self.sock.send(s)
            self.sock.send(b"\r\n")  # End the chunk
        self.sock.send(b"0\r\n\r\n")
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        self.assertEqual(echo.body, expected)
        self.assertEqual(echo.content_length, str(len(expected)))
        self.assertFalse("transfer-encoding" in headers)

    def test_broken_chunked_encoding(self):
        control_line = b"20;\r\n"  # 20 hex = 32 dec
        s = b"This string has 32 characters.\r\n"
        to_send = b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"
        to_send += control_line + s + b"\r\n"
        # garbage in input
        to_send += b"garbage\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        # receiver caught garbage and turned it into a 400
        self.assertline(line, "400", "Bad Request", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertEqual(
            sorted(headers.keys()),
            ["connection", "content-length", "content-type", "date", "server"],
        )
        self.assertEqual(headers["content-type"], "text/plain")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_broken_chunked_encoding_missing_chunk_end(self):
        control_line = b"20;\r\n"  # 20 hex = 32 dec
        s = b"This string has 32 characters.\r\n"
        to_send = b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"
        to_send += control_line + s
        # garbage in input
        to_send += b"garbage"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        # receiver caught garbage and turned it into a 400
        self.assertline(line, "400", "Bad Request", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(b"Chunk not properly terminated" in response_body)
        self.assertEqual(
            sorted(headers.keys()),
            ["connection", "content-length", "content-type", "date", "server"],
        )
        self.assertEqual(headers["content-type"], "text/plain")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_keepalive_http_10(self):
        # Handling of Keep-Alive within HTTP 1.0
        data = b"Default: Don't keep me alive"
        s = b"GET / HTTP/1.0\r\nContent-Length: %d\r\n\r\n%s" % (len(data), data)
        self.connect()
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        connection = response.getheader("Connection", "")
        # We sent no Connection: Keep-Alive header
        # Connection: close (or no header) is default.
        self.assertTrue(connection != "Keep-Alive")

    def test_keepalive_http10_explicit(self):
        # If header Connection: Keep-Alive is explicitly sent,
        # we want to keept the connection open, we also need to return
        # the corresponding header
        data = b"Keep me alive"
        s = (
            b"GET / HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: %d\r\n"
            b"\r\n"
            b"%s" % (len(data), data)
        )
        self.connect()
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        connection = response.getheader("Connection", "")
        self.assertEqual(connection, "Keep-Alive")

    def test_keepalive_http_11(self):
        # Handling of Keep-Alive within HTTP 1.1

        # All connections are kept alive, unless stated otherwise
        data = b"Default: Keep me alive"
        s = b"GET / HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(data), data)
        self.connect()
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        self.assertTrue(response.getheader("connection") != "close")

    def test_keepalive_http11_explicit(self):
        # Explicitly set keep-alive
        data = b"Default: Keep me alive"
        s = (
            b"GET / HTTP/1.1\r\n"
            b"Connection: keep-alive\r\n"
            b"Content-Length: %d\r\n"
            b"\r\n"
            b"%s" % (len(data), data)
        )
        self.connect()
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        self.assertTrue(response.getheader("connection") != "close")

    def test_keepalive_http11_connclose(self):
        # specifying Connection: close explicitly
        data = b"Don't keep me alive"
        s = (
            b"GET / HTTP/1.1\r\n"
            b"Connection: close\r\n"
            b"Content-Length: %d\r\n"
            b"\r\n"
            b"%s" % (len(data), data)
        )
        self.connect()
        self.sock.send(s)
        response = httplib.HTTPResponse(self.sock)
        response.begin()
        self.assertEqual(int(response.status), 200)
        self.assertEqual(response.getheader("connection"), "close")

    def test_proxy_headers(self):
        to_send = (
            b"GET / HTTP/1.0\r\n"
            b"Content-Length: 0\r\n"
            b"Host: www.google.com:8080\r\n"
            b"X-Forwarded-For: 192.168.1.1\r\n"
            b"X-Forwarded-Proto: https\r\n"
            b"X-Forwarded-Port: 5000\r\n\r\n"
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, echo = self._read_echo(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(headers.get("server"), "waitress")
        self.assertTrue(headers.get("date"))
        self.assertIsNone(echo.headers.get("X_FORWARDED_PORT"))
        self.assertEqual(echo.headers["HOST"], "www.google.com:8080")
        self.assertEqual(echo.scheme, "https")
        self.assertEqual(echo.remote_addr, "192.168.1.1")
        self.assertEqual(echo.remote_host, "192.168.1.1")


class PipeliningTests:
    def setUp(self):
        from tests.fixtureapps import echo

        self.start_subprocess(echo.app_body_only)

    def tearDown(self):
        self.stop_subprocess()

    def test_pipelining(self):
        s = (
            b"GET / HTTP/1.0\r\n"
            b"Connection: %s\r\n"
            b"Content-Length: %d\r\n"
            b"\r\n"
            b"%s"
        )
        to_send = b""
        count = 25

        for n in range(count):
            body = b"Response #%d\r\n" % (n + 1)

            if n + 1 < count:
                conn = b"keep-alive"
            else:
                conn = b"close"
            to_send += s % (conn, len(body), body)

        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)

        for n in range(count):
            expect_body = b"Response #%d\r\n" % (n + 1)
            line = fp.readline()  # status line
            version, status, reason = (x.strip() for x in line.split(None, 2))
            headers = parse_headers(fp)
            length = int(headers.get("content-length")) or None
            response_body = fp.read(length)
            self.assertEqual(int(status), 200)
            self.assertEqual(length, len(response_body))
            self.assertEqual(response_body, expect_body)


class ExpectContinueTests:
    def setUp(self):
        from tests.fixtureapps import echo

        self.start_subprocess(echo.app_body_only)

    def tearDown(self):
        self.stop_subprocess()

    def test_expect_continue(self):
        # specifying Connection: close explicitly
        data = b"I have expectations"
        to_send = (
            b"GET / HTTP/1.1\r\n"
            b"Connection: close\r\n"
            b"Content-Length: %d\r\n"
            b"Expect: 100-continue\r\n"
            b"\r\n"
            b"%s" % (len(data), data)
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line = fp.readline()  # continue status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        self.assertEqual(int(status), 100)
        self.assertEqual(reason, b"Continue")
        self.assertEqual(version, b"HTTP/1.1")
        fp.readline()  # blank line
        line = fp.readline()  # next status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        length = int(headers.get("content-length")) or None
        response_body = fp.read(length)
        self.assertEqual(int(status), 200)
        self.assertEqual(length, len(response_body))
        self.assertEqual(response_body, data)


class BadContentLengthTests:
    def setUp(self):
        from tests.fixtureapps import badcl

        self.start_subprocess(badcl.app)

    def tearDown(self):
        self.stop_subprocess()

    def test_short_body(self):
        # check to see if server closes connection when body is too short
        # for cl header
        to_send = (
            b"GET /short_body HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line = fp.readline()  # status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        content_length = int(headers.get("content-length"))
        response_body = fp.read(content_length)
        self.assertEqual(int(status), 200)
        self.assertNotEqual(content_length, len(response_body))
        self.assertEqual(len(response_body), content_length - 1)
        self.assertEqual(response_body, b"abcdefghi")
        # remote closed connection (despite keepalive header); not sure why
        # first send succeeds
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_long_body(self):
        # check server doesnt close connection when body is too short
        # for cl header
        to_send = (
            b"GET /long_body HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line = fp.readline()  # status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        content_length = int(headers.get("content-length")) or None
        response_body = fp.read(content_length)
        self.assertEqual(int(status), 200)
        self.assertEqual(content_length, len(response_body))
        self.assertEqual(response_body, b"abcdefgh")
        # remote does not close connection (keepalive header)
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line = fp.readline()  # status line
        version, status, reason = (x.strip() for x in line.split(None, 2))
        headers = parse_headers(fp)
        content_length = int(headers.get("content-length")) or None
        response_body = fp.read(content_length)
        self.assertEqual(int(status), 200)


class NoContentLengthTests:
    def setUp(self):
        from tests.fixtureapps import nocl

        self.start_subprocess(nocl.app)

    def tearDown(self):
        self.stop_subprocess()

    def test_http10_generator(self):
        body = string.ascii_letters.encode("latin-1")
        to_send = (
            b"GET / HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: %d\r\n\r\n" % len(body)
        )
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(headers.get("content-length"), None)
        self.assertEqual(headers.get("connection"), "close")
        self.assertEqual(response_body, body)
        # remote closed connection (despite keepalive header), because
        # generators cannot have a content-length divined
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_http10_list(self):
        body = string.ascii_letters.encode("latin-1")
        to_send = (
            b"GET /list HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: %d\r\n\r\n" % len(body)
        )
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(headers["content-length"], str(len(body)))
        self.assertEqual(headers.get("connection"), "Keep-Alive")
        self.assertEqual(response_body, body)
        # remote keeps connection open because it divined the content length
        # from a length-1 list
        self.sock.send(to_send)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")

    def test_http10_listlentwo(self):
        body = string.ascii_letters.encode("latin-1")
        to_send = (
            b"GET /list_lentwo HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: %d\r\n\r\n" % len(body)
        )
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(headers.get("content-length"), None)
        self.assertEqual(headers.get("connection"), "close")
        self.assertEqual(response_body, body)
        # remote closed connection (despite keepalive header), because
        # lists of length > 1 cannot have their content length divined
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_http11_generator(self):
        body = string.ascii_letters
        body = body.encode("latin-1")
        to_send = b"GET / HTTP/1.1\r\nContent-Length: %d\r\n\r\n" % len(body)
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb")
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        expected = b""

        for chunk in chunks(body, 10):
            expected += b"%s\r\n%s\r\n" % (
                hex(len(chunk))[2:].upper().encode("latin-1"),
                chunk,
            )
        expected += b"0\r\n\r\n"
        self.assertEqual(response_body, expected)
        # connection is always closed at the end of a chunked response
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_http11_list(self):
        body = string.ascii_letters.encode("latin-1")
        to_send = b"GET /list HTTP/1.1\r\nContent-Length: %d\r\n\r\n" % len(body)
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        self.assertEqual(headers["content-length"], str(len(body)))
        self.assertEqual(response_body, body)
        # remote keeps connection open because it divined the content length
        # from a length-1 list
        self.sock.send(to_send)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")

    def test_http11_listlentwo(self):
        body = string.ascii_letters.encode("latin-1")
        to_send = b"GET /list_lentwo HTTP/1.1\r\nContent-Length: %d\r\n\r\n" % len(body)
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb")
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        expected = b""

        for chunk in (body[:1], body[1:]):
            expected += b"%s\r\n%s\r\n" % (
                (hex(len(chunk))[2:].upper().encode("latin-1")),
                chunk,
            )
        expected += b"0\r\n\r\n"
        self.assertEqual(response_body, expected)
        # connection is always closed at the end of a chunked response
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)


class WriteCallbackTests:
    def setUp(self):
        from tests.fixtureapps import writecb

        self.start_subprocess(writecb.app)

    def tearDown(self):
        self.stop_subprocess()

    def test_short_body(self):
        # check to see if server closes connection when body is too short
        # for cl header
        to_send = (
            b"GET /short_body HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (5)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, 9)
        self.assertNotEqual(cl, len(response_body))
        self.assertEqual(len(response_body), cl - 1)
        self.assertEqual(response_body, b"abcdefgh")
        # remote closed connection (despite keepalive header)
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_long_body(self):
        # check server doesnt close connection when body is too long
        # for cl header
        to_send = (
            b"GET /long_body HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        content_length = int(headers.get("content-length")) or None
        self.assertEqual(content_length, 9)
        self.assertEqual(content_length, len(response_body))
        self.assertEqual(response_body, b"abcdefghi")
        # remote does not close connection (keepalive header)
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")

    def test_equal_body(self):
        # check server doesnt close connection when body is equal to
        # cl header
        to_send = (
            b"GET /equal_body HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        content_length = int(headers.get("content-length")) or None
        self.assertEqual(content_length, 9)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        self.assertEqual(content_length, len(response_body))
        self.assertEqual(response_body, b"abcdefghi")
        # remote does not close connection (keepalive header)
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")

    def test_no_content_length(self):
        # wtf happens when there's no content-length
        to_send = (
            b"GET /no_content_length HTTP/1.0\r\n"
            b"Connection: Keep-Alive\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line = fp.readline()  # status line
        line, headers, response_body = read_http(fp)
        content_length = headers.get("content-length")
        self.assertEqual(content_length, None)
        self.assertEqual(response_body, b"abcdefghi")
        # remote closed connection (despite keepalive header)
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)


class TooLargeTests:

    toobig = 1050

    def setUp(self):
        from tests.fixtureapps import toolarge

        self.start_subprocess(
            toolarge.app, max_request_header_size=1000, max_request_body_size=1000
        )

    def tearDown(self):
        self.stop_subprocess()

    def test_request_headers_too_large_http11(self):
        body = b""
        bad_headers = b"X-Random-Header: 100\r\n" * int(self.toobig / 20)
        to_send = b"GET / HTTP/1.1\r\nContent-Length: 0\r\n"
        to_send += bad_headers
        to_send += b"\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb")
        response_line, headers, response_body = read_http(fp)
        self.assertline(
            response_line, "431", "Request Header Fields Too Large", "HTTP/1.0"
        )
        self.assertEqual(headers["connection"], "close")

    def test_request_body_too_large_with_wrong_cl_http10(self):
        body = b"a" * self.toobig
        to_send = b"GET / HTTP/1.0\r\nContent-Length: 5\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb")
        # first request succeeds (content-length 5)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # server trusts the content-length header; no pipelining,
        # so request fulfilled, extra bytes are thrown away
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_wrong_cl_http10_keepalive(self):
        body = b"a" * self.toobig
        to_send = (
            b"GET / HTTP/1.0\r\nContent-Length: 5\r\nConnection: Keep-Alive\r\n\r\n"
        )
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb")
        # first request succeeds (content-length 5)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        line, headers, response_body = read_http(fp)
        self.assertline(line, "431", "Request Header Fields Too Large", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http10(self):
        body = b"a" * self.toobig
        to_send = b"GET / HTTP/1.0\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # extra bytes are thrown away (no pipelining), connection closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http10_keepalive(self):
        body = b"a" * self.toobig
        to_send = b"GET / HTTP/1.0\r\nConnection: Keep-Alive\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (assumed zero)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        line, headers, response_body = read_http(fp)
        # next response overruns because the extra data appears to be
        # header data
        self.assertline(line, "431", "Request Header Fields Too Large", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_wrong_cl_http11(self):
        body = b"a" * self.toobig
        to_send = b"GET / HTTP/1.1\r\nContent-Length: 5\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb")
        # first request succeeds (content-length 5)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # second response is an error response
        line, headers, response_body = read_http(fp)
        self.assertline(line, "431", "Request Header Fields Too Large", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_wrong_cl_http11_connclose(self):
        body = b"a" * self.toobig
        to_send = b"GET / HTTP/1.1\r\nContent-Length: 5\r\nConnection: close\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (5)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http11(self):
        body = b"a" * self.toobig
        to_send = b"GET / HTTP/1.1\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb")
        # server trusts the content-length header (assumed 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # server assumes pipelined requests due to http/1.1, and the first
        # request was assumed c-l 0 because it had no content-length header,
        # so entire body looks like the header of the subsequent request
        # second response is an error response
        line, headers, response_body = read_http(fp)
        self.assertline(line, "431", "Request Header Fields Too Large", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_with_no_cl_http11_connclose(self):
        body = b"a" * self.toobig
        to_send = b"GET / HTTP/1.1\r\nConnection: close\r\n\r\n"
        to_send += body
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        # server trusts the content-length header (assumed 0)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_request_body_too_large_chunked_encoding(self):
        control_line = b"20;\r\n"  # 20 hex = 32 dec
        s = b"This string has 32 characters.\r\n"
        to_send = b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"
        repeat = control_line + s
        to_send += repeat * ((self.toobig // len(repeat)) + 1)
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        # body bytes counter caught a max_request_body_size overrun
        self.assertline(line, "413", "Request Entity Too Large", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertEqual(headers["content-type"], "text/plain")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)


class InternalServerErrorTests:
    def setUp(self):
        from tests.fixtureapps import error

        self.start_subprocess(error.app, expose_tracebacks=True)

    def tearDown(self):
        self.stop_subprocess()

    def test_before_start_response_http_10(self):
        to_send = b"GET /before_start_response HTTP/1.0\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "500", "Internal Server Error", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b"Internal Server Error"))
        self.assertEqual(headers["connection"], "close")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_before_start_response_http_11(self):
        to_send = b"GET /before_start_response HTTP/1.1\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "500", "Internal Server Error", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b"Internal Server Error"))
        self.assertEqual(
            sorted(headers.keys()),
            ["connection", "content-length", "content-type", "date", "server"],
        )
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_before_start_response_http_11_close(self):
        to_send = b"GET /before_start_response HTTP/1.1\r\nConnection: close\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "500", "Internal Server Error", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b"Internal Server Error"))
        self.assertEqual(
            sorted(headers.keys()),
            ["connection", "content-length", "content-type", "date", "server"],
        )
        self.assertEqual(headers["connection"], "close")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_after_start_response_http10(self):
        to_send = b"GET /after_start_response HTTP/1.0\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "500", "Internal Server Error", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b"Internal Server Error"))
        self.assertEqual(
            sorted(headers.keys()),
            ["connection", "content-length", "content-type", "date", "server"],
        )
        self.assertEqual(headers["connection"], "close")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_after_start_response_http11(self):
        to_send = b"GET /after_start_response HTTP/1.1\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "500", "Internal Server Error", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b"Internal Server Error"))
        self.assertEqual(
            sorted(headers.keys()),
            ["connection", "content-length", "content-type", "date", "server"],
        )
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_after_start_response_http11_close(self):
        to_send = b"GET /after_start_response HTTP/1.1\r\nConnection: close\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "500", "Internal Server Error", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        self.assertTrue(response_body.startswith(b"Internal Server Error"))
        self.assertEqual(
            sorted(headers.keys()),
            ["connection", "content-length", "content-type", "date", "server"],
        )
        self.assertEqual(headers["connection"], "close")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_after_write_cb(self):
        to_send = b"GET /after_write_cb HTTP/1.1\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        self.assertEqual(response_body, b"")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_in_generator(self):
        to_send = b"GET /in_generator HTTP/1.1\r\n\r\n"
        self.connect()
        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        self.assertEqual(response_body, b"")
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)


class FileWrapperTests:
    def setUp(self):
        from tests.fixtureapps import filewrapper

        self.start_subprocess(filewrapper.app)

    def tearDown(self):
        self.stop_subprocess()

    def test_filelike_http11(self):
        to_send = b"GET /filelike HTTP/1.1\r\n\r\n"

        self.connect()

        for t in range(0, 2):
            self.sock.send(to_send)
            fp = self.sock.makefile("rb", 0)
            line, headers, response_body = read_http(fp)
            self.assertline(line, "200", "OK", "HTTP/1.1")
            cl = int(headers["content-length"])
            self.assertEqual(cl, len(response_body))
            ct = headers["content-type"]
            self.assertEqual(ct, "image/jpeg")
            self.assertTrue(b"\377\330\377" in response_body)
            # connection has not been closed

    def test_filelike_nocl_http11(self):
        to_send = b"GET /filelike_nocl HTTP/1.1\r\n\r\n"

        self.connect()

        for t in range(0, 2):
            self.sock.send(to_send)
            fp = self.sock.makefile("rb", 0)
            line, headers, response_body = read_http(fp)
            self.assertline(line, "200", "OK", "HTTP/1.1")
            cl = int(headers["content-length"])
            self.assertEqual(cl, len(response_body))
            ct = headers["content-type"]
            self.assertEqual(ct, "image/jpeg")
            self.assertTrue(b"\377\330\377" in response_body)
            # connection has not been closed

    def test_filelike_shortcl_http11(self):
        to_send = b"GET /filelike_shortcl HTTP/1.1\r\n\r\n"

        self.connect()

        for t in range(0, 2):
            self.sock.send(to_send)
            fp = self.sock.makefile("rb", 0)
            line, headers, response_body = read_http(fp)
            self.assertline(line, "200", "OK", "HTTP/1.1")
            cl = int(headers["content-length"])
            self.assertEqual(cl, 1)
            self.assertEqual(cl, len(response_body))
            ct = headers["content-type"]
            self.assertEqual(ct, "image/jpeg")
            self.assertTrue(b"\377" in response_body)
            # connection has not been closed

    def test_filelike_longcl_http11(self):
        to_send = b"GET /filelike_longcl HTTP/1.1\r\n\r\n"

        self.connect()

        for t in range(0, 2):
            self.sock.send(to_send)
            fp = self.sock.makefile("rb", 0)
            line, headers, response_body = read_http(fp)
            self.assertline(line, "200", "OK", "HTTP/1.1")
            cl = int(headers["content-length"])
            self.assertEqual(cl, len(response_body))
            ct = headers["content-type"]
            self.assertEqual(ct, "image/jpeg")
            self.assertTrue(b"\377\330\377" in response_body)
            # connection has not been closed

    def test_notfilelike_http11(self):
        to_send = b"GET /notfilelike HTTP/1.1\r\n\r\n"

        self.connect()

        for t in range(0, 2):
            self.sock.send(to_send)
            fp = self.sock.makefile("rb", 0)
            line, headers, response_body = read_http(fp)
            self.assertline(line, "200", "OK", "HTTP/1.1")
            cl = int(headers["content-length"])
            self.assertEqual(cl, len(response_body))
            ct = headers["content-type"]
            self.assertEqual(ct, "image/jpeg")
            self.assertTrue(b"\377\330\377" in response_body)
            # connection has not been closed

    def test_notfilelike_iobase_http11(self):
        to_send = b"GET /notfilelike_iobase HTTP/1.1\r\n\r\n"

        self.connect()

        for t in range(0, 2):
            self.sock.send(to_send)
            fp = self.sock.makefile("rb", 0)
            line, headers, response_body = read_http(fp)
            self.assertline(line, "200", "OK", "HTTP/1.1")
            cl = int(headers["content-length"])
            self.assertEqual(cl, len(response_body))
            ct = headers["content-type"]
            self.assertEqual(ct, "image/jpeg")
            self.assertTrue(b"\377\330\377" in response_body)
            # connection has not been closed

    def test_notfilelike_nocl_http11(self):
        to_send = b"GET /notfilelike_nocl HTTP/1.1\r\n\r\n"

        self.connect()

        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        ct = headers["content-type"]
        self.assertEqual(ct, "image/jpeg")
        self.assertTrue(b"\377\330\377" in response_body)
        # connection has been closed (no content-length)
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_notfilelike_shortcl_http11(self):
        to_send = b"GET /notfilelike_shortcl HTTP/1.1\r\n\r\n"

        self.connect()

        for t in range(0, 2):
            self.sock.send(to_send)
            fp = self.sock.makefile("rb", 0)
            line, headers, response_body = read_http(fp)
            self.assertline(line, "200", "OK", "HTTP/1.1")
            cl = int(headers["content-length"])
            self.assertEqual(cl, 1)
            self.assertEqual(cl, len(response_body))
            ct = headers["content-type"]
            self.assertEqual(ct, "image/jpeg")
            self.assertTrue(b"\377" in response_body)
            # connection has not been closed

    def test_notfilelike_longcl_http11(self):
        to_send = b"GET /notfilelike_longcl HTTP/1.1\r\n\r\n"

        self.connect()

        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.1")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body) + 10)
        ct = headers["content-type"]
        self.assertEqual(ct, "image/jpeg")
        self.assertTrue(b"\377\330\377" in response_body)
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_filelike_http10(self):
        to_send = b"GET /filelike HTTP/1.0\r\n\r\n"

        self.connect()

        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        ct = headers["content-type"]
        self.assertEqual(ct, "image/jpeg")
        self.assertTrue(b"\377\330\377" in response_body)
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_filelike_nocl_http10(self):
        to_send = b"GET /filelike_nocl HTTP/1.0\r\n\r\n"

        self.connect()

        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        ct = headers["content-type"]
        self.assertEqual(ct, "image/jpeg")
        self.assertTrue(b"\377\330\377" in response_body)
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_notfilelike_http10(self):
        to_send = b"GET /notfilelike HTTP/1.0\r\n\r\n"

        self.connect()

        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        cl = int(headers["content-length"])
        self.assertEqual(cl, len(response_body))
        ct = headers["content-type"]
        self.assertEqual(ct, "image/jpeg")
        self.assertTrue(b"\377\330\377" in response_body)
        # connection has been closed
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)

    def test_notfilelike_nocl_http10(self):
        to_send = b"GET /notfilelike_nocl HTTP/1.0\r\n\r\n"

        self.connect()

        self.sock.send(to_send)
        fp = self.sock.makefile("rb", 0)
        line, headers, response_body = read_http(fp)
        self.assertline(line, "200", "OK", "HTTP/1.0")
        ct = headers["content-type"]
        self.assertEqual(ct, "image/jpeg")
        self.assertTrue(b"\377\330\377" in response_body)
        # connection has been closed (no content-length)
        self.send_check_error(to_send)
        self.assertRaises(ConnectionClosed, read_http, fp)


class TcpEchoTests(EchoTests, TcpTests, unittest.TestCase):
    pass


class TcpPipeliningTests(PipeliningTests, TcpTests, unittest.TestCase):
    pass


class TcpExpectContinueTests(ExpectContinueTests, TcpTests, unittest.TestCase):
    pass


class TcpBadContentLengthTests(BadContentLengthTests, TcpTests, unittest.TestCase):
    pass


class TcpNoContentLengthTests(NoContentLengthTests, TcpTests, unittest.TestCase):
    pass


class TcpWriteCallbackTests(WriteCallbackTests, TcpTests, unittest.TestCase):
    pass


class TcpTooLargeTests(TooLargeTests, TcpTests, unittest.TestCase):
    pass


class TcpInternalServerErrorTests(
    InternalServerErrorTests, TcpTests, unittest.TestCase
):
    pass


class TcpFileWrapperTests(FileWrapperTests, TcpTests, unittest.TestCase):
    pass


if hasattr(socket, "AF_UNIX"):

    class FixtureUnixWSGIServer(server.UnixWSGIServer):
        """A version of UnixWSGIServer that relays back what it's bound to."""

        family = socket.AF_UNIX  # Testing

        def __init__(self, application, queue, **kw):  # pragma: no cover
            # Coverage doesn't see this as it's ran in a separate process.
            # To permit parallel testing, use a PID-dependent socket.
            kw["unix_socket"] = "/tmp/waitress.test-%d.sock" % os.getpid()
            super().__init__(application, **kw)
            queue.put(self.socket.getsockname())

    class UnixTests(SubprocessTests):

        server = FixtureUnixWSGIServer

        def make_http_connection(self):
            return UnixHTTPConnection(self.bound_to)

        def stop_subprocess(self):
            super().stop_subprocess()
            cleanup_unix_socket(self.bound_to)

        def send_check_error(self, to_send):
            # Unlike inet domain sockets, Unix domain sockets can trigger a
            # 'Broken pipe' error when the socket it closed.
            try:
                self.sock.send(to_send)
            except OSError as exc:
                valid_errors = {errno.EPIPE, errno.ENOTCONN}
                self.assertIn(get_errno(exc), valid_errors)

    class UnixEchoTests(EchoTests, UnixTests, unittest.TestCase):
        pass

    class UnixPipeliningTests(PipeliningTests, UnixTests, unittest.TestCase):
        pass

    class UnixExpectContinueTests(ExpectContinueTests, UnixTests, unittest.TestCase):
        pass

    class UnixBadContentLengthTests(
        BadContentLengthTests, UnixTests, unittest.TestCase
    ):
        pass

    class UnixNoContentLengthTests(NoContentLengthTests, UnixTests, unittest.TestCase):
        pass

    class UnixWriteCallbackTests(WriteCallbackTests, UnixTests, unittest.TestCase):
        pass

    class UnixTooLargeTests(TooLargeTests, UnixTests, unittest.TestCase):
        pass

    class UnixInternalServerErrorTests(
        InternalServerErrorTests, UnixTests, unittest.TestCase
    ):
        pass

    class UnixFileWrapperTests(FileWrapperTests, UnixTests, unittest.TestCase):
        pass


def parse_headers(fp):
    """Parses only RFC2822 headers from a file pointer."""
    headers = {}

    while True:
        line = fp.readline()

        if line in (b"\r\n", b"\n", b""):
            break
        line = line.decode("iso-8859-1")
        name, value = line.strip().split(":", 1)
        headers[name.lower().strip()] = value.lower().strip()

    return headers


class UnixHTTPConnection(httplib.HTTPConnection):
    """Patched version of HTTPConnection that uses Unix domain sockets."""

    def __init__(self, path):
        httplib.HTTPConnection.__init__(self, "localhost")
        self.path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.path)
        self.sock = sock


class ConnectionClosed(Exception):
    pass


# stolen from gevent
def read_http(fp):  # pragma: no cover
    try:
        response_line = fp.readline()
    except OSError as exc:
        fp.close()
        # errno 104 is ENOTRECOVERABLE, In WinSock 10054 is ECONNRESET

        if get_errno(exc) in (errno.ECONNABORTED, errno.ECONNRESET, 104, 10054):
            raise ConnectionClosed
        raise

    if not response_line:
        raise ConnectionClosed

    header_lines = []

    while True:
        line = fp.readline()

        if line in (b"\r\n", b"\r\n", b""):
            break
        else:
            header_lines.append(line)
    headers = dict()

    for x in header_lines:
        x = x.strip()

        if not x:
            continue
        key, value = x.split(b": ", 1)
        key = key.decode("iso-8859-1").lower()
        value = value.decode("iso-8859-1")
        assert key not in headers, "%s header duplicated" % key
        headers[key] = value

    if "content-length" in headers:
        num = int(headers["content-length"])
        body = b""
        left = num

        while left > 0:
            data = fp.read(left)

            if not data:
                break
            body += data
            left -= len(data)
    else:
        # read until EOF
        body = fp.read()

    return response_line, headers, body


# stolen from gevent
def get_errno(exc):  # pragma: no cover
    """Get the error code out of socket.error objects.
    socket.error in <2.5 does not have errno attribute
    socket.error in 3.x does not allow indexing access
    e.args[0] works for all.
    There are cases when args[0] is not errno.
    i.e. http://bugs.python.org/issue6471
    Maybe there are cases when errno is set, but it is not the first argument?
    """
    try:
        if exc.errno is not None:
            return exc.errno
    except AttributeError:
        pass
    try:
        return exc.args[0]
    except IndexError:
        return None


def chunks(l, n):
    """Yield successive n-sized chunks from l."""

    for i in range(0, len(l), n):
        yield l[i : i + n]
