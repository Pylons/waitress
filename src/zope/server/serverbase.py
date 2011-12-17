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
"""Server Base Class

This module provides a base implementation for a channel-based server. It can
only be used as a mix-in to actual server implementations.
"""
import asyncore
import logging
import socket

from zope.server.adjustments import default_adj
from zope.server.interfaces import IServer
from zope.interface import implements


class ServerBase(asyncore.dispatcher, object):
    """Async. server base for launching derivatives of ServerChannelBase."""

    implements(IServer)

    # See zope.server.interfaces.IServer
    channel_class = None    # Override with a channel class.
    SERVER_IDENT = 'zope.server.serverbase'  # Override.

    def __init__(self, ip, port, task_dispatcher=None, adj=None, start=1,
                 hit_log=None, verbose=0):
        if adj is None:
            adj = default_adj
        self.adj = adj
        asyncore.dispatcher.__init__(self)
        self.port = port
        self.task_dispatcher = task_dispatcher
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((ip, port))
        self.verbose = verbose
        self.hit_log = hit_log
        self.logger = logging.getLogger(self.__class__.__name__)
        self.server_name = self.computeServerName(ip)

        if start:
            self.accept_connections()

    def log(self, message):
        """See zope.server.interfaces.IDispatcherLogging"""
        # Override asyncore's default log()
        self.logger.info(message)

    level_mapping = {
        'info': logging.INFO,
        'error': logging.ERROR,
        'warning': logging.WARN,
        }

    def log_info(self, message, type='info'):
        """See zope.server.interfaces.IDispatcherLogging"""
        self.logger.log(self.level_mapping.get(type, logging.INFO), message)

    def computeServerName(self, ip=''):
        """Given an IP, try to determine the server name."""
        if ip:
            server_name = str(ip)
        else:
            server_name = str(socket.gethostname())
        # Convert to a host name if necessary.
        is_hostname = 0
        for c in server_name:
            if c != '.' and not c.isdigit():
                is_hostname = 1
                break
        if not is_hostname:
            if self.verbose:
                self.log_info('Computing hostname', 'info')
            try:
                server_name = socket.gethostbyaddr(server_name)[0]
            except socket.error:
                if self.verbose:
                    self.log_info('Cannot do reverse lookup', 'info')
        return server_name

    def accept_connections(self):
        self.accepting = 1
        self.socket.listen(self.adj.backlog)  # Circumvent asyncore's NT limit
        if self.verbose:
            self.log_info('%s started.\n'
                          '\tHostname: %s\n\tPort: %d' % (
                self.SERVER_IDENT,
                self.server_name,
                self.port
                ))


    def addTask(self, task):
        """See zope.server.interfaces.ITaskDispatcher"""
        td = self.task_dispatcher
        if td is not None:
            td.addTask(task)
        else:
            task.service()

    def readable(self):
        """See zope.server.interfaces.IDispatcher"""
        return (self.accepting and
                len(asyncore.socket_map) < self.adj.connection_limit)

    def writable(self):
        """See zope.server.interfaces.IDispatcher"""
        return 0

    def handle_read(self):
        """See zope.server.interfaces.IDispatcherEventHandler"""
        pass

    def handle_connect(self):
        """See zope.server.interfaces.IDispatcherEventHandler"""
        pass

    def handle_accept(self):
        """See zope.server.interfaces.IDispatcherEventHandler"""
        try:
            v = self.accept()
            if v is None:
                return
            conn, addr = v
        except socket.error:
            # Linux: On rare occasions we get a bogus socket back from
            # accept.  socketmodule.c:makesockaddr complains that the
            # address family is unknown.  We don't want the whole server
            # to shut down because of this.
            if self.adj.log_socket_errors:
                self.log_info ('warning: server accept() threw an exception',
                               'warning')
            return
        for (level, optname, value) in self.adj.socket_options:
            conn.setsockopt(level, optname, value)
        self.channel_class(self, conn, addr, self.adj)
