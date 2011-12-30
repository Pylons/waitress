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
"""Dual-mode channel
"""
import asyncore
import socket
import sys
import time
import traceback

from waitress.compat import thread
from waitress.buffers import OverflowableBuffer
from waitress.parser import HTTPRequestParser

from waitress.task import (
    ErrorTask,
    WSGITask,
    )

from waitress.utilities import (
    logging_dispatcher,
    InternalServerError,
    )

class HTTPChannel(logging_dispatcher, object):
    """Channel that switches between asynchronous and synchronous mode.

    Set self.task = sometask before using a channel in a thread other than
    the thread handling the main loop.

    Set self.task = None to give the channel back to the thread handling
    the main loop.
    """
    task_class = WSGITask
    error_task_class = ErrorTask
    parser_class = HTTPRequestParser

    task_lock = thread.allocate_lock() # syncs access to task-related attrs

    request = None              # A request parser instance
    last_activity = 0           # Time of last activity
    will_close = False          # will_close is set to True to close the socket.
    task = None                 # currently running task

    #
    # ASYNCHRONOUS METHODS (including __init__)
    #

    def __init__(
            self,
            server,
            sock,
            addr,
            adj,
            map=None,
            ):
        self.server = server
        self.addr = addr
        self.adj = adj
        self.outbuf = OverflowableBuffer(adj.outbuf_overflow)
        self.inbuf = OverflowableBuffer(adj.inbuf_overflow)
        self.creation_time = self.last_activity = time.time()
        asyncore.dispatcher.__init__(self, sock, map=map)

    def writable(self):
        if self.task is not None:
            return False
        return self.will_close or self.outbuf

    def handle_write(self):
        if self.task is not None:
            return
        if self.outbuf:
            try:
                self._flush_some()
            except socket.error:
                self.handle_comm_error()
        elif self.will_close:
            self.handle_close()
        self.last_activity = time.time()

    def readable(self):
        if self.task is not None or self.will_close:
            return False
        if self.inbuf:
            self.received()
        return not self.will_close

    def handle_read(self):
        try:
            data = self.recv(self.adj.recv_bytes)
        except socket.error:
            self.handle_comm_error()
            return
        self.last_activity = time.time()
        if data:
            self.inbuf.append(data)

    def add_channel(self, map=None):
        """See asyncore.dispatcher

        This hook keeps track of opened channels.
        """
        asyncore.dispatcher.add_channel(self, map)
        self.server.active_channels[self._fileno] = self

    def del_channel(self, map=None):
        """See asyncore.dispatcher

        This hook keeps track of closed channels.
        """
        fd = self._fileno # next line sets this to None
        asyncore.dispatcher.del_channel(self, map)
        ac = self.server.active_channels
        if fd in ac:
            del ac[fd]

    def received(self):
        """
        Receives input asynchronously and assigns a task to the channel.
        """
        if self.task is not None:
            return False
        chunk = self.inbuf.get(self.adj.recv_bytes)
        if not chunk:
            return
        if self.request is None:
            self.request = self.parser_class(self.adj)
        request = self.request
        n = request.received(chunk)
        if n:
            self.inbuf.skip(n, True)
        if request.expect_continue and request.headers_finished:
            # guaranteed by parser to be a 1.1 request
            self.write(b'HTTP/1.1 100 Continue\r\n\r\n')
            request.expect_continue = False
        if request.completed:
            # The request (with the body) is ready to use.
            if request.connection_close and self.inbuf:
                self.inbuf = OverflowableBuffer(self.adj.inbuf_overflow)
            self.request = None
            if not request.empty:
                if request.error:
                    self.inbuf = OverflowableBuffer(self.adj.inbuf_overflow)
                    task = self.error_task_class(self, request)
                else:
                    task = self.task_class(self, request)
                self.task = task
                self.server.add_task(self)
                return
        if self.inbuf:
            self.server.pull_trigger()

    def handle_error(self, exc_info=None): # exc_info for tests
        """See async.dispatcher

        Handles program errors (not communication errors)
        """
        if exc_info is None: # pragma: no cover
            t, v = sys.exc_info()[:2]
        else:
            t, v = exc_info[:2]
        if t is SystemExit or t is KeyboardInterrupt:
            raise t(v)
        asyncore.dispatcher.handle_error(self)

    def handle_comm_error(self):
        """
        Handles communication errors (not program errors)
        """
        if self.adj.log_socket_errors:
            # handle_error calls close
            self.handle_error()
        else:
            # Ignore socket errors.
            self.handle_close()

    def handle_close(self):
        # Always close in asynchronous mode.  If the connection is
        # closed in a thread, the main loop can end up with a bad file
        # descriptor.
        assert self.task is None
        self.connected = False
        asyncore.dispatcher.close(self)

    #
    # METHODS USED IN BOTH MODES
    #

    def write(self, data):
        wrote = 0
        if data:
            self.outbuf.append(data)
            wrote = len(data)

        while len(self.outbuf) >= self.adj.send_bytes:
            # Send what we can without blocking.
            # We propagate errors to the application on purpose
            # (to stop the application if the connection closes).
            if not self._flush_some(): # pragma: no cover (coverage bug?)
                break

        return wrote

    def _flush_some(self):
        """Flushes data.

        Returns True if some data was sent."""
        outbuf = self.outbuf
        if outbuf and self.connected:
            chunk = outbuf.get(self.adj.send_bytes)
            num_sent = self.send(chunk)
            if num_sent:
                outbuf.skip(num_sent, True)
                return True
        return False

    #
    # ITask implementation.  Delegates to the queued tasks.
    #

    def service(self):
        """Execute a pending task"""
        if self.task is None:
            return
        task = self.task
        try:
            task.service()
        except:
            self.logger.exception('Exception when serving %s' %
                                  task.request.uri)
            if not task.wrote_header:
                if self.adj.expose_tracebacks:
                    body = traceback.format_exc()
                else:
                    body = 'Internal server error'
                request = self.parser_class(self.adj)
                request.error = InternalServerError(body)
                task = self.error_task_class(self, request)
                task.service() # must not fail
            else:
                task.close_on_finish = True
        while self._flush_some():
            pass
        self.task = None
        if task.close_on_finish:
            self.will_close = True
        self.server.pull_trigger()
        self.last_activity = time.time()

    def cancel(self):
        """Cancels all pending tasks"""
        if self.task is not None:
            self.task.cancel()
            self.task = None

    def defer(self):
        pass
