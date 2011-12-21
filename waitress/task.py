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

import logging
from Queue import Queue, Empty
from thread import allocate_lock, start_new_thread
import socket
import time

from zope.interface import implements

from waitress.interfaces import ITaskDispatcher
from waitress.utilities import build_http_date
from waitress.interfaces import ITask, IHeaderOutput

rename_headers = {
    'CONTENT_LENGTH' : 'CONTENT_LENGTH',
    'CONTENT_TYPE'   : 'CONTENT_TYPE',
    'CONNECTION'     : 'CONNECTION_TYPE',
    }

log = logging.getLogger(__name__)

class ThreadedTaskDispatcher(object):
    """A Task Dispatcher that creates a thread for each task."""

    implements(ITaskDispatcher)

    stop_count = 0  # Number of threads that will stop soon.

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
                except:
                    log.exception('Exception during task')
        finally:
            mlock = self.thread_mgmt_lock
            mlock.acquire()
            try:
                self.stop_count -= 1
                try: del threads[thread_no]
                except KeyError: pass
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
                start_new_thread(self.handlerThread, (thread_no,))
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
        if task is None:
            raise ValueError("No task passed to addTask().")
        # assert ITask.providedBy(task)
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
                log.error("%d thread(s) still running" % len(threads))
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
            except Empty:
                pass

    def getPendingTasksEstimate(self):
        """See waitress.interfaces.ITaskDispatcher"""
        return self.queue.qsize()

class HTTPTask(object):
    """An HTTP task accepts a request and writes to a channel.

       Subclass this and override the execute() method.
    """

    implements(ITask, IHeaderOutput)

    instream = None
    close_on_finish = 1
    status = '200'
    reason = 'OK'
    wrote_header = 0
    accumulated_headers = None
    bytes_written = 0
    auth_user_name = ''
    cgi_env = None

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
                self.close_on_finish = 1
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

    def setResponseHeaders(self, mapping):
        """See waitress.interfaces.http.IHeaderOutput"""
        self.response_headers.update(mapping)

    def appendResponseHeaders(self, lst):
        """See waitress.interfaces.http.IHeaderOutput"""
        accum = self.accumulated_headers
        if accum is None:
            self.accumulated_headers = accum = []
        accum.extend(lst)

    def wroteResponseHeader(self):
        """See waitress.interfaces.http.IHeaderOutput"""
        return self.wrote_header

    def setAuthUserName(self, name):
        """See waitress.interfaces.http.IHeaderOutput"""
        self.auth_user_name = name

    def prepareResponseHeaders(self):
        version = self.version
        # Figure out whether the connection should be closed.
        connection = self.request_data.headers.get('CONNECTION', '').lower()
        close_it = 0
        response_headers = self.response_headers
        accumulated_headers = self.accumulated_headers
        if accumulated_headers is None:
            accumulated_headers = []

        if version == '1.0':
            if connection == 'keep-alive':
                if not ('Content-Length' in response_headers):
                    close_it = 1
                else:
                    response_headers['Connection'] = 'Keep-Alive'
            else:
                close_it = 1
        elif version == '1.1':
            if 'connection: close' in (header.lower() for header in
                accumulated_headers):
                close_it = 1
            if connection == 'close':
                close_it = 1
            elif 'Transfer-Encoding' in response_headers:
                if not response_headers['Transfer-Encoding'] == 'chunked':
                    close_it = 1
            elif self.status == '304':
                # Replying with headers only.
                pass
            elif not ('Content-Length' in response_headers):
                # accumulated_headers is a simple list, we need to cut off
                # the value of content-length manually
                if 'content-length' not in (header[:14].lower() for header in
                    accumulated_headers):
                    close_it = 1
            # under HTTP 1.1 keep-alive is default, no need to set the header
        else:
            # Close if unrecognized HTTP version.
            close_it = 1

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


    def buildResponseHeader(self):
        self.prepareResponseHeaders()
        first_line = 'HTTP/%s %s %s' % (self.version, self.status, self.reason)
        lines = [first_line] + ['%s: %s' % hv
                                for hv in self.response_headers.items()]
        accum = self.accumulated_headers
        if accum is not None:
            lines.extend(accum)
        res = '%s\r\n\r\n' % '\r\n'.join(lines)
        return res

    def getCGIEnvironment(self):
        """Returns a CGI-like environment."""
        env = self.cgi_env
        if env is not None:
            # Return the cached copy.
            return env

        request_data = self.request_data
        path = request_data.path
        channel = self.channel
        server = channel.server

        while path and path.startswith('/'):
            path = path[1:]

        env = {}
        env['REQUEST_METHOD'] = request_data.command.upper()
        env['SERVER_PORT'] = str(server.port)
        env['SERVER_NAME'] = server.server_name
        env['SERVER_SOFTWARE'] = server.SERVER_IDENT
        env['SERVER_PROTOCOL'] = "HTTP/%s" % self.version
        env['CHANNEL_CREATION_TIME'] = channel.creation_time
        env['SCRIPT_NAME']=''
        env['PATH_INFO']='/' + path
        query = request_data.query
        if query:
            env['QUERY_STRING'] = query
        env['GATEWAY_INTERFACE'] = 'CGI/1.1'
        addr = channel.addr[0]
        env['REMOTE_ADDR'] = addr

        # If the server has a resolver, try to get the
        # remote host from the resolver's cache.
        resolver = getattr(server, 'resolver', None)
        if resolver is not None:
            dns_cache = resolver.cache
            if addr in dns_cache:
                remote_host = dns_cache[addr][2]
                if remote_host is not None:
                    env['REMOTE_HOST'] = remote_host

        env_has = env.has_key

        for key, value in request_data.headers.items():
            value = value.strip()
            mykey = rename_headers.get(key, None)
            if mykey is None:
                mykey = 'HTTP_%s' % key
            if not env_has(mykey):
                env[mykey] = value

        self.cgi_env = env
        return env

    def start(self):
        now = time.time()
        self.start_time = now

    def finish(self):
        if not self.wrote_header:
            self.write('')
        hit_log = self.channel.server.hit_log
        if hit_log is not None:
            hit_log.log(self)

    def write(self, data):
        channel = self.channel
        if not self.wrote_header:
            rh = self.buildResponseHeader()
            channel.write(rh)
            self.bytes_written += len(rh)
            self.wrote_header = 1
        if data:
            self.bytes_written += channel.write(data)

    def flush(self):
        self.channel.flush()
