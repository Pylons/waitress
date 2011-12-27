##############################################################################
#
# Copyright (c) 2002 Zope Foundation and Contributors.
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
"""Adjustments are tunable parameters.
"""
import socket
import sys

class Adjustments(object):
    """This class contains tunable communication parameters.

    You can either change default_adj to adjust parameters for
    all sockets, or you can create a new instance of this class,
    change its attributes, and pass it to the channel constructors.
    """
    # host
    host = '127.0.0.1'

    # port
    port = 8080

    # threads
    threads = 4

    # wsgi url scheme
    url_scheme = 'http'

    # verbose
    verbose = True

    # ident
    ident = 'waitress'

    # backlog is the argument to pass to socket.listen().
    backlog = 1024

    # recv_bytes is the argument to pass to socket.recv().
    recv_bytes = 8192

    # send_bytes is the number of bytes to send to socket.send().  Multiples
    # of 9000 should avoid partly-filled packets, but don't set this larger
    # than the TCP write buffer size.  In Linux, /proc/sys/net/ipv4/tcp_wmem
    # controls the minimum, default, and maximum sizes of TCP write buffers.
    send_bytes = 9000

    # A tempfile should be created if the pending output is larger than
    # outbuf_overflow, which is measured in bytes. The default is 1MB.  This
    # is conservative.
    outbuf_overflow = 1048576

    # A tempfile should be created if the pending input is larger than
    # inbuf_overflow, which is measured in bytes. The default is 512K.  This
    # is conservative.
    inbuf_overflow = 524288

    # Stop accepting new connections if too many are already active.
    connection_limit = 1000

    # Minimum seconds between cleaning up inactive channels.
    cleanup_interval = 300

    # Maximum seconds to leave an inactive connection open.
    channel_timeout = 900

    # Boolean: turn off to not log premature client disconnects.
    log_socket_errors = True

    # The socket options to set on receiving a connection.  It is a list of
    # (level, optname, value) tuples.  TCP_NODELAY is probably good for Zope,
    # since Zope buffers data itself.
    socket_options = [
        (socket.SOL_TCP, socket.TCP_NODELAY, 1),
        ]

    def __init__(self, **kw):
        for k, v in kw.items():
            if k == 'host':
                v = str(v)
            if k == 'port':
                v = int(v)
            if k == 'threads':
                v = int(v)
            if k == 'url_scheme':
                v = str(v)
            if k == 'backlog':
                v = int(v)
            if k == 'recv_bytes':
                v = int(v)
            if k == 'send_bytes':
                v = int(v)
            if k == 'outbuf_overflow':
                v = int(v)
            if k == 'inbuf_overflow':
                v = int(v)
            if k == 'connection_limit':
                v = int(v)
            if k == 'cleanup_interval':
                v = int(v)
            if k == 'channel_timeout':
                v = int(v)
            if k == 'log_socket_errors':
                v = asbool(v)
            if k == 'verbose':
                v = asbool(v)
            setattr(self, k, v)
        if (sys.platform[:3] == "win" and
            self.host == 'localhost' ): # pragma: no cover
            self.host= ''

truthy = frozenset(('t', 'true', 'y', 'yes', 'on', '1'))

def asbool(s):
    """ Return the boolean value ``True`` if the case-lowered value of string
    input ``s`` is any of ``t``, ``true``, ``y``, ``on``, or ``1``, otherwise
    return the boolean value ``False``.  If ``s`` is the value ``None``,
    return ``False``.  If ``s`` is already one of the boolean values ``True``
    or ``False``, return it."""
    if s is None:
        return False
    if isinstance(s, bool):
        return s
    s = str(s).strip()
    return s.lower() in truthy

