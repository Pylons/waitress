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
import thread

from waitress import trigger
from waitress.adjustments import default_adj
from waitress.buffers import OverflowableBuffer
from waitress.parser import HTTPRequestParser
from waitress.task import HTTPTask

# task_lock is useful for synchronizing access to task-related attributes.
task_lock = thread.allocate_lock()

class HTTPServerChannel(asyncore.dispatcher, object):
    """Channel that switches between asynchronous and synchronous mode.

    Call set_sync() before using a channel in a thread other than
    the thread handling the main loop.

    Call set_async() to give the channel back to the thread handling
    the main loop.
    """

    task_class = HTTPTask
    parser_class = HTTPRequestParser

    trigger = trigger.trigger()

    active_channels = {}        # Class-specific channel tracker
    next_channel_cleanup = [0]  # Class-specific cleanup time
    proto_request = None        # A request parser instance
    last_activity = 0           # Time of last activity
    tasks = None                # List of channel-related tasks to execute
    running_tasks = False       # True when another thread is running tasks
    will_close = False          # will_close is set to True to close the socket.
    async_mode = True           # boolean: async or sync mode

    #
    # ASYNCHRONOUS METHODS (including __init__)
    #

    def __init__(self, server, sock, addr, adj=None, map=None):
        if map is None: # for testing
            map = asyncore.socket_map
        self.addr = addr
        if adj is None:
            adj = default_adj
        self.adj = adj
        self.outbuf = OverflowableBuffer(adj.outbuf_overflow)
        self.creation_time = time.time()
        asyncore.dispatcher.__init__(self, sock, map=map)
        self.server = server
        self.last_activity = t = self.creation_time
        self.check_maintenance(t)

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
        """See async.dispatcher

        This hook keeps track of opened channels.
        """
        asyncore.dispatcher.add_channel(self, map)
        self.__class__.active_channels[self._fileno] = self

    def del_channel(self, map=None):
        """See async.dispatcher

        This hook keeps track of closed channels.
        """
        asyncore.dispatcher.del_channel(self, map)
        ac = self.__class__.active_channels
        fd = self._fileno
        if fd in ac:
            del ac[fd]

    def check_maintenance(self, now):
        """See async.dispatcher

        Performs maintenance if necessary.
        """
        ncc = self.__class__.next_channel_cleanup
        if now < ncc[0]:
            return
        ncc[0] = now + self.adj.cleanup_interval
        self.maintenance()

    def maintenance(self):
        """See async.dispatcher

        Kills off dead connections.
        """
        self.kill_zombies()

    def kill_zombies(self):
        """See async.dispatcher

        Closes connections that have not had any activity in a while.

        The timeout is configured through adj.channel_timeout (seconds).
        """
        now = time.time()
        cutoff = now - self.adj.channel_timeout
        for channel in self.active_channels.values():
            if (channel is not self and not channel.running_tasks and
                channel.last_activity < cutoff):
                channel.close()

    def received(self, data):
        """See async.dispatcher

        Receives input asynchronously and send requests to
        handle_request().
        """
        preq = self.proto_request
        while data:
            if preq is None:
                preq = self.parser_class(self.adj)
            n = preq.received(data)
            if preq.completed:
                # The request is ready to use.
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

    def handle_error(self):
        """See async.dispatcher

        Handles program errors (not communication errors)
        """
        t, v = sys.exc_info()[:2]
        if t is SystemExit or t is KeyboardInterrupt:
            raise t(v)
        asyncore.dispatcher.handle_error(self)

    def handle_comm_error(self):
        """See async.dispatcher

        Handles communication errors (not program errors)
        """
        if self.adj.log_socket_errors:
            self.handle_error()
        else:
            # Ignore socket errors.
            self.close()


    #
    # SYNCHRONOUS METHODS
    #

    def set_async(self):
        """Switches to asynchronous mode.

        The main thread will begin calling received() again.
        """
        self.async_mode = True
        self.pull_trigger()
        self.last_activity = time.time()

    #
    # METHODS USED IN BOTH MODES
    #

    def write(self, data):
        wrote = 0
        if isinstance(data, bytes):
            if data:
                self.outbuf.append(data)
                wrote = len(data)
        else:
            for v in data:
                if v:
                    self.outbuf.append(v)
                    wrote += len(v)

        while len(self.outbuf) >= self.adj.send_bytes:
            # Send what we can without blocking.
            # We propagate errors to the application on purpose
            # (to stop the application if the connection closes).
            if not self._flush_some(): # pragma: no cover (coverage bug?)
                break

        return wrote

    def pull_trigger(self):
        """Wakes up the main loop.
        """
        self.trigger.pull_trigger()

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
            self.pull_trigger()

    def close(self):
        # Always close in asynchronous mode.  If the connection is
        # closed in a thread, the main loop can end up with a bad file
        # descriptor.
        assert self.async_mode
        self.connected = False
        asyncore.dispatcher.close(self)

    def queue_task(self, task):
        """Queue a channel-related task to be executed in another thread."""
        start = False
        task_lock.acquire()
        try:
            if self.tasks is None:
                self.tasks = []
            self.tasks.append(task)
            if not self.running_tasks:
                self.running_tasks = True
                start = True
        finally:
            task_lock.release()
        if start:
            self.set_sync()
            self.server.addTask(self)

    #
    # ITask implementation.  Delegates to the queued tasks.
    #

    def service(self):
        """Execute all pending tasks"""
        while True:
            task = None
            task_lock.acquire()
            try:
                if self.tasks:
                    task = self.tasks.pop(0)
                else:
                    # No more tasks
                    self.running_tasks = False
                    self.set_async()
                    break
            finally:
                task_lock.release()
            try:
                task.service()
            except:
                # propagate the exception, but keep executing tasks
                self.server.addTask(self)
                raise

    def cancel(self):
        """Cancels all pending tasks"""
        task_lock.acquire()
        try:
            if self.tasks:
                old = self.tasks[:]
            else:
                old = []
            self.tasks = []
            self.running_tasks = False
        finally:
            task_lock.release()
        try:
            for task in old:
                task.cancel()
        finally:
            self.set_async()

    def defer(self):
        pass

