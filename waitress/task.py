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

from waitress.compat import (
    tobytes,
    Queue,
    Empty,
    thread,
    reraise,
    )

from waitress.utilities import (
    build_http_date,
    logger,
    )

rename_headers = {
    'CONTENT_LENGTH' : 'CONTENT_LENGTH',
    'CONTENT_TYPE'   : 'CONTENT_TYPE',
    'CONNECTION'     : 'CONNECTION_TYPE',
    }

hop_by_hop = frozenset((
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade'
    ))

class JustTesting(Exception):
    pass

class ThreadedTaskDispatcher(object):
    """A Task Dispatcher that creates a thread for each task.
    """

    stop_count = 0  # Number of threads that will stop soon.
    start_new_thread = thread.start_new_thread
    logger = logger

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
                    self.logger.exception(
                        'Exception when servicing %r' % task)
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
        try:
            task.defer()
            self.queue.put(task)
        except:
            task.cancel()
            raise

    def shutdown(self, cancel_pending=True, timeout=5):
        self.set_thread_count(0)
        # Ensure the threads shut down.
        threads = self.threads
        expiration = time.time() + timeout
        while threads:
            if time.time() >= expiration:
                self.logger.warning("%d thread(s) still running" % len(threads))
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

class Task(object):
    close_on_finish = False
    status = '200 OK'
    wrote_header = False
    start_time = 0
    content_length = -1
    content_bytes_written = 0
    logged_write_excess = False
    complete = False
    chunked_response = False
    logger = logger

    def __init__(self, channel, request):
        self.channel = channel
        self.request = request
        self.response_headers = []
        version = request.version
        if version not in ('1.0', '1.1'):
            # fall back to a version we support.
            version = '1.0'
        self.version = version

    def service(self):
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
            pass

    def cancel(self):
        self.close_on_finish = True

    def defer(self):
        pass

    def build_response_header(self):
        version = self.version
        # Figure out whether the connection should be closed.
        connection = self.request.headers.get('CONNECTION', '').lower()
        response_headers = self.response_headers
        content_length_header = None
        date_header = None
        server_header = None
        connection_close_header = None

        for i, (headername, headerval) in enumerate(response_headers):
            headername = '-'.join(
                [x.capitalize() for x in headername.split('-')]
                )
            if headername == 'Content-Length':
                content_length_header = headerval
            if headername == 'Date':
                date_header = headerval
            if headername == 'Server':
                server_header = headerval
            if headername == 'Connection':
                connection_close_header = headerval.lower()
            # replace with properly capitalized version
            response_headers[i] = (headername, headerval)

        if content_length_header is None and self.content_length != -1:
            content_length_header = str(self.content_length)
            self.response_headers.append(
                ('Content-Length', content_length_header)
                )

        def close_on_finish():
            if connection_close_header is None:
                response_headers.append(('Connection', 'close'))
            self.close_on_finish = True

        if version == '1.0':
            if connection == 'keep-alive':
                if not content_length_header:
                    close_on_finish()
                else:
                    response_headers.append(('Connection', 'Keep-Alive'))
            else:
                close_on_finish()

        elif version == '1.1':
            if connection == 'close':
                close_on_finish()

            if not content_length_header:
                response_headers.append(('Transfer-Encoding', 'chunked'))
                self.chunked_response = True
                if not self.close_on_finish:
                    close_on_finish()

            # under HTTP 1.1 keep-alive is default, no need to set the header
        else:
            raise AssertionError('neither HTTP/1.0 or HTTP/1.1')

        # Set the Server and Date field, if not yet specified. This is needed
        # if the server is used as a proxy.
        ident = self.channel.server.adj.ident
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

    def start(self):
        self.start_time = time.time()

    def finish(self):
        if not self.wrote_header:
            self.write(b'')
        if self.chunked_response:
            # not self.write, it will chunk it!
            self.channel.write_soon(b'0\r\n\r\n')

    def write(self, data):
        if not self.complete:
            raise RuntimeError('start_response was not called before body '
                               'written')
        channel = self.channel
        if not self.wrote_header:
            rh = self.build_response_header()
            channel.write_soon(rh)
            self.wrote_header = True
        if data:
            towrite = data
            cl = self.content_length
            if self.chunked_response:
                # use chunked encoding response
                towrite = tobytes(hex(len(data))[2:].upper()) + b'\r\n'
                towrite += data + b'\r\n'
            elif cl != -1:
                towrite = data[:cl-self.content_bytes_written]
                self.content_bytes_written += len(towrite)
                if towrite != data and not self.logged_write_excess:
                    self.logger.warning(
                        'application-written content exceeded the number of '
                        'bytes specified by Content-Length header (%s)' % cl)
                    self.logged_write_excess = True
            if towrite:
                self.channel.write_soon(towrite)

class ErrorTask(Task):
    """ An error task produces an error response """
    complete = True
    def execute(self):
        e = self.request.error
        body = '%s\r\n\r\n%s' % (e.reason, e.body)
        tag = '\r\n\r\n(generated by waitress)'
        body = body + tag
        self.status = '%s %s' % (e.code, e.reason)
        cl = len(body)
        self.content_length = cl
        self.response_headers.append(('Content-Length', str(cl)))
        self.response_headers.append(('Content-Type', 'text/plain'))
        self.response_headers.append(('Connection', 'close'))
        self.close_on_finish = True
        self.write(tobytes(body))

class WSGITask(Task):
    """A WSGI task accepts a request and writes to a channel.

    """

    environ = None

    def execute(self):
        env = self.get_environment()

        def start_response(status, headers, exc_info=None):
            if self.complete and not exc_info:
                raise AssertionError("start_response called a second time "
                                     "without providing exc_info.")
            if exc_info:
                try:
                    if self.complete:
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

            self.complete = True

            if not status.__class__ is str:
                raise AssertionError('status %s is not a string' % status)

            self.status = status

            # Prepare the headers for output
            for k, v in headers:
                if not k.__class__ is str:
                    raise AssertionError(
                        'Header name %r is not a string in %r' % (k, (k, v))
                        )
                if not v.__class__ is str:
                    raise AssertionError(
                        'Header value %r is not a string in %r' % (v, (k, v))
                        )
                kl = k.lower()
                if kl == 'content-length':
                    self.content_length = int(v)
                elif kl in hop_by_hop:
                    raise AssertionError(
                        '%s is a "hop-by-hop" header; it cannot be used by '
                        'a WSGI application (see PEP 3333)' % k)

            self.response_headers.extend(headers)

            # Return a method used to write the response data.
            return self.write

        # Call the application to handle the request and write a response
        app_iter = self.channel.server.application(env, start_response)

        try:
            # By iterating manually at this point, we execute task.write()
            # multiple times, allowing partial data to be sent.
            first_chunk_len = None
            for chunk in app_iter:
                if first_chunk_len is None:
                    first_chunk_len = len(chunk)
                    # Set a Content-Length header if one is not supplied.
                    # start_response may not have been called until first
                    # iteration as per PEP, so we must reinterrogate
                    # self.content_length here
                    if self.content_length == -1:
                        app_iter_len = None
                        if hasattr(app_iter, '__len__'):
                            app_iter_len = len(app_iter)
                        if app_iter_len == 1:
                            self.content_length = first_chunk_len
                # transmit headers only after first iteration of the iterable
                # that returns a non-empty bytestring (PEP 3333)
                if chunk:
                    self.write(chunk)

            cl = self.content_length
            if cl != -1:
                if self.content_bytes_written != cl:
                    # close the connection so the client isn't sitting around
                    # waiting for more data when there are too few bytes
                    # to service content-length
                    self.close_on_finish = True
                    self.logger.warning(
                        'appplication returned too few bytes (%s) '
                        'for specified Content-Length (%s) via app_iter' % (
                            self.content_bytes_written, cl),
                        )
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()

    def get_environment(self):
        """Returns a WSGI environment."""
        environ = self.environ
        if environ is not None:
            # Return the cached copy.
            return environ

        request = self.request
        path = request.path
        channel = self.channel
        server = channel.server

        while path and path.startswith('/'):
            path = path[1:]

        environ = {}
        environ['REQUEST_METHOD'] = request.command.upper()
        environ['SERVER_PORT'] = str(server.effective_port)
        environ['SERVER_NAME'] = server.server_name
        environ['SERVER_SOFTWARE'] = server.adj.ident
        environ['SERVER_PROTOCOL'] = 'HTTP/%s' % self.version
        environ['SCRIPT_NAME'] = ''
        environ['PATH_INFO'] = '/' + path
        environ['QUERY_STRING'] = request.query
        environ['REMOTE_ADDR'] = channel.addr[0]

        for key, value in request.headers.items():
            value = value.strip()
            mykey = rename_headers.get(key, None)
            if mykey is None:
                mykey = 'HTTP_%s' % key
            if not mykey in environ:
                environ[mykey] = value

        # the following environment variables are required by the WSGI spec
        environ['wsgi.version'] = (1,0)
        environ['wsgi.url_scheme'] = request.url_scheme
        environ['wsgi.errors'] = sys.stderr # apps should use the logging module
        environ['wsgi.multithread'] = True
        environ['wsgi.multiprocess'] = False
        environ['wsgi.run_once'] = False
        environ['wsgi.input'] = request.get_body_stream()

        self.environ = environ
        return environ
