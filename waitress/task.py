##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################

import socket
import sys
import time
import traceback

from waitress.utilities import (
    build_http_date,
    )

from waitress.compat import (
    tobytes,
    Queue,
    Empty,
    thread,
    reraise,
    tostr,
    )

rename_headers = {
    'CONTENT_LENGTH' : 'CONTENT_LENGTH',
    'CONTENT_TYPE'   : 'CONTENT_TYPE',
    'CONNECTION'     : 'CONNECTION_TYPE',
    }

class JustTesting(Exception):
    pass

class ThreadedTaskDispatcher(object):
    """A Task Dispatcher that creates a thread for each task.
    See ITaskDispatcher.
    """

    stop_count = 0  # Number of threads that will stop soon.
    stderr = sys.stderr
    start_new_thread = thread.start_new_thread

    def __init__(self):
        self.threads = {}  # { thread number -> 1 }
        self.queue = Queue()
        self.thread_mgmt_lock = thread.allocate_lock()

    def handler_thread(self, thread_no):
        threads = self.threads
        try:
            while threads.get(thread_no):
                task = self.queue.get()
                if task is None:
                    # Special value: kill this thread.
                    break
                try:
                    task.service()
                except Exception as e:
                    traceback.print_exc(None, self.stderr)
                    self.stderr.flush()
                    if isinstance(e, JustTesting):
                        break
        finally:
            mlock = self.thread_mgmt_lock
            mlock.acquire()
            try:
                self.stop_count -= 1
                threads.pop(thread_no, None)
            finally:
                mlock.release()

    def set_thread_count(self, count):
        """See waitress.interfaces.ITaskDispatcher"""
        mlock = self.thread_mgmt_lock
        mlock.acquire()
        try:
            threads = self.threads
            thread_no = 0
            running = len(threads) - self.stop_count
            while running < count:
                # Start threads.
                while thread_no in threads:
                    thread_no = thread_no + 1
                threads[thread_no] = 1
                running += 1
                self.start_new_thread(self.handler_thread, (thread_no,))
                thread_no = thread_no + 1
            if running > count:
                # Stop threads.
                to_stop = running - count
                self.stop_count += to_stop
                for n in range(to_stop):
                    self.queue.put(None)
                    running -= 1
        finally:
            mlock.release()

    def add_task(self, task):
        """See waitress.interfaces.ITaskDispatcher"""
        try:
            task.defer()
            self.queue.put(task)
        except:
            task.cancel()
            raise

    def shutdown(self, cancel_pending=True, timeout=5):
        """See waitress.interfaces.ITaskDispatcher"""
        self.set_thread_count(0)
        # Ensure the threads shut down.
        threads = self.threads
        expiration = time.time() + timeout
        while threads:
            if time.time() >= expiration:
                self.stderr.write("%d thread(s) still running" % len(threads))
                self.stderr.flush()
                break
            time.sleep(0.1)
        if cancel_pending:
            # Cancel remaining tasks.
            try:
                queue = self.queue
                while not queue.empty():
                    task = queue.get()
                    if task is not None:
                        task.cancel()
            except Empty: # pragma: no cover
                pass
            return True
        return False

class HTTPTask(object):
    """An HTTP task accepts a request and writes to a channel.

       See ITask, IHeaderOutput.
    """

    instream = None
    close_on_finish = False
    status = '200 OK'
    wrote_header = False
    accumulated_headers = None
    start_time = 0
    environ = None
    start_response_called = False
    content_length = -1
    content_bytes_written = 0

    def __init__(self, channel, request_data):
        self.channel = channel
        self.request_data = request_data
        self.response_headers = []
        version = request_data.version
        if version not in ('1.0', '1.1'):
            # fall back to a version we support.
            version = '1.0'
        self.version = version
        self.expect_continue = self.request_data.expect_continue

    def service(self):
        """See waitress.interfaces.ITask"""
        try:
            try:
                self.start()
                self.execute()
                self.finish()
            except socket.error:
                self.close_on_finish = True
                if self.channel.adj.log_socket_errors:
                    raise
        finally:
            if self.close_on_finish:
                self.channel.close_when_done()

    def cancel(self):
        """See waitress.interfaces.ITask"""
        self.channel.close_when_done()

    def defer(self):
        """See waitress.interfaces.ITask"""
        pass

    def execute(self):
        env = self.get_environment()

        def start_response(status, headers, exc_info=None):
            self.start_response_called = True
            if self.wrote_header and not exc_info:
                raise AssertionError("start_response called a second time "
                                     "without providing exc_info.")
            if exc_info:
                try:
                    if self.wrote_header:
                        # higher levels will catch and handle raised exception:
                        # 1. "service" method in task.py
                        # 2. "service" method in channel.py
                        # 3. "handler_thread" method in task.py
                        reraise(exc_info[0], exc_info[1], exc_info[2])
                    else:
                        # As per WSGI spec existing headers must be cleared
                        self.response_headers = []
                finally:
                    exc_info = None

            # Prepare the headers for output
            if not isinstance(status, str):
                raise ValueError('status %s is not a string' % status)

            self.status = status

            for k, v in headers:
                if not isinstance(k, str):
                    raise ValueError(
                        'Header name %r is not a string in %s' % (k, (k, v))
                        )
                if not isinstance(v, str):
                    raise ValueError(
                        'Header value %r is not a string in %s' % (v, (k, v))
                        )
                k = '-'.join([x.capitalize() for x in k.split('-')])
                self.response_headers.append((tostr(k), tostr(v)))
                if k == 'Content-Length':
                    self.content_length = int(v)

            # Return the write method used to write the response data.
            return self.write

        # Call the application to handle the request and write a response
        app_iter = self.channel.server.application(env, start_response)

        app_iter_len = None
        if hasattr(app_iter, '__len__'):
            app_iter_len = len(app_iter)

        try:
            # By iterating manually at this point, we execute task.write()
            # multiple times, allowing partial data to be sent.
            first_chunk_len = None
            for chunk in app_iter:
                if first_chunk_len is None:
                    first_chunk_len = len(chunk)
                # transmit headers only after first iteration of the iterable
                # that returns a non-empty bytestring (PEP 3333)
                if not chunk:
                    continue
                # Set a Content-Length header if one is not supplied.
                # start_response may not have been called until first iteration
                # as per PEP
                cl = self.content_length
                has_content_length = cl != -1
                if not has_content_length and app_iter_len == 1:
                    cl = self.content_length = first_chunk_len
                towrite = chunk
                if has_content_length:
                    towrite = chunk[:cl-self.content_bytes_written]
                self.write(towrite)
                if towrite != chunk:
                    self.channel.server.log_info(
                        'app_iter content exceeded the number of bytes '
                        'specified by Content-Length header (%s)' % cl)
                    break

            cl = self.content_length
            if cl != -1:
                if self.content_bytes_written != cl:
                    # close the connection so the client isn't sitting around
                    # waiting for more data
                    self.close_on_finish = True
                    self.channel.server.log_info(
                        'app_iter returned too few bytes (%s) '
                        'for specified Content-Length (%s)' % (
                            self.content_bytes_written,
                            cl)
                        )
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()

    def write(self, data):
        if not self.start_response_called:
            raise RuntimeError('start_response was not called before body '
                               'written')
        channel = self.channel
        if not self.wrote_header:
            rh = self.build_response_header()
            channel.write(rh)
            self.wrote_header = True
        if data:
            self.content_bytes_written += len(data)
            channel.write(data)

    def build_response_header(self):
        version = self.version
        # Figure out whether the connection should be closed.
        connection = self.request_data.headers.get('CONNECTION', '').lower()
        response_headers = self.response_headers
        connection_header = None
        content_length_header = None
        transfer_encoding_header = None
        date_header = None
        server_header = None

        for headername, headerval in response_headers:
            if headername == 'Connection':
                connection_header = headerval.lower()
            if headername == 'Content-Length':
                content_length_header = headerval
            if headername == 'Transfer-Encoding':
                transfer_encoding_header = headerval.lower()
            if headername == 'Date':
                date_header = headerval
            if headername == 'Server':
                server_header = headerval

        if content_length_header is None and self.content_length != -1:
            content_length_header = str(self.content_length)
            self.response_headers.append(
                ('Content-Length',content_length_header)
                )

        def close_on_finish():
            if connection_header != 'close':
                response_headers.append(('Connection', 'close'))
            self.close_on_finish = True

        if version == '1.0':
            if connection == 'keep-alive':
                if not content_length_header:
                    close_on_finish()
                elif not connection_header:
                    response_headers.append(('Connection', 'Keep-Alive'))
            else:
                close_on_finish()
        elif version == '1.1':
            if connection_header == 'close':
                self.close_on_finish = True # shortcut doesnt call closure
            elif connection == 'close':
                close_on_finish()
            elif transfer_encoding_header:
                if transfer_encoding_header != 'chunked':
                    close_on_finish()
            elif self.status[:3] == '304':
                # Replying with headers only.
                pass
            elif not content_length_header:
                close_on_finish()
            # under HTTP 1.1 keep-alive is default, no need to set the header
        else:
            # Close if unrecognized HTTP version.
            close_on_finish()

        # Set the Server and Date field, if not yet specified. This is needed
        # if the server is used as a proxy.
        ident = self.channel.server.SERVER_IDENT
        if not server_header:
            response_headers.append(('Server', ident))
        else:
            response_headers.append(('Via', ident))
        if not date_header:
            response_headers.append(('Date', build_http_date(self.start_time)))

        first_line = 'HTTP/%s %s' % (self.version, self.status)
        next_lines = ['%s: %s' % hv for hv in sorted(self.response_headers)]
        lines = [first_line] + next_lines
        res = '%s\r\n\r\n' % '\r\n'.join(lines)
        return tobytes(res)

    def get_environment(self):
        """Returns a WSGI environment."""
        environ = self.environ
        if environ is not None:
            # Return the cached copy.
            return environ

        request_data = self.request_data
        path = request_data.path
        channel = self.channel
        server = channel.server

        while path and path.startswith('/'):
            path = path[1:]

        environ = {}
        environ['REQUEST_METHOD'] = request_data.command.upper()
        environ['SERVER_PORT'] = str(server.port)
        environ['SERVER_NAME'] = server.server_name
        environ['SERVER_SOFTWARE'] = server.SERVER_IDENT
        environ['SERVER_PROTOCOL'] = "HTTP/%s" % self.version
        environ['SCRIPT_NAME'] = ''
        environ['PATH_INFO'] = '/' + path
        query = request_data.query
        if query:
            environ['QUERY_STRING'] = query
        environ['REMOTE_ADDR'] = channel.addr[0]

        for key, value in request_data.headers.items():
            value = value.strip()
            mykey = rename_headers.get(key, None)
            if mykey is None:
                mykey = 'HTTP_%s' % key
            if not mykey in environ:
                environ[mykey] = value

        # the following environment variables are required by the WSGI spec
        environ['wsgi.version'] = (1,0)
        environ['wsgi.url_scheme'] = request_data.url_scheme
        environ['wsgi.errors'] = sys.stderr # apps should use the logging module
        environ['wsgi.multithread'] = True    # XXX base on dispatcher
        environ['wsgi.multiprocess'] = False  # XXX base on dispatcher
        environ['wsgi.run_once'] = False
        environ['wsgi.input'] = request_data.getBodyStream()

        self.environ = environ
        return environ

    def start(self):
        self.start_time = time.time()

    def finish(self):
        if not self.wrote_header:
            self.write(b'')

def fake_write(body):
    raise NotImplementedError(
        "the waitress HTTP Server does not support the WSGI write() function.")

