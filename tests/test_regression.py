##############################################################################
#
# Copyright (c) 2005 Zope Foundation and Contributors.
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
"""Tests for waitress.channel maintenance logic

Regression test for HTTPChannel.maintenance: channels that have been
"inactive" for a configured time get closed. The bug was that
last_activity is set at creation time but never updated during async
channel activity (reads and writes), so any channel older than the
configured timeout would be marked for closing when maintenance ran,
regardless of activity.

This used to be a single doctest (see git history), written against a
Python 2-only API (tuple-unpacking ``bind`` parameters, print
statements) that could not run under Python 3 at all, and that pytest
additionally warned about collecting via its ``test_suite()`` wrapper
(see GH #481). It is rewritten below as ordinary pytest functions
against the current API.
"""

import socket
import time

from waitress.server import create_server

dummy_app = object()


class FakeListenSocket(socket.socket):
    """Stand-in for the listening socket create_server() binds to. Only
    used because _start=False and _sock is supplied still exercises the
    normal socket setup path (set_reuse_addr, etc.) -- nothing here is
    ever actually connected to."""

    family = socket.AF_INET
    type = socket.SOCK_STREAM
    proto = 0

    def __init__(self):
        self.bound = None
        self.opts = []

    def bind(self, addr):
        self.bound = addr

    def listen(self, num):
        self.listened = num

    def getsockname(self):
        return self.bound

    def setsockopt(self, *arg):
        self.opts.append(arg)

    def getsockopt(self, *arg):
        return 1

    def setblocking(self, *_):
        pass

    def fileno(self):
        return 10

    def getpeername(self):
        return "127.0.0.1"

    def close(self):
        pass


class FakeSocket:  # pragma: no cover
    """Minimal socket stand-in, just enough to construct a real
    HTTPChannel and drive it through handle_read()/handle_write()."""

    def __init__(self, no):
        self.no = no
        self.to_recv = b""
        self.sent = b""

    def fileno(self):
        return self.no

    def getpeername(self):
        return ("localhost", self.no)

    def getsockopt(self, level, optname):
        return 2048

    def setblocking(self, *_):
        pass

    def close(self):
        pass

    def send(self, data):
        self.sent += data
        return len(data)

    def recv(self, buffer_size):
        result = self.to_recv[:buffer_size]
        self.to_recv = self.to_recv[buffer_size:]
        return result


class DummyTaskDispatcher:
    def __init__(self):
        self.tasks = []

    def add_task(self, task):
        self.tasks.append(task)

    def shutdown(self):
        self.was_shutdown = True


def _make_server(map, channel_timeout=120, cleanup_interval=30):
    """A real TcpWSGIServer, not started, backed by a FakeSocket so no
    actual socket is bound."""
    return create_server(
        dummy_app,
        host="127.0.0.1",
        port=0,
        map=map,
        _sock=FakeListenSocket(),
        _dispatcher=DummyTaskDispatcher(),
        _start=False,
        channel_timeout=channel_timeout,
        cleanup_interval=cleanup_interval,
    )


def _make_channel(server, no, map):
    from waitress.channel import HTTPChannel

    sock = FakeSocket(no)
    channel = HTTPChannel(server, sock, ("localhost", no), adj=server.adj, map=map)
    server.active_channels[no] = channel

    return channel, sock


def test_maintenance_closes_inactive_channel():
    """A channel with no activity for the timeout duration gets marked
    for closing by maintenance."""
    map = {}
    server = _make_server(map, channel_timeout=1)
    channel, _ = _make_channel(server, 42, map)

    assert channel.will_close is False

    channel.last_activity -= server.adj.channel_timeout + 1
    server.maintenance(time.time())

    assert channel.will_close is True


def test_maintenance_write_activity_prevents_close():
    """A channel that has had write activity since it went "idle" must
    not be marked for closing, even though it's older than the
    timeout."""
    map = {}
    server = _make_server(map, channel_timeout=1)
    channel, sock = _make_channel(server, 7, map)

    channel.last_activity -= server.adj.channel_timeout + 1

    # Give it something to flush, then flush it -- this is what bumps
    # last_activity on the write path.
    channel.total_outbufs_len = 1
    channel.outbufs[0].append(b"data")
    channel.handle_write()

    server.maintenance(time.time())

    assert channel.will_close is False


def test_maintenance_read_activity_prevents_close():
    """A channel that has had read activity since it went "idle" must
    not be marked for closing, even though it's older than the
    timeout."""
    map = {}
    server = _make_server(map, channel_timeout=1)
    channel, sock = _make_channel(server, 3, map)

    channel.last_activity -= server.adj.channel_timeout + 1

    # A single byte of inbound data is enough to bump last_activity via
    # handle_read(), without needing a complete HTTP request.
    sock.to_recv = b"G"
    channel.handle_read()

    server.maintenance(time.time())

    assert channel.will_close is False


def test_maintenance_leaves_channel_with_pending_requests_alone():
    """A channel currently servicing a request must never be marked
    for closing by maintenance, regardless of last_activity -- matching
    the "main loop window" case from the original regression: activity
    can still be in flight even if the timestamp itself is stale."""
    map = {}
    server = _make_server(map, channel_timeout=1)
    channel, _ = _make_channel(server, 4, map)

    channel.last_activity -= server.adj.channel_timeout + 1
    channel.requests = [object()]

    server.maintenance(time.time())

    assert channel.will_close is False
