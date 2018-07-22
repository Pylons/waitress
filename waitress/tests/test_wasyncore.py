from waitress import wasyncore as asyncore
from waitress import compat
import contextlib
import functools
import gc
import unittest
import select
import os
import socket
import sys
import time
import errno
import re
import struct
import threading
import warnings

from io import BytesIO

TIMEOUT = 3
HAS_UNIX_SOCKETS = hasattr(socket, 'AF_UNIX')
HOST = 'localhost'
HOSTv4 = "127.0.0.1"
HOSTv6 = "::1"

# Filename used for testing
if os.name == 'java':
    # Jython disallows @ in module names
    TESTFN = '$test'
else:
    TESTFN = '@test'

TESTFN = "{}_{}_tmp".format(TESTFN, os.getpid())

class DummyLogger(object):
    def __init__(self):
        self.messages = []

    def log(self, severity, message):
        self.messages.append((severity, message))

class WarningsRecorder(object):
    """Convenience wrapper for the warnings list returned on
       entry to the warnings.catch_warnings() context manager.
    """
    def __init__(self, warnings_list):
        self._warnings = warnings_list
        self._last = 0

    def __getattr__(self, attr):
        if len(self._warnings) > self._last:
            return getattr(self._warnings[-1], attr)
        elif attr in warnings.WarningMessage._WARNING_DETAILS:
            return None
        raise AttributeError("%r has no attribute %r" % (self, attr))

    @property
    def warnings(self):
        return self._warnings[self._last:]

    def reset(self):
        self._last = len(self._warnings)


def _filterwarnings(filters, quiet=False):
    """Catch the warnings, then check if all the expected
    warnings have been raised and re-raise unexpected warnings.
    If 'quiet' is True, only re-raise the unexpected warnings.
    """
    # Clear the warning registry of the calling module
    # in order to re-raise the warnings.
    frame = sys._getframe(2)
    registry = frame.f_globals.get('__warningregistry__')
    if registry:
        registry.clear()
    with warnings.catch_warnings(record=True) as w:
        # Set filter "always" to record all warnings.  Because
        # test_warnings swap the module, we need to look up in
        # the sys.modules dictionary.
        sys.modules['warnings'].simplefilter("always")
        yield WarningsRecorder(w)
    # Filter the recorded warnings
    reraise = list(w)
    missing = []
    for msg, cat in filters:
        seen = False
        for w in reraise[:]:
            warning = w.message
            # Filter out the matching messages
            if (re.match(msg, str(warning), re.I) and
                issubclass(warning.__class__, cat)):
                seen = True
                reraise.remove(w)
        if not seen and not quiet:
            # This filter caught nothing
            missing.append((msg, cat.__name__))
    if reraise:
        raise AssertionError("unhandled warning %s" % reraise[0])
    if missing:
        raise AssertionError("filter (%r, %s) did not catch any warning" %
                             missing[0])


@contextlib.contextmanager
def check_warnings(*filters, **kwargs):
    """Context manager to silence warnings.

    Accept 2-tuples as positional arguments:
        ("message regexp", WarningCategory)

    Optional argument:
     - if 'quiet' is True, it does not fail if a filter catches nothing
        (default True without argument,
         default False if some filters are defined)

    Without argument, it defaults to:
        check_warnings(("", Warning), quiet=True)
    """
    quiet = kwargs.get('quiet')
    if not filters:
        filters = (("", Warning),)
        # Preserve backward compatibility
        if quiet is None:
            quiet = True
    return _filterwarnings(filters, quiet)

def gc_collect():
    """Force as many objects as possible to be collected.

    In non-CPython implementations of Python, this is needed because timely
    deallocation is not guaranteed by the garbage collector.  (Even in CPython
    this can be the case in case of reference cycles.)  This means that __del__
    methods may be called later than expected and weakrefs may remain alive for
    longer than expected.  This function tries its best to force all garbage
    objects to disappear.
    """
    gc.collect()
    if sys.platform.startswith('java'):
        time.sleep(0.1)
    gc.collect()
    gc.collect()

def threading_setup():
    return (compat.thread._count(), None)

def threading_cleanup(*original_values):
    global environment_altered

    _MAX_COUNT = 100

    for count in range(_MAX_COUNT):
        values = (compat.thread._count(), None)
        if values == original_values:
            break

        if not count:
            # Display a warning at the first iteration
            environment_altered = True
            sys.stderr.write(
                "Warning -- threading_cleanup() failed to cleanup "
                "%s threads (count: %s)"
                % (values[0] - original_values[0])
                )
            sys.stderr.flush()

        values = None

        time.sleep(0.01)
        gc_collect()


def reap_threads(func):
    """Use this function when threads are being used.  This will
    ensure that the threads are cleaned up even when the test fails.
    """
    @functools.wraps(func)
    def decorator(*args):
        key = threading_setup()
        try:
            return func(*args)
        finally:
            threading_cleanup(*key)
    return decorator

def join_thread(thread, timeout=30.0):
    """Join a thread. Raise an AssertionError if the thread is still alive
    after timeout seconds.
    """
    thread.join(timeout)
    if thread.is_alive():
        msg = "failed to join the thread in %.1f seconds" % timeout
        raise AssertionError(msg)

def bind_port(sock, host=HOST):
    """Bind the socket to a free port and return the port number.  Relies on
    ephemeral ports in order to ensure we are using an unbound port.  This is
    important as many tests may be running simultaneously, especially in a
    buildbot environment.  This method raises an exception if the sock.family
    is AF_INET and sock.type is SOCK_STREAM, *and* the socket has SO_REUSEADDR
    or SO_REUSEPORT set on it.  Tests should *never* set these socket options
    for TCP/IP sockets.  The only case for setting these options is testing
    multicasting via multiple UDP sockets.

    Additionally, if the SO_EXCLUSIVEADDRUSE socket option is available (i.e.
    on Windows), it will be set on the socket.  This will prevent anyone else
    from bind()'ing to our host/port for the duration of the test.
    """

    if sock.family == socket.AF_INET and sock.type == socket.SOCK_STREAM:
        if hasattr(socket, 'SO_REUSEADDR'):
            if sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 1:
                raise RuntimeError("tests should never set the SO_REUSEADDR " \
                                 "socket option on TCP/IP sockets!")
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                if sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT) == 1:
                    raise RuntimeError(
                        "tests should never set the SO_REUSEPORT "   \
                        "socket option on TCP/IP sockets!")
            except OSError:
                # Python's socket module was compiled using modern headers
                # thus defining SO_REUSEPORT but this process is running
                # under an older kernel that does not support SO_REUSEPORT.
                pass
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)

    sock.bind((host, 0))
    port = sock.getsockname()[1]
    return port

@contextlib.contextmanager
def closewrapper(sock):
    try:
        yield sock
    finally:
        sock.close()

class dummysocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def fileno(self):
        return 42

class dummychannel:
    def __init__(self):
        self.socket = dummysocket()

    def close(self):
        self.socket.close()

class exitingdummy:
    def __init__(self):
        pass

    def handle_read_event(self):
        raise asyncore.ExitNow()

    handle_write_event = handle_read_event
    handle_close = handle_read_event
    handle_expt_event = handle_read_event

class crashingdummy:
    def __init__(self):
        self.error_handled = False

    def handle_read_event(self):
        raise Exception()

    handle_write_event = handle_read_event
    handle_close = handle_read_event
    handle_expt_event = handle_read_event

    def handle_error(self):
        self.error_handled = True

# used when testing senders; just collects what it gets until newline is sent
def capture_server(evt, buf, serv):
    try:
        serv.listen(0)
        conn, addr = serv.accept()
    except socket.timeout:
        pass
    else:
        n = 200
        start = time.time()
        while n > 0 and time.time() - start < 3.0:
            r, w, e = select.select([conn], [], [], 0.1)
            if r:
                n -= 1
                data = conn.recv(10)
                # keep everything except for the newline terminator
                buf.write(data.replace(b'\n', b''))
                if b'\n' in data:
                    break
            time.sleep(0.01)

        conn.close()
    finally:
        serv.close()
        evt.set()

def bind_unix_socket(sock, addr):
    """Bind a unix socket, raising SkipTest if PermissionError is raised."""
    assert sock.family == socket.AF_UNIX
    try:
        sock.bind(addr)
    except PermissionError:
        sock.close()
        raise unittest.SkipTest('cannot bind AF_UNIX sockets')

def bind_af_aware(sock, addr):
    """Helper function to bind a socket according to its family."""
    if HAS_UNIX_SOCKETS and sock.family == socket.AF_UNIX:
        # Make sure the path doesn't exist.
        unlink(addr)
        bind_unix_socket(sock, addr)
    else:
        sock.bind(addr)

if sys.platform.startswith("win"):
    def _waitfor(func, pathname, waitall=False):
        # Perform the operation
        func(pathname)
        # Now setup the wait loop
        if waitall:
            dirname = pathname
        else:
            dirname, name = os.path.split(pathname)
            dirname = dirname or '.'
        # Check for `pathname` to be removed from the filesystem.
        # The exponential backoff of the timeout amounts to a total
        # of ~1 second after which the deletion is probably an error
        # anyway.
        # Testing on an i7@4.3GHz shows that usually only 1 iteration is
        # required when contention occurs.
        timeout = 0.001
        while timeout < 1.0:
            # Note we are only testing for the existence of the file(s) in
            # the contents of the directory regardless of any security or
            # access rights.  If we have made it this far, we have sufficient
            # permissions to do that much using Python's equivalent of the
            # Windows API FindFirstFile.
            # Other Windows APIs can fail or give incorrect results when
            # dealing with files that are pending deletion.
            L = os.listdir(dirname)
            if not (L if waitall else name in L):
                return
            # Increase the timeout and try again
            time.sleep(timeout)
            timeout *= 2
        warnings.warn('tests may fail, delete still pending for ' + pathname,
                      RuntimeWarning, stacklevel=4)

    def _unlink(filename):
        _waitfor(os.unlink, filename)
else:
    _unlink = os.unlink


def unlink(filename):
    try:
        _unlink(filename)
    except OSError:
        pass

class HelperFunctionTests(unittest.TestCase):
    def test_readwriteexc(self):
        # Check exception handling behavior of read, write and _exception

        # check that ExitNow exceptions in the object handler method
        # bubbles all the way up through asyncore read/write/_exception calls
        tr1 = exitingdummy()
        self.assertRaises(asyncore.ExitNow, asyncore.read, tr1)
        self.assertRaises(asyncore.ExitNow, asyncore.write, tr1)
        self.assertRaises(asyncore.ExitNow, asyncore._exception, tr1)

        # check that an exception other than ExitNow in the object handler
        # method causes the handle_error method to get called
        tr2 = crashingdummy()
        asyncore.read(tr2)
        self.assertEqual(tr2.error_handled, True)

        tr2 = crashingdummy()
        asyncore.write(tr2)
        self.assertEqual(tr2.error_handled, True)

        tr2 = crashingdummy()
        asyncore._exception(tr2)
        self.assertEqual(tr2.error_handled, True)

    # asyncore.readwrite uses constants in the select module that
    # are not present in Windows systems (see this thread:
    # http://mail.python.org/pipermail/python-list/2001-October/109973.html)
    # These constants should be present as long as poll is available

    @unittest.skipUnless(hasattr(select, 'poll'), 'select.poll required')
    def test_readwrite(self):
        # Check that correct methods are called by readwrite()

        attributes = ('read', 'expt', 'write', 'closed', 'error_handled')

        expected = (
            (select.POLLIN, 'read'),
            (select.POLLPRI, 'expt'),
            (select.POLLOUT, 'write'),
            (select.POLLERR, 'closed'),
            (select.POLLHUP, 'closed'),
            (select.POLLNVAL, 'closed'),
            )

        class testobj:
            def __init__(self):
                self.read = False
                self.write = False
                self.closed = False
                self.expt = False
                self.error_handled = False

            def handle_read_event(self):
                self.read = True

            def handle_write_event(self):
                self.write = True

            def handle_close(self):
                self.closed = True

            def handle_expt_event(self):
                self.expt = True

            def handle_error(self):
                self.error_handled = True

        for flag, expectedattr in expected:
            tobj = testobj()
            self.assertEqual(getattr(tobj, expectedattr), False)
            asyncore.readwrite(tobj, flag)

            # Only the attribute modified by the routine we expect to be
            # called should be True.
            for attr in attributes:
                self.assertEqual(getattr(tobj, attr), attr==expectedattr)

            # check that ExitNow exceptions in the object handler method
            # bubbles all the way up through asyncore readwrite call
            tr1 = exitingdummy()
            self.assertRaises(asyncore.ExitNow, asyncore.readwrite, tr1, flag)

            # check that an exception other than ExitNow in the object handler
            # method causes the handle_error method to get called
            tr2 = crashingdummy()
            self.assertEqual(tr2.error_handled, False)
            asyncore.readwrite(tr2, flag)
            self.assertEqual(tr2.error_handled, True)

    def test_closeall(self):
        self.closeall_check(False)

    def test_closeall_default(self):
        self.closeall_check(True)

    def closeall_check(self, usedefault):
        # Check that close_all() closes everything in a given map

        l = []
        testmap = {}
        for i in range(10):
            c = dummychannel()
            l.append(c)
            self.assertEqual(c.socket.closed, False)
            testmap[i] = c

        if usedefault:
            socketmap = asyncore.socket_map
            try:
                asyncore.socket_map = testmap
                asyncore.close_all()
            finally:
                testmap, asyncore.socket_map = asyncore.socket_map, socketmap
        else:
            asyncore.close_all(testmap)

        self.assertEqual(len(testmap), 0)

        for c in l:
            self.assertEqual(c.socket.closed, True)

    def test_compact_traceback(self):
        try:
            raise Exception("I don't like spam!")
        except:
            real_t, real_v, real_tb = sys.exc_info()
            r = asyncore.compact_traceback()
        else:
            self.fail("Expected exception")

        (f, function, line), t, v, info = r
        self.assertEqual(os.path.split(f)[-1], 'test_wasyncore.py')
        self.assertEqual(function, 'test_compact_traceback')
        self.assertEqual(t, real_t)
        self.assertEqual(v, real_v)
        self.assertEqual(info, '[%s|%s|%s]' % (f, function, line))


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        asyncore.close_all()

    def test_basic(self):
        d = asyncore.dispatcher()
        self.assertEqual(d.readable(), True)
        self.assertEqual(d.writable(), True)

    def test_repr(self):
        d = asyncore.dispatcher()
        self.assertEqual(
            repr(d),
            '<waitress.wasyncore.dispatcher at %#x>' % id(d)
        )

    def test_log_info(self):
        import logging
        inst = asyncore.dispatcher(map={})
        logger = DummyLogger()
        inst.logger = logger
        inst.log_info('message', 'warning')
        self.assertEqual(logger.messages, [(logging.WARN, 'message')])

    def test_log(self):
        import logging
        inst = asyncore.dispatcher()
        logger = DummyLogger()
        inst.logger = logger
        inst.log('message')
        self.assertEqual(logger.messages, [(logging.DEBUG, 'message')])

    def test_unhandled(self):
        import logging
        inst = asyncore.dispatcher()
        logger = DummyLogger()
        inst.logger = logger
        
        inst.handle_expt()
        inst.handle_read()
        inst.handle_write()
        inst.handle_connect()

        expected = [(logging.WARN, 'unhandled incoming priority event'),
                    (logging.WARN, 'unhandled read event'),
                    (logging.WARN, 'unhandled write event'),
                    (logging.WARN, 'unhandled connect event')]
        self.assertEqual(logger.messages, expected)

    def test_strerror(self):
        # refers to bug #8573
        err = asyncore._strerror(errno.EPERM)
        if hasattr(os, 'strerror'):
            self.assertEqual(err, os.strerror(errno.EPERM))
        err = asyncore._strerror(-1)
        self.assertTrue(err != "")


class dispatcherwithsend_noread(asyncore.dispatcher_with_send):
    def readable(self):
        return False

    def handle_connect(self):
        pass


class DispatcherWithSendTests(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        asyncore.close_all()

    @reap_threads
    def test_send(self):
        evt = threading.Event()
        sock = socket.socket()
        sock.settimeout(3)
        port = bind_port(sock)

        cap = BytesIO()
        args = (evt, cap, sock)
        t = threading.Thread(target=capture_server, args=args)
        t.start()
        try:
            # wait a little longer for the server to initialize (it sometimes
            # refuses connections on slow machines without this wait)
            time.sleep(0.2)

            data = b"Suppose there isn't a 16-ton weight?"
            d = dispatcherwithsend_noread()
            d.create_socket()
            d.connect((HOST, port))

            # give time for socket to connect
            time.sleep(0.1)

            d.send(data)
            d.send(data)
            d.send(b'\n')

            n = 1000
            while d.out_buffer and n > 0:
                asyncore.poll()
                n -= 1

            evt.wait()

            self.assertEqual(cap.getvalue(), data*2)
        finally:
            join_thread(t, timeout=TIMEOUT)


@unittest.skipUnless(hasattr(asyncore, 'file_wrapper'),
                     'asyncore.file_wrapper required')
class FileWrapperTest(unittest.TestCase):
    def setUp(self):
        self.d = b"It's not dead, it's sleeping!"
        with open(TESTFN, 'wb') as file:
            file.write(self.d)

    def tearDown(self):
        unlink(TESTFN)

    def test_recv(self):
        fd = os.open(TESTFN, os.O_RDONLY)
        w = asyncore.file_wrapper(fd)
        os.close(fd)

        self.assertNotEqual(w.fd, fd)
        self.assertNotEqual(w.fileno(), fd)
        self.assertEqual(w.recv(13), b"It's not dead")
        self.assertEqual(w.read(6), b", it's")
        w.close()
        self.assertRaises(OSError, w.read, 1)

    def test_send(self):
        d1 = b"Come again?"
        d2 = b"I want to buy some cheese."
        fd = os.open(TESTFN, os.O_WRONLY | os.O_APPEND)
        w = asyncore.file_wrapper(fd)
        os.close(fd)

        w.write(d1)
        w.send(d2)
        w.close()
        with open(TESTFN, 'rb') as file:
            self.assertEqual(file.read(), self.d + d1 + d2)

    @unittest.skipUnless(hasattr(asyncore, 'file_dispatcher'),
                         'asyncore.file_dispatcher required')
    def test_dispatcher(self):
        fd = os.open(TESTFN, os.O_RDONLY)
        data = []
        class FileDispatcher(asyncore.file_dispatcher):
            def handle_read(self):
                data.append(self.recv(29))
        FileDispatcher(fd)
        os.close(fd)
        asyncore.loop(timeout=0.01, use_poll=True, count=2)
        self.assertEqual(b"".join(data), self.d)

    def test_resource_warning(self):
        # Issue #11453
        fd = os.open(TESTFN, os.O_RDONLY)
        f = asyncore.file_wrapper(fd)

        os.close(fd)
        with check_warnings(('', compat.ResourceWarning)):
            f = None
            gc_collect()

    def test_close_twice(self):
        fd = os.open(TESTFN, os.O_RDONLY)
        f = asyncore.file_wrapper(fd)
        os.close(fd)

        os.close(f.fd)  # file_wrapper dupped fd
        with self.assertRaises(OSError):
            f.close()

        self.assertEqual(f.fd, -1)
        # calling close twice should not fail
        f.close()


class BaseTestHandler(asyncore.dispatcher):

    def __init__(self, sock=None):
        asyncore.dispatcher.__init__(self, sock)
        self.flag = False

    def handle_accept(self):
        raise Exception("handle_accept not supposed to be called")

    def handle_accepted(self):
        raise Exception("handle_accepted not supposed to be called")

    def handle_connect(self):
        raise Exception("handle_connect not supposed to be called")

    def handle_expt(self):
        raise Exception("handle_expt not supposed to be called")

    def handle_close(self):
        raise Exception("handle_close not supposed to be called")

    def handle_error(self):
        raise


class BaseServer(asyncore.dispatcher):
    """A server which listens on an address and dispatches the
    connection to a handler.
    """

    def __init__(self, family, addr, handler=BaseTestHandler):
        asyncore.dispatcher.__init__(self)
        self.create_socket(family)
        self.set_reuse_addr()
        bind_af_aware(self.socket, addr)
        self.listen(5)
        self.handler = handler

    @property
    def address(self):
        return self.socket.getsockname()

    def handle_accepted(self, sock, addr):
        self.handler(sock)

    def handle_error(self):
        raise


class BaseClient(BaseTestHandler):

    def __init__(self, family, address):
        BaseTestHandler.__init__(self)
        self.create_socket(family)
        self.connect(address)

    def handle_connect(self):
        pass


class BaseTestAPI:

    def tearDown(self):
        asyncore.close_all(ignore_all=True)

    def loop_waiting_for_flag(self, instance, timeout=5):
        timeout = float(timeout) / 100
        count = 100
        while asyncore.socket_map and count > 0:
            asyncore.loop(timeout=0.01, count=1, use_poll=self.use_poll)
            if instance.flag:
                return
            count -= 1
            time.sleep(timeout)
        self.fail("flag not set")

    def test_handle_connect(self):
        # make sure handle_connect is called on connect()

        class TestClient(BaseClient):
            def handle_connect(self):
                self.flag = True

        server = BaseServer(self.family, self.addr)
        client = TestClient(self.family, server.address)
        self.loop_waiting_for_flag(client)

    def test_handle_accept(self):
        # make sure handle_accept() is called when a client connects

        class TestListener(BaseTestHandler):

            def __init__(self, family, addr):
                BaseTestHandler.__init__(self)
                self.create_socket(family)
                bind_af_aware(self.socket, addr)
                self.listen(5)
                self.address = self.socket.getsockname()

            def handle_accept(self):
                self.flag = True

        server = TestListener(self.family, self.addr)
        client = BaseClient(self.family, server.address)
        self.loop_waiting_for_flag(server)

    def test_handle_accepted(self):
        # make sure handle_accepted() is called when a client connects

        class TestListener(BaseTestHandler):

            def __init__(self, family, addr):
                BaseTestHandler.__init__(self)
                self.create_socket(family)
                bind_af_aware(self.socket, addr)
                self.listen(5)
                self.address = self.socket.getsockname()

            def handle_accept(self):
                asyncore.dispatcher.handle_accept(self)

            def handle_accepted(self, sock, addr):
                sock.close()
                self.flag = True

        server = TestListener(self.family, self.addr)
        client = BaseClient(self.family, server.address)
        self.loop_waiting_for_flag(server)


    def test_handle_read(self):
        # make sure handle_read is called on data received

        class TestClient(BaseClient):
            def handle_read(self):
                self.flag = True

        class TestHandler(BaseTestHandler):
            def __init__(self, conn):
                BaseTestHandler.__init__(self, conn)
                self.send(b'x' * 1024)

        server = BaseServer(self.family, self.addr, TestHandler)
        client = TestClient(self.family, server.address)
        self.loop_waiting_for_flag(client)

    def test_handle_write(self):
        # make sure handle_write is called

        class TestClient(BaseClient):
            def handle_write(self):
                self.flag = True

        server = BaseServer(self.family, self.addr)
        client = TestClient(self.family, server.address)
        self.loop_waiting_for_flag(client)

    def test_handle_close(self):
        # make sure handle_close is called when the other end closes
        # the connection

        class TestClient(BaseClient):

            def handle_read(self):
                # in order to make handle_close be called we are supposed
                # to make at least one recv() call
                self.recv(1024)

            def handle_close(self):
                self.flag = True
                self.close()

        class TestHandler(BaseTestHandler):
            def __init__(self, conn):
                BaseTestHandler.__init__(self, conn)
                self.close()

        server = BaseServer(self.family, self.addr, TestHandler)
        client = TestClient(self.family, server.address)
        self.loop_waiting_for_flag(client)

    def test_handle_close_after_conn_broken(self):
        # Check that ECONNRESET/EPIPE is correctly handled (issues #5661 and
        # #11265).

        data = b'\0' * 128

        class TestClient(BaseClient):

            def handle_write(self):
                self.send(data)

            def handle_close(self):
                self.flag = True
                self.close()

            def handle_expt(self):
                self.flag = True
                self.close()

        class TestHandler(BaseTestHandler):

            def handle_read(self):
                self.recv(len(data))
                self.close()

            def writable(self):
                return False

        server = BaseServer(self.family, self.addr, TestHandler)
        client = TestClient(self.family, server.address)
        self.loop_waiting_for_flag(client)

    @unittest.skipIf(sys.platform.startswith("sunos"),
                     "OOB support is broken on Solaris")
    def test_handle_expt(self):
        # Make sure handle_expt is called on OOB data received.
        # Note: this might fail on some platforms as OOB data is
        # tenuously supported and rarely used.
        if HAS_UNIX_SOCKETS and self.family == socket.AF_UNIX:
            self.skipTest("Not applicable to AF_UNIX sockets.")

        if sys.platform == "darwin" and self.use_poll:
            self.skipTest("poll may fail on macOS; see issue #28087")

        class TestClient(BaseClient):
            def handle_expt(self):
                self.socket.recv(1024, socket.MSG_OOB)
                self.flag = True

        class TestHandler(BaseTestHandler):
            def __init__(self, conn):
                BaseTestHandler.__init__(self, conn)
                self.socket.send(
                    compat.tobytes(chr(244)), socket.MSG_OOB
                )

        server = BaseServer(self.family, self.addr, TestHandler)
        client = TestClient(self.family, server.address)
        self.loop_waiting_for_flag(client)

    def test_handle_error(self):

        class TestClient(BaseClient):
            def handle_write(self):
                1.0 / 0
            def handle_error(self):
                self.flag = True
                try:
                    raise
                except ZeroDivisionError:
                    pass
                else:
                    raise Exception("exception not raised")

        server = BaseServer(self.family, self.addr)
        client = TestClient(self.family, server.address)
        self.loop_waiting_for_flag(client)

    def test_connection_attributes(self):
        server = BaseServer(self.family, self.addr)
        client = BaseClient(self.family, server.address)

        # we start disconnected
        self.assertFalse(server.connected)
        self.assertTrue(server.accepting)
        # this can't be taken for granted across all platforms
        #self.assertFalse(client.connected)
        self.assertFalse(client.accepting)

        # execute some loops so that client connects to server
        asyncore.loop(timeout=0.01, use_poll=self.use_poll, count=100)
        self.assertFalse(server.connected)
        self.assertTrue(server.accepting)
        self.assertTrue(client.connected)
        self.assertFalse(client.accepting)

        # disconnect the client
        client.close()
        self.assertFalse(server.connected)
        self.assertTrue(server.accepting)
        self.assertFalse(client.connected)
        self.assertFalse(client.accepting)

        # stop serving
        server.close()
        self.assertFalse(server.connected)
        self.assertFalse(server.accepting)

    def test_create_socket(self):
        s = asyncore.dispatcher()
        s.create_socket(self.family)
        #self.assertEqual(s.socket.type, socket.SOCK_STREAM)
        self.assertEqual(s.socket.family, self.family)
        self.assertEqual(s.socket.gettimeout(), 0)
        #self.assertFalse(s.socket.get_inheritable())

    def test_bind(self):
        if HAS_UNIX_SOCKETS and self.family == socket.AF_UNIX:
            self.skipTest("Not applicable to AF_UNIX sockets.")
        s1 = asyncore.dispatcher()
        s1.create_socket(self.family)
        s1.bind(self.addr)
        s1.listen(5)
        port = s1.socket.getsockname()[1]

        s2 = asyncore.dispatcher()
        s2.create_socket(self.family)
        # EADDRINUSE indicates the socket was correctly bound
        self.assertRaises(socket.error, s2.bind, (self.addr[0], port))

    def test_set_reuse_addr(self):
        if HAS_UNIX_SOCKETS and self.family == socket.AF_UNIX:
            self.skipTest("Not applicable to AF_UNIX sockets.")

        with closewrapper(socket.socket(self.family)) as sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except OSError:
                unittest.skip("SO_REUSEADDR not supported on this platform")
            else:
                # if SO_REUSEADDR succeeded for sock we expect asyncore
                # to do the same
                s = asyncore.dispatcher(socket.socket(self.family))
                self.assertFalse(s.socket.getsockopt(socket.SOL_SOCKET,
                                                     socket.SO_REUSEADDR))
                s.socket.close()
                s.create_socket(self.family)
                s.set_reuse_addr()
                self.assertTrue(s.socket.getsockopt(socket.SOL_SOCKET,
                                                     socket.SO_REUSEADDR))

    @reap_threads
    def test_quick_connect(self):
        # see: http://bugs.python.org/issue10340
        if self.family not in (socket.AF_INET, getattr(socket, "AF_INET6", object())):
            self.skipTest("test specific to AF_INET and AF_INET6")

        server = BaseServer(self.family, self.addr)
        # run the thread 500 ms: the socket should be connected in 200 ms
        t = threading.Thread(target=lambda: asyncore.loop(timeout=0.1,
                                                          count=5))
        t.start()
        try:
            sock = socket.socket(self.family, socket.SOCK_STREAM)
            with closewrapper(sock) as s:
                s.settimeout(.2)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                             struct.pack('ii', 1, 0))

                try:
                    s.connect(server.address)
                except OSError:
                    pass
        finally:
            join_thread(t, timeout=TIMEOUT)

class TestAPI_UseIPv4Sockets(BaseTestAPI):
    family = socket.AF_INET
    addr = (HOST, 0)

@unittest.skipUnless(compat.IPV6_ENABLED, 'IPv6 support required')
class TestAPI_UseIPv6Sockets(BaseTestAPI):
    family = socket.AF_INET6
    addr = (HOSTv6, 0)

@unittest.skipUnless(HAS_UNIX_SOCKETS, 'Unix sockets required')
class TestAPI_UseUnixSockets(BaseTestAPI):
    if HAS_UNIX_SOCKETS:
        family = socket.AF_UNIX
    addr = TESTFN

    def tearDown(self):
        unlink(self.addr)
        BaseTestAPI.tearDown(self)

class TestAPI_UseIPv4Select(TestAPI_UseIPv4Sockets, unittest.TestCase):
    use_poll = False

@unittest.skipUnless(hasattr(select, 'poll'), 'select.poll required')
class TestAPI_UseIPv4Poll(TestAPI_UseIPv4Sockets, unittest.TestCase):
    use_poll = True

class TestAPI_UseIPv6Select(TestAPI_UseIPv6Sockets, unittest.TestCase):
    use_poll = False

@unittest.skipUnless(hasattr(select, 'poll'), 'select.poll required')
class TestAPI_UseIPv6Poll(TestAPI_UseIPv6Sockets, unittest.TestCase):
    use_poll = True

class TestAPI_UseUnixSocketsSelect(TestAPI_UseUnixSockets, unittest.TestCase):
    use_poll = False

@unittest.skipUnless(hasattr(select, 'poll'), 'select.poll required')
class TestAPI_UseUnixSocketsPoll(TestAPI_UseUnixSockets, unittest.TestCase):
    use_poll = True

class Test__strerror(unittest.TestCase):
    def _callFUT(self, err):
        from waitress.wasyncore import _strerror
        return _strerror(err)

    def test_gardenpath(self):
        self.assertEqual(self._callFUT(1), 'Operation not permitted')

    def test_unknown(self):
        self.assertEqual(self._callFUT('wut'), 'Unknown error wut')
        
class Test_read(unittest.TestCase):
    def _callFUT(self, dispatcher):
        from waitress.wasyncore import read
        return read(dispatcher)

    def test_gardenpath(self):
        inst = DummyDispatcher()
        self._callFUT(inst)
        self.assertTrue(inst.read_event_handled)
        self.assertFalse(inst.error_handled)

    def test_reraised(self):
        from waitress.wasyncore import ExitNow
        inst = DummyDispatcher(ExitNow)
        self.assertRaises(ExitNow,self._callFUT, inst)
        self.assertTrue(inst.read_event_handled)
        self.assertFalse(inst.error_handled)

    def test_non_reraised(self):
        inst = DummyDispatcher(OSError)
        self._callFUT(inst)
        self.assertTrue(inst.read_event_handled)
        self.assertTrue(inst.error_handled)

class Test_write(unittest.TestCase):
    def _callFUT(self, dispatcher):
        from waitress.wasyncore import write
        return write(dispatcher)

    def test_gardenpath(self):
        inst = DummyDispatcher()
        self._callFUT(inst)
        self.assertTrue(inst.write_event_handled)
        self.assertFalse(inst.error_handled)

    def test_reraised(self):
        from waitress.wasyncore import ExitNow
        inst = DummyDispatcher(ExitNow)
        self.assertRaises(ExitNow,self._callFUT, inst)
        self.assertTrue(inst.write_event_handled)
        self.assertFalse(inst.error_handled)

    def test_non_reraised(self):
        inst = DummyDispatcher(OSError)
        self._callFUT(inst)
        self.assertTrue(inst.write_event_handled)
        self.assertTrue(inst.error_handled)

class Test__exception(unittest.TestCase):
    def _callFUT(self, dispatcher):
        from waitress.wasyncore import _exception
        return _exception(dispatcher)

    def test_gardenpath(self):
        inst = DummyDispatcher()
        self._callFUT(inst)
        self.assertTrue(inst.expt_event_handled)
        self.assertFalse(inst.error_handled)

    def test_reraised(self):
        from waitress.wasyncore import ExitNow
        inst = DummyDispatcher(ExitNow)
        self.assertRaises(ExitNow,self._callFUT, inst)
        self.assertTrue(inst.expt_event_handled)
        self.assertFalse(inst.error_handled)

    def test_non_reraised(self):
        inst = DummyDispatcher(OSError)
        self._callFUT(inst)
        self.assertTrue(inst.expt_event_handled)
        self.assertTrue(inst.error_handled)
        
class DummyDispatcher(object):
    read_event_handled = False
    write_event_handled = False
    expt_event_handled = False
    error_handled = False
    close_handled = False
    def __init__(self, exc=None):
        self.exc = exc

    def handle_read_event(self):
        self.read_event_handled = True
        if self.exc is not None:
            raise self.exc

    def handle_write_event(self):
        self.write_event_handled = True
        if self.exc is not None:
            raise self.exc

    def handle_expt_event(self):
        self.expt_event_handled = True
        if self.exc is not None:
            raise self.exc
        
    def handle_error(self):
        self.error_handled = True

    def handle_close(self):
        self.close_handled = True
        
