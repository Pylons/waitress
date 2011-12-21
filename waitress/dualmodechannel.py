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
from time import time

from waitress import trigger
from waitress.adjustments import default_adj
from waitress.buffers import OverflowableBuffer

class DualModeChannel(asyncore.dispatcher):
    """Channel that switches between asynchronous and synchronous mode.

    Call set_sync() before using a channel in a thread other than
    the thread handling the main loop.

    Call set_async() to give the channel back to the thread handling
    the main loop.
    """

    # will_close is set to True to close the socket.
    will_close = False

    # boolean: async or sync mode
    async_mode = True

    last_activity = None

    trigger = trigger.trigger()

    def __init__(self, sock, addr, adj=None, map=None):
        if map is None: # for testing
            map = asyncore.socket_map
        self.addr = addr
        if adj is None:
            adj = default_adj
        self.adj = adj
        self.outbuf = OverflowableBuffer(adj.outbuf_overflow)
        self.creation_time = time()
        asyncore.dispatcher.__init__(self, sock, map=map)

    #
    # ASYNCHRONOUS METHODS
    #

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
        self.last_activity = time()

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
        self.last_activity = time()
        self.received(data)

    def received(self, data):
        """
        Override to receive data in async mode.
        """
        pass

    def handle_comm_error(self):
        """
        Designed for handling communication errors that occur
        during asynchronous operations *only*.  Probably should log
        this, but in a different place.
        """
        self.handle_error()

    def set_sync(self):
        """Switches to synchronous mode.

        The main thread will stop calling received().
        """
        self.async_mode = False

    #
    # SYNCHRONOUS METHODS
    #

    def flush(self, block=True): # pragma: no cover (see comment in body)
        """Sends pending data.

        If block is set, this pauses the application.  If it is turned
        off, only the amount of data that can be sent without blocking
        is sent.
        """
        # XXX this looks smelly, but I think it's only actually used by
        # test_serverbase and httptask, and nothing at all appears to call
        # flush on httptask (CM); maybe delete it.
        if not block:
            while self._flush_some():
                pass
            return
        blocked = False
        try:
            # setting the blocking mode here?  wtf?  (CM)
            while self.outbuf:
                # We propagate errors to the application on purpose.
                if not blocked:
                    self.socket.setblocking(1)
                    blocked = True
                self._flush_some()
        finally:
            if blocked:
                self.socket.setblocking(0)

    def set_async(self):
        """Switches to asynchronous mode.

        The main thread will begin calling received() again.
        """
        self.async_mode = True
        self.pull_trigger()
        self.last_activity = time()

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
