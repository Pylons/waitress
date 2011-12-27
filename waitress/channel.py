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
from waitress.dispatcher import logging_dispatcher
from waitress.parser import HTTPRequestParser
from waitress.task import WSGITask

class HTTPChannel(logging_dispatcher, object):
    """Channel that switches between asynchronous and synchronous mode.

    Call set_sync() before using a channel in a thread other than
    the thread handling the main loop.

    Call set_async() to give the channel back to the thread handling
    the main loop.
    """
    task_class = WSGITask
    parser_class = HTTPRequestParser

    task_lock = thread.allocate_lock() # syncs access to task-related attrs

    proto_request = None        # A request parser instance
    last_activity = 0           # Time of last activity
    tasks = None                # List of channel-related tasks to execute
    running_tasks = False       # True when another thread is running tasks
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
        self.creation_time = self.last_activity = time.time()
        asyncore.dispatcher.__init__(self, sock, map=map)

    def handle_close(self):
        self.close()

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
            self.close()
        self.last_activity = time.time()

    def readable(self):
        if not self.async_mode:
            return False
        return not self.will_close

    def handle_read(self):
        if not self.async_mode or self.will_close:
            return
        try:
            data = self.recv(self.adj.recv_bytes)
        except socket.error:
            self.handle_comm_error()
            return
        self.last_activity = time.time()
        self.received(data)

    def set_sync(self):
        """Switches to synchronous mode.

        The main thread will stop calling received().
        """
        self.async_mode = False

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

    def received(self, data):
        """
        Receives input asynchronously and send requests to
        handle_request().
        """
        preq = self.proto_request
        while data:
            if preq is None:
                preq = self.parser_class(self.adj)
            n = preq.received(data)
            if preq.expect_continue and preq.headers_finished:
                # guaranteed by parser to be a 1.1 request
                self.write(b'HTTP/1.1 100 Continue\r\n\r\n')
                preq.expect_continue = False
            if preq.completed:
                # The request (with the body) is ready to use.
                self.proto_request = None
                if not preq.empty:
                    self.handle_request(preq)
                preq = None
            else:
                self.proto_request = preq
            if n >= len(data):
                break
            data = data[n:]

    def handle_request(self, req):
        """Creates and queues a task for processing a request.

        Subclasses may override this method to handle some requests
        immediately in the main async thread.
        """
        task = self.task_class(self, req)
        self.queue_task(task)

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
            self.close()

    def close(self):
        # Always close in asynchronous mode.  If the connection is
        # closed in a thread, the main loop can end up with a bad file
        # descriptor.
        assert self.async_mode
        self.connected = False
        asyncore.dispatcher.close(self)

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

        Returns 1 if some data was sent."""
        outbuf = self.outbuf
        if outbuf and self.connected:
            chunk = outbuf.get(self.adj.send_bytes)
            num_sent = self.send(chunk)
            if num_sent:
                outbuf.skip(num_sent, 1)
                return True
        return False

    def close_when_done(self):
        # Flush all possible.
        while self._flush_some():
            pass
        self.will_close = True
        if not self.async_mode:
            # For safety, don't close the socket until the
            # main thread calls handle_write().
            self.async_mode = True
            self.server.pull_trigger()

    def queue_task(self, task):
        """Queue a channel-related task to be executed in another thread."""
        start = False
        self.task_lock.acquire()
        try:
            if self.tasks is None:
                self.tasks = []
            self.tasks.append(task)
            if not self.running_tasks:
                self.running_tasks = True
                start = True
        finally:
            self.task_lock.release()
        if start:
            self.set_sync()
            self.server.add_task(self)

    #
    # ITask implementation.  Delegates to the queued tasks.
    #

    def service(self):
        """Execute all pending tasks"""
        while True:
            task = None
            self.task_lock.acquire()
            try:
                if self.tasks:
                    task = self.tasks.pop(0)
                else:
                    # No more tasks
                    self.running_tasks = False
                    self.set_async()
                    break
            finally:
                self.task_lock.release()
            try:
                task.service()
            except:
                # propagate the exception, but keep executing tasks
                self.server.add_task(self)
                raise

    def cancel(self):
        """Cancels all pending tasks"""
        self.task_lock.acquire()
        try:
            if self.tasks:
                old = self.tasks[:]
            else:
                old = []
            self.tasks = []
            self.running_tasks = False
        finally:
            self.task_lock.release()
        try:
            for task in old:
                task.cancel()
        finally:
            self.set_async()

    def defer(self):
        pass
