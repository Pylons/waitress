import io
import unittest


class TestThreadedTaskDispatcher(unittest.TestCase):
    def _makeOne(self):
        from waitress.task import ThreadedTaskDispatcher

        return ThreadedTaskDispatcher()

    def test_handler_thread_task_raises(self):
        inst = self._makeOne()
        inst.threads.add(0)
        inst.logger = DummyLogger()

        class BadDummyTask(DummyTask):
            def service(self):
                super().service()
                inst.stop_count += 1
                raise Exception

        task = BadDummyTask()
        inst.logger = DummyLogger()
        inst.queue.append(task)
        inst.active_count += 1
        inst.handler_thread(0)
        self.assertEqual(inst.stop_count, 0)
        self.assertEqual(inst.active_count, 0)
        self.assertSetEqual(inst.threads, set())
        self.assertEqual(len(inst.logger.logged), 1)

    def test_set_thread_count_increase(self):
        inst = self._makeOne()
        L = []
        inst.start_new_thread = lambda *x: L.append(x)
        inst.set_thread_count(1)
        self.assertListEqual(L, [(inst.handler_thread, 0)])

    def test_set_thread_count_increase_with_existing(self):
        inst = self._makeOne()
        L = []
        inst.threads = {0}
        inst.start_new_thread = lambda *x: L.append(x)
        inst.set_thread_count(2)
        self.assertListEqual(L, [(inst.handler_thread, 1)])

    def test_set_thread_count_decrease(self):
        inst = self._makeOne()
        inst.threads = {0, 1}
        inst.set_thread_count(1)
        self.assertEqual(inst.stop_count, 1)

    def test_set_thread_count_same(self):
        inst = self._makeOne()
        L = []
        inst.start_new_thread = lambda *x: L.append(x)
        inst.threads = {0}
        inst.set_thread_count(1)
        self.assertListEqual(L, [])

    def test_add_task_with_idle_threads(self):
        task = DummyTask()
        inst = self._makeOne()
        inst.threads.add(0)
        inst.queue_logger = DummyLogger()
        inst.add_task(task)
        self.assertEqual(len(inst.queue), 1)
        self.assertEqual(len(inst.queue_logger.logged), 0)

    def test_add_task_with_all_busy_threads(self):
        task = DummyTask()
        inst = self._makeOne()
        inst.queue_logger = DummyLogger()
        inst.add_task(task)
        self.assertEqual(len(inst.queue_logger.logged), 1)
        inst.add_task(task)
        self.assertEqual(len(inst.queue_logger.logged), 2)

    def test_shutdown_one_thread(self):
        inst = self._makeOne()
        inst.threads.add(0)
        inst.logger = DummyLogger()
        task = DummyTask()
        inst.queue.append(task)
        self.assertTrue(inst.shutdown(timeout=0.01))
        self.assertListEqual(
            inst.logger.logged,
            [
                "1 thread(s) still running",
                "Canceling 1 pending task(s)",
            ],
        )
        self.assertTrue(task.cancelled)

    def test_shutdown_no_threads(self):
        inst = self._makeOne()
        self.assertTrue(inst.shutdown(timeout=0.01))

    def test_shutdown_no_cancel_pending(self):
        inst = self._makeOne()
        self.assertFalse(inst.shutdown(cancel_pending=False, timeout=0.01))


class TestTask(unittest.TestCase):
    def _makeOne(self, channel=None, request=None):
        if channel is None:
            channel = DummyChannel()
        if request is None:
            request = DummyParser()
        from waitress.task import Task

        return Task(channel, request)

    def test_ctor_version_not_in_known(self):
        request = DummyParser()
        request.version = "8.4"
        inst = self._makeOne(request=request)
        self.assertEqual(inst.version, "1.0")

    def test_build_response_header_bad_http_version(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "8.4"
        self.assertRaises(AssertionError, inst.build_response_header)

    def test_build_response_header_v10_keepalive_no_content_length(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.request.headers["CONNECTION"] = "keep-alive"
        inst.version = "1.0"
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b"HTTP/1.0 200 OK")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")
        self.assertTrue(inst.close_on_finish)
        self.assertIn(("Connection", "close"), inst.response_headers)

    def test_build_response_header_v10_keepalive_with_content_length(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.request.headers["CONNECTION"] = "keep-alive"
        inst.response_headers = [("Content-Length", "10")]
        inst.version = "1.0"
        inst.content_length = 0
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b"HTTP/1.0 200 OK")
        self.assertEqual(lines[1], b"Connection: Keep-Alive")
        self.assertEqual(lines[2], b"Content-Length: 10")
        self.assertTrue(lines[3].startswith(b"Date:"))
        self.assertEqual(lines[4], b"Server: waitress")
        self.assertFalse(inst.close_on_finish)

    def test_build_response_header_v11_connection_closed_by_client(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.1"
        inst.request.headers["CONNECTION"] = "close"
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b"HTTP/1.1 200 OK")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")
        self.assertEqual(lines[4], b"Transfer-Encoding: chunked")
        self.assertIn(("Connection", "close"), inst.response_headers)
        self.assertTrue(inst.close_on_finish)

    def test_build_response_header_v11_connection_keepalive_by_client(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.request.headers["CONNECTION"] = "keep-alive"
        inst.version = "1.1"
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b"HTTP/1.1 200 OK")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")
        self.assertEqual(lines[4], b"Transfer-Encoding: chunked")
        self.assertIn(("Connection", "close"), inst.response_headers)
        self.assertTrue(inst.close_on_finish)

    def test_build_response_header_v11_200_no_content_length(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.1"
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b"HTTP/1.1 200 OK")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")
        self.assertEqual(lines[4], b"Transfer-Encoding: chunked")
        self.assertTrue(inst.close_on_finish)
        self.assertIn(("Connection", "close"), inst.response_headers)

    def test_build_response_header_v11_204_no_content_length_or_transfer_encoding(self):
        # RFC 7230: MUST NOT send Transfer-Encoding or Content-Length
        # for any response with a status code of 1xx or 204.
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.1"
        inst.status = "204 No Content"
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b"HTTP/1.1 204 No Content")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")
        self.assertTrue(inst.close_on_finish)
        self.assertIn(("Connection", "close"), inst.response_headers)

    def test_build_response_header_v11_1xx_no_content_length_or_transfer_encoding(self):
        # RFC 7230: MUST NOT send Transfer-Encoding or Content-Length
        # for any response with a status code of 1xx or 204.
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.1"
        inst.status = "100 Continue"
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b"HTTP/1.1 100 Continue")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")
        self.assertTrue(inst.close_on_finish)
        self.assertIn(("Connection", "close"), inst.response_headers)

    def test_build_response_header_v11_304_no_content_length_or_transfer_encoding(self):
        # RFC 7230: MUST NOT send Transfer-Encoding or Content-Length
        # for any response with a status code of 1xx, 204 or 304.
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.1"
        inst.status = "304 Not Modified"
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b"HTTP/1.1 304 Not Modified")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")
        self.assertTrue(inst.close_on_finish)
        self.assertIn(("Connection", "close"), inst.response_headers)

    def test_build_response_header_via_added(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.0"
        inst.response_headers = [("Server", "abc")]
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], b"HTTP/1.0 200 OK")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: abc")
        self.assertEqual(lines[4], b"Via: waitress")

    def test_build_response_header_date_exists(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.0"
        inst.response_headers = [("Date", "date")]
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b"HTTP/1.0 200 OK")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")

    def test_build_response_header_preexisting_content_length(self):
        inst = self._makeOne()
        inst.request = DummyParser()
        inst.version = "1.1"
        inst.content_length = 100
        result = inst.build_response_header()
        lines = filter_lines(result)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], b"HTTP/1.1 200 OK")
        self.assertEqual(lines[1], b"Content-Length: 100")
        self.assertTrue(lines[2].startswith(b"Date:"))
        self.assertEqual(lines[3], b"Server: waitress")

    def test_remove_content_length_header(self):
        inst = self._makeOne()
        inst.response_headers = [("Content-Length", "70")]
        inst.remove_content_length_header()
        self.assertListEqual(inst.response_headers, [])

    def test_remove_content_length_header_with_other(self):
        inst = self._makeOne()
        inst.response_headers = [
            ("Content-Length", "70"),
            ("Content-Type", "text/html"),
        ]
        inst.remove_content_length_header()
        self.assertListEqual(inst.response_headers, [("Content-Type", "text/html")])

    def test_start(self):
        inst = self._makeOne()
        inst.start()
        self.assertTrue(inst.start_time)

    def test_finish_didnt_write_header(self):
        inst = self._makeOne()
        inst.wrote_header = False
        inst.complete = True
        inst.finish()
        self.assertTrue(inst.channel.written)

    def test_finish_wrote_header(self):
        inst = self._makeOne()
        inst.wrote_header = True
        inst.finish()
        self.assertFalse(inst.channel.written)

    def test_finish_chunked_response(self):
        inst = self._makeOne()
        inst.wrote_header = True
        inst.chunked_response = True
        inst.finish()
        self.assertEqual(inst.channel.written, b"0\r\n\r\n")

    def test_write_wrote_header(self):
        inst = self._makeOne()
        inst.wrote_header = True
        inst.complete = True
        inst.content_length = 3
        inst.write(b"abc")
        self.assertEqual(inst.channel.written, b"abc")

    def test_write_header_not_written(self):
        inst = self._makeOne()
        inst.wrote_header = False
        inst.complete = True
        inst.write(b"abc")
        self.assertTrue(inst.channel.written)
        self.assertTrue(inst.wrote_header)

    def test_write_start_response_uncalled(self):
        inst = self._makeOne()
        self.assertRaises(RuntimeError, inst.write, b"")

    def test_write_chunked_response(self):
        inst = self._makeOne()
        inst.wrote_header = True
        inst.chunked_response = True
        inst.complete = True
        inst.write(b"abc")
        self.assertEqual(inst.channel.written, b"3\r\nabc\r\n")

    def test_write_preexisting_content_length(self):
        inst = self._makeOne()
        inst.wrote_header = True
        inst.complete = True
        inst.content_length = 1
        inst.logger = DummyLogger()
        inst.write(b"abc")
        self.assertTrue(inst.channel.written)
        self.assertTrue(inst.logged_write_excess)
        self.assertEqual(len(inst.logger.logged), 1)


class TestWSGITask(unittest.TestCase):
    def _makeOne(self, channel=None, request=None):
        if channel is None:
            channel = DummyChannel()
        if request is None:
            request = DummyParser()
        from waitress.task import WSGITask

        return WSGITask(channel, request)

    def test_service(self):
        inst = self._makeOne()

        def execute():
            inst.executed = True

        inst.execute = execute
        inst.complete = True
        inst.service()
        self.assertTrue(inst.start_time)
        self.assertTrue(inst.close_on_finish)
        self.assertTrue(inst.channel.written)
        self.assertTrue(inst.executed)

    def test_service_server_raises_socket_error(self):
        import socket

        inst = self._makeOne()

        def execute():
            raise OSError

        inst.execute = execute
        self.assertRaises(socket.error, inst.service)
        self.assertTrue(inst.start_time)
        self.assertTrue(inst.close_on_finish)
        self.assertFalse(inst.channel.written)

    def test_execute_app_calls_start_response_twice_wo_exc_info(self):
        def app(environ, start_response):
            start_response("200 OK", [])
            start_response("200 OK", [])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(AssertionError, inst.execute)

    def test_execute_app_calls_start_response_w_exc_info_complete(self):
        def app(environ, start_response):
            start_response("200 OK", [], [ValueError, ValueError(), None])
            return [b"a"]

        inst = self._makeOne()
        inst.complete = True
        inst.channel.server.application = app
        inst.execute()
        self.assertTrue(inst.complete)
        self.assertEqual(inst.status, "200 OK")
        self.assertTrue(inst.channel.written)

    def test_execute_app_calls_start_response_w_excinf_headers_unwritten(self):
        def app(environ, start_response):
            start_response("200 OK", [], [ValueError, None, None])
            return [b"a"]

        inst = self._makeOne()
        inst.wrote_header = False
        inst.channel.server.application = app
        inst.response_headers = [("a", "b")]
        inst.execute()
        self.assertTrue(inst.complete)
        self.assertEqual(inst.status, "200 OK")
        self.assertTrue(inst.channel.written)
        self.assertNotIn(("a", "b"), inst.response_headers)

    def test_execute_app_calls_start_response_w_excinf_headers_written(self):
        def app(environ, start_response):
            start_response("200 OK", [], [ValueError, ValueError(), None])

        inst = self._makeOne()
        inst.complete = True
        inst.wrote_header = True
        inst.channel.server.application = app
        self.assertRaises(ValueError, inst.execute)

    def test_execute_bad_header_key(self):
        def app(environ, start_response):
            start_response("200 OK", [(None, "a")])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(AssertionError, inst.execute)

    def test_execute_bad_header_value(self):
        def app(environ, start_response):
            start_response("200 OK", [("a", None)])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(AssertionError, inst.execute)

    def test_execute_hopbyhop_header(self):
        def app(environ, start_response):
            start_response("200 OK", [("Connection", "close")])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(AssertionError, inst.execute)

    def test_execute_bad_header_value_control_characters(self):
        def app(environ, start_response):
            start_response("200 OK", [("a", "\n")])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(ValueError, inst.execute)

    def test_execute_bad_header_name_control_characters(self):
        def app(environ, start_response):
            start_response("200 OK", [("a\r", "value")])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(ValueError, inst.execute)

    def test_execute_bad_status_control_characters(self):
        def app(environ, start_response):
            start_response("200 OK\r", [])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(ValueError, inst.execute)

    def test_preserve_header_value_order(self):
        def app(environ, start_response):
            write = start_response("200 OK", [("C", "b"), ("A", "b"), ("A", "a")])
            write(b"abc")
            return []

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertIn(b"A: b\r\nA: a\r\nC: b\r\n", inst.channel.written)

    def test_execute_bad_status_value(self):
        def app(environ, start_response):
            start_response(None, [])

        inst = self._makeOne()
        inst.channel.server.application = app
        self.assertRaises(AssertionError, inst.execute)

    def test_execute_with_content_length_header(self):
        def app(environ, start_response):
            start_response("200 OK", [("Content-Length", "1")])
            return [b"a"]

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertEqual(inst.content_length, 1)

    def test_execute_app_calls_write(self):
        def app(environ, start_response):
            write = start_response("200 OK", [("Content-Length", "3")])
            write(b"abc")
            return []

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertEqual(inst.channel.written[-3:], b"abc")

    def test_execute_app_returns_len1_chunk_without_cl(self):
        def app(environ, start_response):
            start_response("200 OK", [])
            return [b"abc"]

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertEqual(inst.content_length, 3)

    def test_execute_app_returns_empty_chunk_as_first(self):
        def app(environ, start_response):
            start_response("200 OK", [])
            return ["", b"abc"]

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertIsNone(inst.content_length)

    def test_execute_app_returns_too_many_bytes(self):
        def app(environ, start_response):
            start_response("200 OK", [("Content-Length", "1")])
            return [b"abc"]

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.logger = DummyLogger()
        inst.execute()
        self.assertTrue(inst.close_on_finish)
        self.assertEqual(len(inst.logger.logged), 1)

    def test_execute_app_returns_too_few_bytes(self):
        def app(environ, start_response):
            start_response("200 OK", [("Content-Length", "3")])
            return [b"a"]

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.logger = DummyLogger()
        inst.execute()
        self.assertTrue(inst.close_on_finish)
        self.assertEqual(len(inst.logger.logged), 1)

    def test_execute_app_head_with_content_length(self):
        def app(environ, start_response):
            start_response("200 OK", [("Content-Length", "3")])
            return [b""]

        inst = self._makeOne()
        inst.request.command = "HEAD"
        inst.channel.server.application = app
        inst.logger = DummyLogger()
        inst.execute()
        self.assertFalse(inst.close_on_finish)
        self.assertEqual(len(inst.logger.logged), 0)

    def test_execute_app_without_body_204_logged(self):
        def app(environ, start_response):
            start_response("204 No Content", [("Content-Length", "3")])
            return [b"abc"]

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.logger = DummyLogger()
        inst.execute()
        self.assertTrue(inst.close_on_finish)
        self.assertNotIn(b"abc", inst.channel.written)
        self.assertNotIn(b"Content-Length", inst.channel.written)
        self.assertNotIn(b"Transfer-Encoding", inst.channel.written)
        self.assertEqual(len(inst.logger.logged), 1)

    def test_execute_app_without_body_304_logged(self):
        def app(environ, start_response):
            start_response("304 Not Modified", [("Content-Length", "3")])
            return [b"abc"]

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.logger = DummyLogger()
        inst.execute()
        self.assertTrue(inst.close_on_finish)
        self.assertNotIn(b"abc", inst.channel.written)
        self.assertNotIn(b"Content-Length", inst.channel.written)
        self.assertNotIn(b"Transfer-Encoding", inst.channel.written)
        self.assertEqual(len(inst.logger.logged), 1)

    def test_execute_app_returns_closeable(self):
        class closeable(list):
            def close(self):
                self.closed = True

        foo = closeable([b"abc"])

        def app(environ, start_response):
            start_response("200 OK", [("Content-Length", "3")])
            return foo

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertTrue(foo.closed)

    def test_execute_app_returns_filewrapper_prepare_returns_True(self):
        from waitress.buffers import ReadOnlyFileBasedBuffer

        f = io.BytesIO(b"abc")
        app_iter = ReadOnlyFileBasedBuffer(f, 8192)

        def app(environ, start_response):
            start_response("200 OK", [("Content-Length", "3")])
            return app_iter

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertTrue(inst.channel.written)  # header
        self.assertListEqual(inst.channel.otherdata, [app_iter])

    def test_execute_app_returns_filewrapper_prepare_returns_True_nocl(self):
        from waitress.buffers import ReadOnlyFileBasedBuffer

        f = io.BytesIO(b"abc")
        app_iter = ReadOnlyFileBasedBuffer(f, 8192)

        def app(environ, start_response):
            start_response("200 OK", [])
            return app_iter

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.execute()
        self.assertTrue(inst.channel.written)  # header
        self.assertListEqual(inst.channel.otherdata, [app_iter])
        self.assertEqual(inst.content_length, 3)

    def test_execute_app_returns_filewrapper_prepare_returns_True_badcl(self):
        from waitress.buffers import ReadOnlyFileBasedBuffer

        f = io.BytesIO(b"abc")
        app_iter = ReadOnlyFileBasedBuffer(f, 8192)

        def app(environ, start_response):
            start_response("200 OK", [])
            return app_iter

        inst = self._makeOne()
        inst.channel.server.application = app
        inst.content_length = 10
        inst.response_headers = [("Content-Length", "10")]
        inst.execute()
        self.assertTrue(inst.channel.written)  # header
        self.assertListEqual(inst.channel.otherdata, [app_iter])
        self.assertEqual(inst.content_length, 3)
        self.assertIn(("Content-Length", "3"), inst.response_headers)

    def test_get_environment_already_cached(self):
        inst = self._makeOne()
        inst.environ = {}
        self.assertDictEqual(inst.get_environment(), inst.environ)

    def test_get_environment_path_startswith_more_than_one_slash(self):
        inst = self._makeOne()
        request = DummyParser()
        request.path = "///abc"
        inst.request = request
        environ = inst.get_environment()
        self.assertEqual(environ["PATH_INFO"], "/abc")

    def test_get_environment_path_empty(self):
        inst = self._makeOne()
        request = DummyParser()
        request.path = ""
        inst.request = request
        environ = inst.get_environment()
        self.assertEqual(environ["PATH_INFO"], "")

    def test_get_environment_no_query(self):
        inst = self._makeOne()
        request = DummyParser()
        inst.request = request
        environ = inst.get_environment()
        self.assertEqual(environ["QUERY_STRING"], "")

    def test_get_environment_with_query(self):
        inst = self._makeOne()
        request = DummyParser()
        request.query = "abc"
        inst.request = request
        environ = inst.get_environment()
        self.assertEqual(environ["QUERY_STRING"], "abc")

    def test_get_environ_with_url_prefix_miss(self):
        inst = self._makeOne()
        inst.channel.server.adj.url_prefix = "/foo"
        request = DummyParser()
        request.path = "/bar"
        inst.request = request
        environ = inst.get_environment()
        self.assertEqual(environ["PATH_INFO"], "/bar")
        self.assertEqual(environ["SCRIPT_NAME"], "/foo")

    def test_get_environ_with_url_prefix_hit(self):
        inst = self._makeOne()
        inst.channel.server.adj.url_prefix = "/foo"
        request = DummyParser()
        request.path = "/foo/fuz"
        inst.request = request
        environ = inst.get_environment()
        self.assertEqual(environ["PATH_INFO"], "/fuz")
        self.assertEqual(environ["SCRIPT_NAME"], "/foo")

    def test_get_environ_with_url_prefix_empty_path(self):
        inst = self._makeOne()
        inst.channel.server.adj.url_prefix = "/foo"
        request = DummyParser()
        request.path = "/foo"
        inst.request = request
        environ = inst.get_environment()
        self.assertEqual(environ["PATH_INFO"], "")
        self.assertEqual(environ["SCRIPT_NAME"], "/foo")

    def test_get_environment_values(self):
        import sys

        inst = self._makeOne()
        request = DummyParser()
        request.headers = {
            "CONTENT_TYPE": "abc",
            "CONTENT_LENGTH": "10",
            "X_FOO": "\xa0BAR\x85",
            "CONNECTION": "close",
        }
        request.query = "abc"
        inst.request = request
        environ = inst.get_environment()

        # nail the keys of environ
        self.assertListEqual(
            sorted(environ.keys()),
            [
                "CONTENT_LENGTH",
                "CONTENT_TYPE",
                "HTTP_CONNECTION",
                "HTTP_X_FOO",
                "PATH_INFO",
                "QUERY_STRING",
                "REMOTE_ADDR",
                "REMOTE_HOST",
                "REMOTE_PORT",
                "REQUEST_METHOD",
                "REQUEST_URI",
                "SCRIPT_NAME",
                "SERVER_NAME",
                "SERVER_PORT",
                "SERVER_PROTOCOL",
                "SERVER_SOFTWARE",
                "waitress.client_disconnected",
                "wsgi.errors",
                "wsgi.file_wrapper",
                "wsgi.input",
                "wsgi.input_terminated",
                "wsgi.multiprocess",
                "wsgi.multithread",
                "wsgi.run_once",
                "wsgi.url_scheme",
                "wsgi.version",
            ],
        )

        self.assertEqual(environ["REQUEST_METHOD"], "GET")
        self.assertEqual(environ["SERVER_PORT"], "80")
        self.assertEqual(environ["SERVER_NAME"], "localhost")
        self.assertEqual(environ["SERVER_SOFTWARE"], "waitress")
        self.assertEqual(environ["SERVER_PROTOCOL"], "HTTP/1.0")
        self.assertEqual(environ["SCRIPT_NAME"], "")
        self.assertEqual(environ["HTTP_CONNECTION"], "close")
        self.assertEqual(environ["PATH_INFO"], "/")
        self.assertEqual(environ["QUERY_STRING"], "abc")
        self.assertEqual(environ["REMOTE_ADDR"], "127.0.0.1")
        self.assertEqual(environ["REMOTE_HOST"], "127.0.0.1")
        self.assertEqual(environ["REMOTE_PORT"], "39830")
        self.assertEqual(environ["CONTENT_TYPE"], "abc")
        self.assertEqual(environ["CONTENT_LENGTH"], "10")
        # Make sure we don't strip non RFC compliant whitespace
        self.assertEqual(environ["HTTP_X_FOO"], "\xa0BAR\x85")
        self.assertEqual(environ["wsgi.version"], (1, 0))
        self.assertEqual(environ["wsgi.url_scheme"], "http")
        self.assertEqual(environ["wsgi.errors"], sys.stderr)
        self.assertTrue(environ["wsgi.multithread"])
        self.assertFalse(environ["wsgi.multiprocess"])
        self.assertFalse(environ["wsgi.run_once"])
        self.assertEqual(environ["wsgi.input"], "stream")
        self.assertTrue(environ["wsgi.input_terminated"])
        self.assertEqual(inst.environ, environ)


class TestErrorTask(unittest.TestCase):
    def _makeOne(self, channel=None, request=None):
        if channel is None:
            channel = DummyChannel()
        if request is None:
            request = DummyParser()
            request.error = self._makeDummyError()
        from waitress.task import ErrorTask

        return ErrorTask(channel, request)

    def _makeDummyError(self):
        from waitress.utilities import Error

        e = Error("body")
        e.code = 432
        e.reason = "Too Ugly"
        return e

    def test_execute_http_10(self):
        inst = self._makeOne()
        inst.execute()
        lines = filter_lines(inst.channel.written)
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[0], b"HTTP/1.0 432 Too Ugly")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertEqual(lines[2], b"Content-Length: 43")
        self.assertEqual(lines[3], b"Content-Type: text/plain; charset=utf-8")
        self.assertTrue(lines[4])
        self.assertEqual(lines[5], b"Server: waitress")
        self.assertEqual(lines[6], b"Too Ugly")
        self.assertEqual(lines[7], b"body")
        self.assertEqual(lines[8], b"(generated by waitress)")

    def test_execute_http_11(self):
        inst = self._makeOne()
        inst.version = "1.1"
        inst.execute()
        lines = filter_lines(inst.channel.written)
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[0], b"HTTP/1.1 432 Too Ugly")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertEqual(lines[2], b"Content-Length: 43")
        self.assertEqual(lines[3], b"Content-Type: text/plain; charset=utf-8")
        self.assertTrue(lines[4])
        self.assertEqual(lines[5], b"Server: waitress")
        self.assertEqual(lines[6], b"Too Ugly")
        self.assertEqual(lines[7], b"body")
        self.assertEqual(lines[8], b"(generated by waitress)")

    def test_execute_http_11_close(self):
        inst = self._makeOne()
        inst.version = "1.1"
        inst.request.headers["CONNECTION"] = "close"
        inst.execute()
        lines = filter_lines(inst.channel.written)
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[0], b"HTTP/1.1 432 Too Ugly")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertEqual(lines[2], b"Content-Length: 43")
        self.assertEqual(lines[3], b"Content-Type: text/plain; charset=utf-8")
        self.assertTrue(lines[4])
        self.assertEqual(lines[5], b"Server: waitress")
        self.assertEqual(lines[6], b"Too Ugly")
        self.assertEqual(lines[7], b"body")
        self.assertEqual(lines[8], b"(generated by waitress)")

    def test_execute_http_11_keep_forces_close(self):
        inst = self._makeOne()
        inst.version = "1.1"
        inst.request.headers["CONNECTION"] = "keep-alive"
        inst.execute()
        lines = filter_lines(inst.channel.written)
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[0], b"HTTP/1.1 432 Too Ugly")
        self.assertEqual(lines[1], b"Connection: close")
        self.assertEqual(lines[2], b"Content-Length: 43")
        self.assertEqual(lines[3], b"Content-Type: text/plain; charset=utf-8")
        self.assertTrue(lines[4])
        self.assertEqual(lines[5], b"Server: waitress")
        self.assertEqual(lines[6], b"Too Ugly")
        self.assertEqual(lines[7], b"body")
        self.assertEqual(lines[8], b"(generated by waitress)")


class DummyTask:
    serviced = False
    cancelled = False

    def service(self):
        self.serviced = True

    def cancel(self):
        self.cancelled = True


class DummyAdj:
    log_socket_errors = True
    ident = "waitress"
    host = "127.0.0.1"
    port = 80
    url_prefix = ""


class DummyServer:
    server_name = "localhost"
    effective_port = 80

    def __init__(self):
        self.adj = DummyAdj()


class DummyChannel:
    closed_when_done = False
    adj = DummyAdj()
    creation_time = 0
    addr = ("127.0.0.1", 39830)

    def check_client_disconnected(self):
        # For now, until we have tests handling this feature
        return False

    def __init__(self, server=None):
        if server is None:
            server = DummyServer()
        self.server = server
        self.written = b""
        self.otherdata = []

    def write_soon(self, data):
        if isinstance(data, bytes):
            self.written += data
        else:
            self.otherdata.append(data)
        return len(data)


class DummyParser:
    version = "1.0"
    command = "GET"
    path = "/"
    request_uri = "/"
    query = ""
    url_scheme = "http"
    expect_continue = False
    headers_finished = False

    def __init__(self):
        self.headers = {}

    def get_body_stream(self):
        return "stream"


def filter_lines(s):
    return list(filter(None, s.split(b"\r\n")))


class DummyLogger:
    def __init__(self):
        self.logged = []

    def warning(self, msg, *args):
        self.logged.append(msg % args)

    def exception(self, msg, *args):
        self.logged.append(msg % args)
