import errno
import select
import socket
import sys
import threading
import time
import unittest

dummy_app = object()


class TestWSGIServer(unittest.TestCase):
    def setUp(self):
        # Keep track of every server that gets created so that tearDown can
        # close all of them, not just the last one a test held on to.
        self.insts = []

    def tearDown(self):
        for inst in self.insts:
            inst.close()

    def _register(self, inst):
        self.insts.append(inst)

        return inst

    def _makeOne(
        self,
        application=dummy_app,
        host="127.0.0.1",
        port=0,
        _dispatcher=None,
        adj=None,
        map=None,
        _start=True,
        _sock=None,
        _server=None,
    ):
        from waitress.server import create_server

        return self._register(
            create_server(
                application,
                host=host,
                port=port,
                map=map,
                _dispatcher=_dispatcher,
                _start=_start,
                _sock=_sock,
            )
        )

    def _makeOneWithMap(
        self, adj=None, _start=True, host="127.0.0.1", port=0, app=dummy_app
    ):
        sock = DummySock()
        task_dispatcher = DummyTaskDispatcher()
        map = {}
        return self._makeOne(
            app,
            host=host,
            port=port,
            map=map,
            _sock=sock,
            _dispatcher=task_dispatcher,
            _start=_start,
        )

    def _makeOneWithMulti(
        self, adj=None, _start=True, app=dummy_app, listen="127.0.0.1:0 127.0.0.1:0"
    ):
        sock = DummySock()
        task_dispatcher = DummyTaskDispatcher()
        map = {}
        from waitress.server import create_server

        return self._register(
            create_server(
                app,
                listen=listen,
                map=map,
                _dispatcher=task_dispatcher,
                _start=_start,
                _sock=sock,
            )
        )

    def _makeWithSockets(
        self,
        application=dummy_app,
        _dispatcher=None,
        map=None,
        _start=True,
        _sock=None,
        _server=None,
        sockets=None,
    ):
        from waitress.server import create_server

        _sockets = []
        if sockets is not None:
            _sockets = sockets

        return self._register(
            create_server(
                application,
                map=map,
                _dispatcher=_dispatcher,
                _start=_start,
                _sock=_sock,
                sockets=_sockets,
            )
        )

    def test_ctor_app_is_None(self):
        self.assertRaises(ValueError, self._makeOneWithMap, app=None)

    def test_ctor_start_true(self):
        inst = self._makeOneWithMap(_start=True)
        self.assertTrue(inst.accepting)
        self.assertEqual(inst.socket.listened, 1024)

    def test_ctor_makes_dispatcher(self):
        inst = self._makeOne(_start=False, map={})
        self.assertEqual(
            inst.task_dispatcher.__class__.__name__, "ThreadedTaskDispatcher"
        )

    def test_ctor_start_false(self):
        inst = self._makeOneWithMap(_start=False)
        self.assertFalse(inst.accepting)

    def test_get_server_multi(self):
        inst = self._makeOneWithMulti()
        self.assertEqual(inst.__class__.__name__, "MultiSocketServer")

    def test_run(self):
        inst = self._makeOneWithMap(_start=False)
        inst.asyncore = DummyAsyncore()
        inst.task_dispatcher = DummyTaskDispatcher()
        inst.run()
        self.assertTrue(inst.task_dispatcher.was_shutdown)

    def test_run_base_server(self):
        inst = self._makeOneWithMulti(_start=False)
        inst.asyncore = DummyAsyncore()
        inst.task_dispatcher = DummyTaskDispatcher()
        inst.run()
        self.assertTrue(inst.task_dispatcher.was_shutdown)

    def test_pull_trigger(self):
        inst = self._makeOneWithMap(_start=False)
        inst.trigger.close()
        inst.trigger = DummyTrigger()
        inst.pull_trigger()
        self.assertTrue(inst.trigger.pulled)

    def test_add_task(self):
        task = DummyTask()
        inst = self._makeOneWithMap()
        inst.add_task(task)
        self.assertListEqual(inst.task_dispatcher.tasks, [task])
        self.assertFalse(task.serviced)

    def test_readable_not_accepting(self):
        inst = self._makeOneWithMap()
        inst.accepting = False
        self.assertFalse(inst.readable())

    def test_readable_maplen_gt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {"a": 1, "b": 2}
        self.assertFalse(inst.readable())
        self.assertTrue(inst.in_connection_overflow)

    def test_readable_maplen_lt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {}
        self.assertTrue(inst.readable())
        self.assertFalse(inst.in_connection_overflow)

    def test_readable_maplen_toggles_connection_overflow(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {"a": 1, "b": 2}
        self.assertFalse(inst.in_connection_overflow)
        self.assertFalse(inst.readable())
        self.assertTrue(inst.in_connection_overflow)
        inst._map = {}
        self.assertTrue(inst.readable())
        self.assertFalse(inst.in_connection_overflow)

    def test_readable_maintenance_false(self):
        import time

        inst = self._makeOneWithMap()
        then = time.time() + 1000
        inst.next_channel_cleanup = then
        L = []
        inst.maintenance = lambda t: L.append(t)
        inst.readable()
        self.assertListEqual(L, [])
        self.assertEqual(inst.next_channel_cleanup, then)

    def test_readable_maintenance_true(self):
        inst = self._makeOneWithMap()
        inst.next_channel_cleanup = 0
        L = []
        inst.maintenance = lambda t: L.append(t)
        inst.readable()
        self.assertEqual(len(L), 1)
        self.assertNotEqual(inst.next_channel_cleanup, 0)

    def test_writable(self):
        inst = self._makeOneWithMap()
        self.assertFalse(inst.writable())

    def test_handle_read(self):
        inst = self._makeOneWithMap()
        self.assertIsNone(inst.handle_read())

    def test_handle_connect(self):
        inst = self._makeOneWithMap()
        self.assertIsNone(inst.handle_connect())

    def test_handle_accept_wouldblock_socket_error(self):
        inst = self._makeOneWithMap()
        ewouldblock = socket.error(errno.EWOULDBLOCK)
        inst.socket = DummySock(toraise=ewouldblock)
        inst.handle_accept()
        self.assertFalse(inst.socket.accepted)

    def test_handle_accept_other_socket_error(self):
        inst = self._makeOneWithMap()
        eaborted = socket.error(errno.ECONNABORTED)
        inst.socket = DummySock(toraise=eaborted)
        inst.adj = DummyAdj

        def foo():
            raise OSError

        inst.accept = foo
        inst.logger = DummyLogger()
        inst.handle_accept()
        self.assertFalse(inst.socket.accepted)
        self.assertEqual(len(inst.logger.logged), 1)

    def test_handle_accept_noerror(self):
        inst = self._makeOneWithMap()
        innersock = DummySock()
        inst.socket = DummySock(acceptresult=(innersock, None))
        inst.adj = DummyAdj
        L = []
        inst.channel_class = lambda *arg, **kw: L.append(arg)
        inst.handle_accept()
        self.assertTrue(inst.socket.accepted)
        self.assertListEqual(innersock.opts, [("level", "optname", "value")])
        self.assertListEqual(L, [(inst, innersock, None, inst.adj)])

    def test_maintenance(self):
        inst = self._makeOneWithMap()
        zombie = DummyChannel()
        zombie.last_activity = 0
        zombie.running_tasks = False
        inst.active_channels[100] = zombie
        inst.maintenance(10000)
        self.assertTrue(zombie.will_close)

    def test_backward_compatibility(self):
        from waitress.adjustments import Adjustments
        from waitress.server import TcpWSGIServer, WSGIServer

        self.assertIs(WSGIServer, TcpWSGIServer)
        inst = self._register(WSGIServer(None, _start=False, port=1234))
        # Ensure the adjustment was actually applied.
        self.assertNotEqual(Adjustments.port, 1234)
        self.assertEqual(inst.adj.port, 1234)

    def test_create_with_one_tcp_socket(self):
        from waitress.server import TcpWSGIServer

        sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM)]
        sockets[0].bind(("127.0.0.1", 0))
        inst = self._makeWithSockets(_start=False, sockets=sockets)
        self.assertIsInstance(inst, TcpWSGIServer)

    def test_create_with_multiple_tcp_sockets(self):
        from waitress.server import MultiSocketServer

        sockets = [
            socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            socket.socket(socket.AF_INET, socket.SOCK_STREAM),
        ]
        sockets[0].bind(("127.0.0.1", 0))
        sockets[1].bind(("127.0.0.1", 0))
        inst = self._makeWithSockets(_start=False, sockets=sockets)
        self.assertIsInstance(inst, MultiSocketServer)
        self.assertEqual(len(inst.effective_listen), 2)

    def test_create_with_one_socket_should_not_bind_socket(self):
        innersock = DummySock()
        sockets = [DummySock(acceptresult=(innersock, None))]
        sockets[0].bind(("127.0.0.1", 80))
        sockets[0].bind_called = False
        inst = self._makeWithSockets(_start=False, sockets=sockets)
        self.assertTupleEqual(inst.socket.bound, ("127.0.0.1", 80))
        self.assertFalse(inst.socket.bind_called)

    def test_create_with_one_socket_handle_accept_noerror(self):
        innersock = DummySock()
        sockets = [DummySock(acceptresult=(innersock, None))]
        sockets[0].bind(("127.0.0.1", 80))
        inst = self._makeWithSockets(sockets=sockets)
        L = []
        inst.channel_class = lambda *arg, **kw: L.append(arg)
        inst.adj = DummyAdj
        inst.handle_accept()
        self.assertTrue(sockets[0].accepted)
        self.assertListEqual(innersock.opts, [("level", "optname", "value")])
        self.assertListEqual(L, [(inst, innersock, None, inst.adj)])

    def test_close_shuts_down_task_dispatcher(self):
        inst = self._makeOne(_start=False, map={})
        dispatcher = inst.task_dispatcher
        self.assertTrue(inst.own_task_dispatcher)
        self.assertEqual(len(dispatcher.threads), inst.adj.threads)
        inst.close()
        self.assertEqual(dispatcher.threads, set())

    def test_close_is_idempotent(self):
        inst = self._makeOne(_start=False, map={})
        inst.close()
        inst.close()

    def test_close_closes_active_channels(self):
        inst = self._makeOneWithMap()
        channel = DummyChannel()
        inst.active_channels[100] = channel
        inst.close()
        self.assertTrue(channel.closed)

    def test_multi_close_shuts_down_task_dispatcher(self):
        inst = self._makeOneWithMulti()
        inst.close()
        self.assertTrue(inst.task_dispatcher.was_shutdown)
        self.assertEqual(
            inst.task_dispatcher.shutdown_timeout, inst.adj.shutdown_timeout
        )

    def test_multi_finds_its_servers_in_the_map(self):
        from waitress.server import BaseWSGIServer, MultiSocketServer

        inst = self._makeOneWithMulti()
        # The servers can also be passed in, which is what create_server does,
        # but they are discoverable from the socket map alone.
        rediscovered = MultiSocketServer(inst.map, inst.adj, inst.effective_listen)
        self.assertTrue(rediscovered.servers)
        self.assertListEqual(
            rediscovered.servers,
            [s for s in inst.map.values() if isinstance(s, BaseWSGIServer)],
        )

    def test_ctor_does_not_start_threads_until_bound(self):
        from waitress.server import TcpWSGIServer

        class FailingServer(TcpWSGIServer):
            def bind_server_socket(self):
                raise OSError(errno.EADDRINUSE, "Address already in use")

        map = {}
        threads_before = threading.active_count()

        with self.assertRaises(OSError):
            FailingServer(dummy_app, map=map, host="127.0.0.1", port=0)

        self.assertEqual(threading.active_count(), threads_before)
        self.assertDictEqual(map, {})


class TestServerCleanup(unittest.TestCase):
    """
    A failure to create a server must not leave any threads, sockets or socket
    map entries behind: the caller has no way of getting at them to clean them
    up itself. See https://github.com/Pylons/waitress/issues/480
    """

    def setUp(self):
        self.insts = []

    def tearDown(self):
        for inst in self.insts:
            inst.close()

    def _makeOne(self, **kw):
        from waitress.server import create_server

        kw.setdefault("map", {})
        inst = create_server(dummy_app, **kw)
        self.insts.append(inst)

        return inst

    def _makeOneListening(self):
        """Create a server holding on to an ephemeral port."""
        inst = self._makeOne(host="127.0.0.1", port=0)

        return inst.effective_host, inst.effective_port

    @unittest.skipIf(
        sys.platform.startswith("win"),
        "Windows allows rebinding a port that is already being listened on",
    )
    def test_bind_failure_does_not_leak(self):
        from waitress.server import create_server

        host, port = self._makeOneListening()

        map = {}
        threads_before = threading.active_count()

        with self.assertRaises(OSError) as cm:
            create_server(dummy_app, host=host, port=port, map=map)

        self.assertEqual(cm.exception.errno, errno.EADDRINUSE)
        # No worker threads were started, and no trigger or server socket was
        # left registered in the socket map.
        self.assertEqual(threading.active_count(), threads_before)
        self.assertDictEqual(map, {})

    @unittest.skipIf(
        sys.platform.startswith("win"),
        "Windows allows rebinding a port that is already being listened on",
    )
    def test_partial_bind_failure_closes_the_servers_that_did_bind(self):
        from waitress.server import create_server

        host, port = self._makeOneListening()

        map = {}
        threads_before = threading.active_count()

        # The first of these binds successfully, the second one does not. The
        # first one is not returned to us, so create_server has to close it.
        with self.assertRaises(OSError) as cm:
            create_server(
                dummy_app, listen=f"127.0.0.1:0 {host}:{port}", map=map, threads=2
            )

        self.assertEqual(cm.exception.errno, errno.EADDRINUSE)
        self.assertEqual(threading.active_count(), threads_before)
        self.assertDictEqual(map, {})

    def test_no_sockets_to_listen_on(self):
        dispatcher = DummyTaskDispatcher()

        with self.assertRaises(ValueError):
            self._makeOne(listen="", _dispatcher=dispatcher)

        self.assertTrue(dispatcher.was_shutdown)

    def test_create_server_hands_dispatcher_to_single_server(self):
        inst = self._makeOne(host="127.0.0.1", port=0)
        self.assertTrue(inst.own_task_dispatcher)

    def test_create_server_keeps_dispatcher_for_multisocket(self):
        from waitress.server import BaseWSGIServer

        map = {}
        inst = self._makeOne(listen="127.0.0.1:0 127.0.0.1:0", map=map)

        for server in map.values():
            if isinstance(server, BaseWSGIServer):
                # MultiSocketServer owns the dispatcher, closing a single one
                # of the listening sockets must not stop the worker threads.
                self.assertFalse(server.own_task_dispatcher)

        self.assertEqual(len(inst.task_dispatcher.threads), inst.adj.threads)
        inst.close()
        self.assertEqual(inst.task_dispatcher.threads, set())


class TestDrain(unittest.TestCase):
    """
    Tests for the loop that keeps the server running long enough for the
    requests that are already in flight to finish.
    """

    def _callFUT(self, servers, map=None, asyncore=None, **kw):
        from waitress.server import _drain

        if map is None:
            map = {}

        if asyncore is None:
            asyncore = DummyAsyncoreLoop()

        return _drain(servers, map, DummyShutdownAdj(**kw), asyncore)

    def test_stops_accepting_before_anything_else(self):
        server = DummyDrainServer()
        asyncore = DummyAsyncoreLoop()
        self._callFUT([server], asyncore=asyncore)
        self.assertTrue(server.stopped_accepting)

    def test_no_channels_does_not_run_the_loop(self):
        asyncore = DummyAsyncoreLoop()
        self._callFUT([DummyDrainServer()], asyncore=asyncore)
        self.assertEqual(asyncore.calls, 0)

    def test_disabled_by_a_zero_timeout(self):
        server = DummyDrainServer({1: DummyChannel()})
        asyncore = DummyAsyncoreLoop()
        self._callFUT([server], asyncore=asyncore, shutdown_timeout=0)
        self.assertTrue(server.stopped_accepting)
        self.assertEqual(asyncore.calls, 0)

    def test_idle_channel_is_asked_to_close_once_flushed(self):
        channel = DummyChannel()
        server = DummyDrainServer({1: channel})
        # The loop "closes" the channel on the first pass through.
        asyncore = DummyAsyncoreLoop(on_loop=lambda: server.active_channels.clear())
        self._callFUT([server], asyncore=asyncore)
        self.assertTrue(channel.draining)
        self.assertTrue(channel.close_when_flushed)
        self.assertEqual(asyncore.calls, 1)

    def test_busy_channel_is_left_running(self):
        channel = DummyChannel(requests=["a request being serviced"])
        server = DummyDrainServer({1: channel})
        asyncore = DummyAsyncoreLoop()

        with self.assertLogs("waitress", level="WARNING") as logged:
            self._callFUT([server], asyncore=asyncore, shutdown_timeout=0.01)

        # We stop reading new requests off it, but we do not pull the rug out
        # from underneath the task that is still running.
        self.assertTrue(channel.draining)
        self.assertFalse(channel.close_when_flushed)
        self.assertIn("Graceful shutdown timed out", logged.output[0])

    def test_second_interrupt_gives_up(self):
        channel = DummyChannel(requests=["a request being serviced"])
        server = DummyDrainServer({1: channel})

        def interrupt():
            raise KeyboardInterrupt

        asyncore = DummyAsyncoreLoop(on_loop=interrupt)

        with self.assertLogs("waitress", level="WARNING") as logged:
            self._callFUT([server], asyncore=asyncore)

        self.assertIn("Graceful shutdown interrupted", logged.output[0])


class TestGracefulShutdown(unittest.TestCase):
    """
    End to end tests: a real socket, a real task dispatcher and a real WSGI
    application, driven by a real wasyncore loop.
    """

    def _makeServer(self, app, **kw):
        from waitress.server import create_server

        self.map = {}
        server = create_server(
            app, host="127.0.0.1", port=0, map=self.map, threads=1, **kw
        )
        self.addCleanup(server.close)

        return server

    def _connect(self, server):
        client = socket.create_connection(
            (server.effective_host, int(server.effective_port)), timeout=10
        )
        self.addCleanup(client.close)

        return client

    def _pump(self, until, timeout=10):
        """Run the main loop until ``until()`` is true."""
        from waitress import wasyncore

        deadline = time.time() + timeout

        while not until() and time.time() < deadline:
            wasyncore.loop(timeout=0.01, map=self.map, count=1)

        self.assertTrue(until(), "timed out waiting for the server")

    def _read_all(self, client):
        chunks = []

        while True:
            chunk = client.recv(4096)

            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    def test_in_flight_request_gets_its_response(self):
        started = threading.Event()
        may_finish = threading.Event()

        def app(environ, start_response):
            started.set()
            may_finish.wait(10)
            start_response(
                "200 OK",
                [("Content-Type", "text/plain"), ("Content-Length", "5")],
            )

            return [b"hello"]

        server = self._makeServer(app)
        client = self._connect(server)
        client.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")

        # Hand the request off to the task thread, which then blocks.
        self._pump(started.is_set)

        # This is the moment a Ctrl-C would land: the response has not been
        # written yet, and it only ever will be if the main loop keeps running
        # for long enough to pick it up from the task thread.
        may_finish.set()
        server.graceful_shutdown()

        response = self._read_all(client)
        self.assertTrue(response.startswith(b"HTTP/1.0 200 OK"), response)
        self.assertTrue(response.endswith(b"hello"), response)

    def test_response_larger_than_the_socket_buffers_is_not_truncated(self):
        # A response that doesn't fit in the socket buffers can only be written
        # out by the main loop: the task thread parks itself on outbuf_lock
        # until the loop has drained enough of the outbuf for it to continue.
        # Stopping the loop at that point both truncates the response and
        # leaves the task thread wedged forever.
        body_len = 4 * 1024 * 1024
        chunk = b"x" * 65536
        started = threading.Event()

        def app(environ, start_response):
            started.set()
            start_response(
                "200 OK",
                [("Content-Type", "text/plain"), ("Content-Length", str(body_len))],
            )

            return [chunk] * (body_len // len(chunk))

        server = self._makeServer(app, outbuf_high_watermark=8192)
        client = self._connect(server)
        client.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")

        received = []
        reader = threading.Thread(
            target=lambda: received.append(self._read_all(client))
        )
        reader.daemon = True
        reader.start()

        self._pump(started.is_set)
        server.graceful_shutdown()

        reader.join(30)
        self.assertFalse(reader.is_alive(), "the connection was never closed")
        response = received[0]
        self.assertTrue(response.startswith(b"HTTP/1.0 200 OK"), response[:64])
        self.assertEqual(len(response) - response.index(b"\r\n\r\n") - 4, body_len)
        # And the task thread is not left parked on the outbuf lock.
        self.assertEqual(server.task_dispatcher.threads, set())

    def test_stops_accepting_new_connections(self):
        server = self._makeServer(dummy_app)
        host, port = server.effective_host, int(server.effective_port)

        server.graceful_shutdown()

        with self.assertRaises(OSError):
            conn = socket.create_connection((host, port), timeout=10)
            conn.close()

    def test_idle_keepalive_connection_is_closed(self):
        def app(environ, start_response):
            start_response(
                "200 OK",
                [("Content-Type", "text/plain"), ("Content-Length", "2")],
            )

            return [b"ok"]

        server = self._makeServer(app)
        client = self._connect(server)
        client.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")

        # Let the request complete. The connection stays open for reuse.
        self._pump(lambda: _peek(client))
        self.assertEqual(len(server.active_channels), 1)

        server.graceful_shutdown()

        # The connection is closed rather than left hanging around until the
        # channel timeout expires.
        self.assertEqual(server.active_channels, {})
        self.assertIn(b"200 OK", self._read_all(client))

    def test_run_shuts_down_gracefully(self):
        server = self._makeServer(dummy_app)
        server.asyncore = DummyAsyncore()
        server.run()
        self.assertIsNone(server.socket)
        self.assertEqual(server.task_dispatcher.threads, set())

    def test_trigger_is_closed(self):
        server = self._makeServer(dummy_app)
        trigger = server.trigger
        server.graceful_shutdown()
        # The pipe behind the trigger is what produces the "unclosed file"
        # ResourceWarning on shutdown when it is left dangling.
        # https://github.com/Pylons/waitress/issues/264
        self.assertTrue(trigger._closed)
        self.assertEqual(self.map, {})


class TestStartStop(unittest.TestCase):
    """
    Running the server in a background thread and stopping it again, the
    functionality webtest's StopableWSGIServer used to have to bolt on.
    """

    def _makeOne(self, app=None, listen="127.0.0.1:0", **kw):
        from waitress.server import create_server

        if app is None:
            app = hello_app
        server = create_server(app, listen=listen, map={}, **kw)
        self.addCleanup(server.close)

        return server

    def _get(self, host, port, path="/"):
        client = socket.create_connection((host, int(port)), timeout=10)

        try:
            client.sendall(
                f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode("latin-1")
            )
            chunks = []

            while True:
                chunk = client.recv(4096)

                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            client.close()

    def test_start_serves_requests_and_stop_stops(self):
        server = self._makeOne()
        server.start()

        # The port was picked by the OS, but we can still find out what it is,
        # without having to race anybody for it.
        # https://github.com/Pylons/waitress/issues/290
        host, port = server.effective_host, server.effective_port
        self.assertNotEqual(int(port), 0)
        self.assertIn(b"hello", self._get(host, port))

        self.assertTrue(server.stop(timeout=30))

        with self.assertRaises(OSError):
            self._get(host, port)

    def test_start_twice(self):
        server = self._makeOne()
        server.start()
        self.addCleanup(server.stop, 30)
        self.assertRaises(RuntimeError, server.start)

    def test_stop_can_be_called_twice(self):
        server = self._makeOne()
        server.start()
        self.assertTrue(server.stop(timeout=30))
        # The second one has nothing left to wait for.
        self.assertFalse(server.stop())

    def test_stop_without_start_does_not_wait(self):
        server = self._makeOne()
        self.assertFalse(server.stop())

    def test_stop_from_the_application(self):
        # Stopping from inside a request has to work, that's a request being
        # serviced that the shutdown then has to wait for.
        stopped = []
        holder = []

        def app(environ, start_response):
            stopped.append(holder[0].stop())
            start_response(
                "200 OK", [("Content-Type", "text/plain"), ("Content-Length", "7")]
            )

            return [b"stopped"]

        server = self._makeOne(app)
        holder.append(server)
        server.start()
        host, port = server.effective_host, server.effective_port
        thread = server._thread

        # The response still has to make it out the door.
        self.assertIn(b"stopped", self._get(host, port))
        # stop() did not wait: it was called from a thread that the shutdown
        # itself has to wait for, so waiting would have deadlocked.
        self.assertEqual(stopped, [False])

        thread.join(30)
        self.assertFalse(thread.is_alive())

    def test_multisocket_start_and_stop(self):
        server = self._makeOne(listen="127.0.0.1:0 127.0.0.1:0")
        self.assertEqual(server.__class__.__name__, "MultiSocketServer")
        server.start()

        for host, port in server.effective_listen:
            self.assertIn(b"hello", self._get(host, port))

        self.assertTrue(server.stop(timeout=30))

        for host, port in server.effective_listen:
            with self.assertRaises(OSError):
                self._get(host, port)


def hello_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", "5")])

    return [b"hello"]


def _peek(client):
    """Return True if there is anything to read on ``client``."""
    return bool(select.select([client], [], [], 0)[0])


if hasattr(socket, "AF_UNIX"):

    class TestUnixWSGIServer(unittest.TestCase):
        unix_socket = "/tmp/waitress.test.sock"

        def _makeOne(self, _start=True, _sock=None):
            from waitress.server import create_server

            self.inst = create_server(
                dummy_app,
                map={},
                _start=_start,
                _sock=_sock,
                _dispatcher=DummyTaskDispatcher(),
                unix_socket=self.unix_socket,
                unix_socket_perms="600",
            )
            return self.inst

        def _makeWithSockets(
            self,
            application=dummy_app,
            _dispatcher=None,
            map=None,
            _start=True,
            _sock=None,
            _server=None,
            sockets=None,
        ):
            from waitress.server import create_server

            _sockets = []
            if sockets is not None:
                _sockets = sockets
            self.inst = create_server(
                application,
                map=map,
                _dispatcher=_dispatcher,
                _start=_start,
                _sock=_sock,
                sockets=_sockets,
            )
            return self.inst

        def tearDown(self):
            self.inst.close()

        def _makeDummy(self, *args, **kwargs):
            sock = DummySock(*args, **kwargs)
            sock.family = socket.AF_UNIX
            return sock

        def test_unix(self):
            inst = self._makeOne(_start=False)
            self.assertEqual(inst.socket.family, socket.AF_UNIX)
            self.assertEqual(inst.socket.getsockname(), self.unix_socket)

        def test_handle_accept(self):
            # Working on the assumption that we only have to test the happy path
            # for Unix domain sockets as the other paths should've been covered
            # by inet sockets.
            client = self._makeDummy()
            listen = self._makeDummy(acceptresult=(client, None))
            inst = self._makeOne(_sock=listen)
            self.assertTrue(inst.accepting)
            self.assertEqual(inst.socket.listened, 1024)
            L = []
            inst.channel_class = lambda *arg, **kw: L.append(arg)
            inst.handle_accept()
            self.assertTrue(inst.socket.accepted)
            self.assertListEqual(client.opts, [])
            self.assertListEqual(L, [(inst, client, ("localhost", None), inst.adj)])

        def test_creates_new_sockinfo(self):
            from waitress.server import UnixWSGIServer

            self.inst = UnixWSGIServer(
                dummy_app, unix_socket=self.unix_socket, unix_socket_perms="600"
            )

            self.assertEqual(self.inst.sockinfo[0], socket.AF_UNIX)

        def test_create_with_unix_socket(self):
            from waitress.server import (
                BaseWSGIServer,
                MultiSocketServer,
                UnixWSGIServer,
            )

            sockets = [
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
            ]
            inst = self._makeWithSockets(sockets=sockets, _start=False)
            self.assertIsInstance(inst, MultiSocketServer)
            server = list(
                filter(lambda s: isinstance(s, BaseWSGIServer), inst.map.values())
            )
            self.assertIsInstance(server[0], UnixWSGIServer)
            self.assertIsInstance(server[1], UnixWSGIServer)


class DummySock(socket.socket):
    accepted = False
    blocking = False
    family = socket.AF_INET
    type = socket.SOCK_STREAM
    proto = 0

    def __init__(self, toraise=None, acceptresult=(None, None)):
        self.toraise = toraise
        self.acceptresult = acceptresult
        self.bound = None
        self.opts = []
        self.bind_called = False

    def bind(self, addr):
        self.bind_called = True
        self.bound = addr

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
        return "127.0.0.1"

    def setsockopt(self, *arg):
        self.opts.append(arg)

    def getsockopt(self, *arg):
        return 1

    def listen(self, num):
        self.listened = num

    def getsockname(self):
        return self.bound

    def close(self):
        pass


class DummyChannel:
    will_close = False
    close_when_flushed = False
    draining = False

    def __init__(self, requests=()):
        self.requests = list(requests)
        self.requests_lock = threading.Lock()
        self.closed = False

    def handle_close(self):
        self.closed = True


class DummyDrainServer:
    def __init__(self, active_channels=None):
        self.active_channels = active_channels if active_channels is not None else {}
        self.stopped_accepting = False

    def stop_accepting(self):
        self.stopped_accepting = True


class DummyShutdownAdj:
    asyncore_loop_timeout = 1
    asyncore_use_poll = False
    shutdown_timeout = 5

    def __init__(self, **kw):
        self.__dict__.update(kw)


class DummyAsyncoreLoop:
    def __init__(self, on_loop=None):
        self.calls = 0
        self.on_loop = on_loop

    def loop(self, timeout=30.0, use_poll=False, map=None, count=None):
        self.calls += 1

        if self.on_loop is not None:
            self.on_loop()


class DummyTaskDispatcher:
    was_shutdown = False

    def __init__(self):
        self.tasks = []

    def add_task(self, task):
        self.tasks.append(task)

    def shutdown(self, cancel_pending=True, timeout=5):
        self.was_shutdown = True
        self.shutdown_timeout = timeout


class DummyTask:
    serviced = False
    start_response_called = False
    wrote_header = False
    status = "200 OK"

    def __init__(self):
        self.response_headers = {}
        self.written = ""

    def service(self):  # pragma: no cover
        self.serviced = True


class DummyAdj:
    connection_limit = 1
    log_socket_errors = True
    socket_options = [("level", "optname", "value")]
    cleanup_interval = 900
    channel_timeout = 300
    shutdown_timeout = 5


class DummyAsyncore:
    def loop(self, timeout=30.0, use_poll=False, map=None, count=None):
        raise SystemExit


class DummyTrigger:
    def pull_trigger(self):
        self.pulled = True

    def close(self):
        pass


class DummyLogger:
    def __init__(self):
        self.logged = []

    def warning(self, msg, **kw):
        self.logged.append(msg)
