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

from waitress.utilities import build_http_date

from waitress.compat import (
    tostr,
    tobytes,
    Queue,
    Empty,
    thread,
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

    def handlerThread(self, thread_no):
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

    def setThreadCount(self, count):
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
                self.start_new_thread(self.handlerThread, (thread_no,))
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

    def addTask(self, task):
        """See waitress.interfaces.ITaskDispatcher"""
        try:
            task.defer()
            self.queue.put(task)
        except:
            task.cancel()
            raise

    def shutdown(self, cancel_pending=True, timeout=5):
        """See waitress.interfaces.ITaskDispatcher"""
        self.setThreadCount(0)
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

       Subclass this and override the execute() method.

       See ITask, IHeaderOutput.
    """

    instream = None
    close_on_finish = False
    status = '200'
    reason = 'OK'
    wrote_header = False
    accumulated_headers = None
    bytes_written = 0
    start_time = 0
    environ = None

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
                self.channel.server.executeRequest(self)
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

    def setResponseStatus(self, status, reason):
        """See waitress.interfaces.http.IHeaderOutput"""
        self.status = status
        self.reason = reason

    def appendResponseHeader(self, name, value):
        if not isinstance(name, str):
            raise ValueError(
                'Header name %r is not a string in %s' % (name, (name, value))
                )
        if not isinstance(value, str):
            raise ValueError(
                'Header value %r is not a string in %s' % (value, (name, value))
                )
        name = '-'.join([x.capitalize() for x in name.split('-')])
        self.response_headers.append((tostr(name), tostr(value)))

    def buildResponseHeader(self):
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
            elif self.status == '304':
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

        first_line = 'HTTP/%s %s %s' % (self.version, self.status, self.reason)
        next_lines = ['%s: %s' % hv for hv in sorted(self.response_headers)]
        lines = [first_line] + next_lines
        res = '%s\r\n\r\n' % '\r\n'.join(lines)
        return tobytes(res)

    def getEnvironment(self):
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

    def write(self, data):
        channel = self.channel
        if not self.wrote_header:
            rh = self.buildResponseHeader()
            channel.write(rh)
            self.bytes_written += len(rh)
            self.wrote_header = True
        if data:
            self.bytes_written += channel.write(data)

