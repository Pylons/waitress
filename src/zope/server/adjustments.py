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

from zope.server import maxsockets


class Adjustments(object):
    """This class contains tunable communication parameters.

    You can either change default_adj to adjust parameters for
    all sockets, or you can create a new instance of this class,
    change its attributes, and pass it to the channel constructors.
    """

    # backlog is the argument to pass to socket.listen().
    backlog = 1024

    # recv_bytes is the argument to pass to socket.recv().
    recv_bytes = 8192

    # send_bytes is the number of bytes to send to socket.send().
    # Multiples of 9000 should avoid partly-filled packets, but don't
    # set this larger than the TCP write buffer size.  In Linux,
    # /proc/sys/net/ipv4/tcp_wmem controls the minimum, default, and
    # maximum sizes of TCP write buffers.
    send_bytes = 9000

    # copy_bytes is the number of bytes to copy from one file to another.
    copy_bytes = 65536

    # Create a tempfile if the pending output data gets larger
    # than outbuf_overflow.  With RAM so cheap, this probably
    # ought to be set to the 16-32 MB range (circa 2001) for
    # good performance with big transfers.  The default is
    # conservative.
    outbuf_overflow = 1050000

    # Create a tempfile if the data received gets larger
    # than inbuf_overflow.
    inbuf_overflow = 525000

    # Stop accepting new connections if too many are already active.
    connection_limit = maxsockets.max_select_sockets() - 3  # Safe

    # Minimum seconds between cleaning up inactive channels.
    cleanup_interval = 300

    # Maximum seconds to leave an inactive connection open.
    channel_timeout = 900

    # Boolean: turn off to not log premature client disconnects.
    log_socket_errors = 1

    # The socket options to set on receiving a connection.
    # It is a list of (level, optname, value) tuples.
    # TCP_NODELAY is probably good for Zope, since Zope buffers
    # data itself.
    socket_options = [
        (socket.SOL_TCP, socket.TCP_NODELAY, 1),
        ]


default_adj = Adjustments()
