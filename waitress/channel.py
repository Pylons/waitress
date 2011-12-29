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

from waitress.compat import thread
from waitress.buffers import OverflowableBuffer
from waitress.parser import HTTPRequestParser

from waitress.task import (
    ErrorTask,
    WSGITask,
    )

from waitress.utilities import logging_dispatcher

class HTTPChannel(logging_dispatcher, object):
    """Channel that switches between asynchronous and synchronous mode.

    Set self.async_mode = False before using a channel in a thread other than
    the thread handling the main loop.

    Set self.async_mode = True to give the channel back to the thread handling
    the main loop.
    """
    task_class = WSGITask
    error_task_class = ErrorTask
    parser_class = HTTPRequestParser

    task_lock = thread.allocate_lock() # syncs access to task-related attrs

    proto_request = None        # A request parser instance
    last_activity = 0           # Time of last activity
    will_close = False          # will_close is set to True to close the socket.
    async_mode = True           # boolean: async or sync mode

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
        self.tasks = []
        asyncore.dispatcher.__init__(self, sock, map=map)

    def writable(self):
        if not self.async_mode:
            return False
        return self.will_close or self.outbuf

    def handle_write(self):
        if not self.async_mode:
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
        if not self.async_mode:
            return False
        if self.inbuf:
            self.received()
        return not self.will_close

    def handle_read(self):
        if not self.async_mode:
            return
        try:
            data = self.recv(self.adj.recv_bytes)
        except socket.error:
            self.handle_comm_error()
            return
        self.last_activity = time.time()
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
        Receives input asynchronously and send requests to
        handle_request().
        """
        if not self.async_mode:
            return False
        chunk = self.inbuf.get(self.adj.recv_bytes)
        if not chunk:
            return
        preq = self.proto_request
        if preq is None:
            preq = self.parser_class(self.adj)
        n = preq.received(chunk)
        if n:
            self.inbuf.skip(n, True)
        if preq.expect_continue and preq.headers_finished:
            # guaranteed by parser to be a 1.1 request
            self.write(b'HTTP/1.1 100 Continue\r\n\r\n')
            preq.expect_continue = False
        if preq.completed:
            # The request (with the body) is ready to use.
            self.proto_request = None
            if not preq.empty:
                if preq.error:
                    task = self.error_task_class(self, preq)
                else:
                    task = self.task_class(self, preq)
                with self.task_lock:
                    self.tasks.append(task)
            if preq.connection_close and self.inbuf:
                self.inbuf = OverflowableBuffer(self.adj.inbuf_overflow)
            preq = None
        else:
            self.proto_request = preq
        if self.inbuf:
            self.server.pull_trigger()
        else:
            # run those dogs
            self.server.add_task(self)

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

    #
    # SYNCHRONOUS METHODS
    #

    def set_async(self):
        """Switches to asynchronous mode.

        The main thread will begin calling received() again.
        """
        self.async_mode = True
        self.server.pull_trigger()
        self.last_activity = time.time()

    #
    # METHODS USED IN BOTH MODES
    #

    def handle_close(self):
        # Always close in asynchronous mode.  If the connection is
        # closed in a thread, the main loop can end up with a bad file
        # descriptor.
        assert self.async_mode
        self.connected = False
        asyncore.dispatcher.close(self)

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
        """Execute all pending tasks"""
        self.async_mode = False
        while True:
            with self.task_lock:
                if self.tasks:
                    task = self.tasks.pop(0)
                else:
                    break
            try:
                task.service()
                if task.close_on_finish:
                    self.will_close = True
            except:
                # allow error to propagate but readd ourselves to the
                # task queue
                if self.tasks:
                    self.server.add_task(self)
                raise
        while self._flush_some():
            pass
        self.set_async()

    def cancel(self):
        """Cancels all pending tasks"""
        with self.task_lock:
            if self.tasks:
                old = self.tasks[:]
            else:
                old = []
            self.tasks = []
        try:
            for task in old:
                task.cancel()
        finally:
            self.set_async()

    def defer(self):
        pass
