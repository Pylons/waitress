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

import asyncore
import socket
import sys

from waitress.adjustments import Adjustments
from waitress.channel import HTTPServerChannel
from waitress import trigger

class WSGIHTTPServer(asyncore.dispatcher, object):
    """
    if __name__ == '__main__':
        from waitress.task import ThreadedTaskDispatcher
        td = ThreadedTaskDispatcher()
        td.setThreadCount(4)
        server = WSGIHTTPServer(app, '', 8080, task_dispatcher=td)
        server.run()
    """

    channel_class = HTTPServerChannel
    SERVER_IDENT = 'waitress'
    socketmod = socket # test shim

    def __init__(self,
                 application,
                 ip,
                 port,
                 task_dispatcher,
                 ident=None,
                 adj=None,
                 map=None,
                 start=True, # test shim
                 sock=None   # test shim
                 ): 

        self.application = application

        if ident is not None:
            self.SERVER_IDENT = ident

        if sys.platform[:3] == "win" and ip == 'localhost':
            ip = ''

        self.ip = ip or '127.0.0.1'

        if adj is None:
            adj = Adjustments()
        self.adj = adj
        self.trigger = trigger.trigger(map)
        asyncore.dispatcher.__init__(self, sock, map=map)
        self.port = port
        self.task_dispatcher = task_dispatcher
        if sock is None:
            self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((ip, port))
        self.server_name = self.computeServerName(ip)
        if start:
            self.accept_connections()

    def computeServerName(self, ip):
        """Given an IP, try to determine the server name."""
        if ip:
            server_name = str(ip)
        else:
            server_name = str(self.socketmod.gethostname())
        # Convert to a host name if necessary.
        for c in server_name:
            if c != '.' and not c.isdigit():
                return server_name
        try:
            if server_name == '0.0.0.0':
                return 'localhost'
            server_name = self.socketmod.gethostbyaddr(server_name)[0]
        except socket.error: # pragma: no cover
            pass
        return server_name

    def getsockname(self):
        return self.socket.getsockname()

    def accept_connections(self):
        self.accepting = True
        self.socket.listen(self.adj.backlog)  # Get around asyncore NT limit

    def addTask(self, task):
        """See waitress.interfaces.ITaskDispatcher"""
        self.task_dispatcher.addTask(task)

    def readable(self):
        """See waitress.interfaces.IDispatcher"""
        return (self.accepting and len(self._map) < self.adj.connection_limit)

    def writable(self):
        """See waitress.interfaces.IDispatcher"""
        return False

    def handle_read(self):
        """See waitress.interfaces.IDispatcherEventHandler"""
        pass

    def handle_connect(self):
        """See waitress.interfaces.IDispatcherEventHandler"""
        pass

    def handle_accept(self):
        """See waitress.interfaces.IDispatcherEventHandler"""
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
                self.log_info('warning: server accept() threw an exception',
                              'warning')
            return
        for (level, optname, value) in self.adj.socket_options:
            conn.setsockopt(level, optname, value)
        self.channel_class(self, conn, addr, self.adj, map=self._map)

    def run(self):
        try:
            asyncore.loop(map=self._map)
        except (SystemError, KeyboardInterrupt):
            self.task_dispatcher.shutdown()

    def pull_trigger(self):
        self.trigger.pull_trigger()
