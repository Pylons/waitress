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

class Adjustments(object):
    """This class contains tunable communication parameters.

    You can either change default_adj to adjust parameters for
    all sockets, or you can create a new instance of this class,
    change its attributes, and pass it to the channel constructors.
    """
    # wsgi url scheme
    url_scheme = 'http'

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
    connection_limit = 100

    # Minimum seconds between cleaning up inactive channels.
    cleanup_interval = 300

    # Maximum seconds to leave an inactive connection open.
    channel_timeout = 60

    # Boolean: turn off to not log premature client disconnects.
    log_socket_errors = True

    # The socket options to set on receiving a connection.  It is a list of
    # (level, optname, value) tuples.  TCP_NODELAY is probably good for Zope,
    # since Zope buffers data itself.
    socket_options = [
        (socket.SOL_TCP, socket.TCP_NODELAY, 1),
        ]

default_adj = Adjustments()
