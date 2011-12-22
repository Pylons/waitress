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

from Queue import (
    Queue,
    Empty,
    )
from thread import (
    allocate_lock,
    start_new_thread,
    )
import socket
import time
import sys
import traceback

from waitress.utilities import build_http_date

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
    start_new_thread = start_new_thread

    def __init__(self):
        self.threads = {}  # { thread number -> 1 }
        self.queue = Queue()
        self.thread_mgmt_lock = allocate_lock()

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
    close_on_finish = True
    status = '200'
    reason = 'OK'
    wrote_header = False
    accumulated_headers = None
    bytes_written = 0
    environ = None

    def __init__(self, channel, request_data):
        self.channel = channel
        self.request_data = request_data
        self.response_headers = {}
        version = request_data.version
        if version not in ('1.0', '1.1'):
            # fall back to a version we support.
            version = '1.0'
        self.version = version

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

    def appendResponseHeaders(self, lst):
        """See waitress.interfaces.http.IHeaderOutput"""
        accum = self.accumulated_headers
        if accum is None:
            self.accumulated_headers = accum = []
        accum.extend(lst)

    def buildResponseHeader(self):
        version = self.version
        # Figure out whether the connection should be closed.
        connection = self.request_data.headers.get('CONNECTION', '').lower()
        close_it = False
        response_headers = self.response_headers
        accumulated_headers = self.accumulated_headers
        if accumulated_headers is None:
            accumulated_headers = []

        if version == '1.0':
            if connection == 'keep-alive':
                if not ('Content-Length' in response_headers):
                    close_it = True
                else:
                    response_headers['Connection'] = 'Keep-Alive'
            else:
                close_it = True
        elif version == '1.1':
            if 'connection: close' in (header.lower() for header in
                accumulated_headers):
                close_it = True
            if connection == 'close':
                close_it = True
            elif 'Transfer-Encoding' in response_headers:
                if not response_headers['Transfer-Encoding'] == 'chunked':
                    close_it = True
            elif self.status == '304':
                # Replying with headers only.
                pass
            elif not ('Content-Length' in response_headers):
                # accumulated_headers is a simple list, we need to cut off
                # the value of content-length manually
                if 'content-length' not in (header[:14].lower() for header in
                    accumulated_headers):
                    close_it = True
            # under HTTP 1.1 keep-alive is default, no need to set the header
        else:
            # Close if unrecognized HTTP version.
            close_it = True

        self.close_on_finish = close_it
        if close_it:
            self.response_headers['Connection'] = 'close'

        # Set the Server and Date field, if not yet specified. This is needed
        # if the server is used as a proxy.
        if 'server' not in (header[:6].lower() for header in
                            accumulated_headers):
            self.response_headers['Server'] = self.channel.server.SERVER_IDENT
        else:
            self.response_headers['Via'] = self.channel.server.SERVER_IDENT
        if 'date' not in (header[:4].lower() for header in
                            accumulated_headers):
            self.response_headers['Date'] = build_http_date(self.start_time)


        first_line = 'HTTP/%s %s %s' % (self.version, self.status, self.reason)
        lines = [first_line] + ['%s: %s' % hv
                                for hv in self.response_headers.items()]
        accum = self.accumulated_headers
        if accum is not None:
            lines.extend(accum)
        res = '%s\r\n\r\n' % '\r\n'.join(lines)
        return res

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
        environ['CHANNEL_CREATION_TIME'] = channel.creation_time
        environ['SCRIPT_NAME']=''
        environ['PATH_INFO']='/' + path
        query = request_data.query
        if query:
            environ['QUERY_STRING'] = query
        environ['GATEWAY_INTERFACE'] = 'CGI/1.1'
        addr = channel.addr[0]
        environ['REMOTE_ADDR'] = addr

        # If the server has a resolver, try to get the
        # remote host from the resolver's cache.
        resolver = getattr(server, 'resolver', None)
        if resolver is not None:
            dns_cache = resolver.cache
            if addr in dns_cache:
                remote_host = dns_cache[addr][2]
                if remote_host is not None:
                    environ['REMOTE_HOST'] = remote_host

        for key, value in request_data.headers.items():
            value = value.strip()
            mykey = rename_headers.get(key, None)
            if mykey is None:
                mykey = 'HTTP_%s' % key
            if not mykey in environ:
                environ[mykey] = value

        # deduce the URL scheme (http or https)
        if (environ.get('HTTPS', '').lower() == "on" or
            environ.get('SERVER_PORT_SECURE') == "1"):
            protocol = 'https'
        else:
            protocol = 'http'

        # the following environment variables are required by the WSGI spec
        environ['wsgi.version'] = (1,0)
        environ['wsgi.url_scheme'] = protocol
        environ['wsgi.errors'] = sys.stderr # apps should use the logging module
        environ['wsgi.multithread'] = True
        environ['wsgi.multiprocess'] = True
        environ['wsgi.run_once'] = False
        environ['wsgi.input'] = self.request_data.getBodyStream()

        self.environ = environ
        return environ

    def start(self):
        now = time.time()
        self.start_time = now

    def finish(self):
        if not self.wrote_header:
            self.write('')

    def write(self, data):
        channel = self.channel
        if not self.wrote_header:
            rh = self.buildResponseHeader()
            channel.write(rh)
            self.bytes_written += len(rh)
            self.wrote_header = True
        if data:
            self.bytes_written += channel.write(data)

