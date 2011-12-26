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
import re
import socket
import sys

from waitress.adjustments import Adjustments
from waitress.channel import HTTPServerChannel
from waitress.compat import reraise
from waitress import trigger

class WSGIHTTPServer(asyncore.dispatcher, object):
    """
    if __name__ == '__main__':
        from waitress.taskthreads import ThreadedTaskDispatcher
        td = ThreadedTaskDispatcher()
        td.setThreadCount(4)
        server = WSGIHTTPServer('', 8080, task_dispatcher=td)
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
                 start=True, # test shim
                 map=None,   # test shim
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
        is_hostname = False
        for c in server_name:
            if c != '.' and not c.isdigit():
                is_hostname = True
                break
        if not is_hostname:
            try:
                if server_name == '0.0.0.0':
                    return 'localhost'
                server_name = self.socketmod.gethostbyaddr(server_name)[0]
            except socket.error: # pragma: no cover
                pass
        return server_name

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
        self.channel_class(self, conn, addr, self.adj)

    def executeRequest(self, task):
        env = task.getEnvironment()

        def start_response(status, headers, exc_info=None):
            if task.wrote_header and not exc_info:
                raise AssertionError("start_response called a second time "
                                     "without providing exc_info.")
            if exc_info:
                try:
                    if task.wrote_header:
                        # higher levels will catch and handle raised exception:
                        # 1. "service" method in task.py
                        # 2. "service" method in channel.py
                        # 3. "handlerThread" method in task.py
                        reraise(exc_info[0], exc_info[1], exc_info[2])
                    else:
                        # As per WSGI spec existing headers must be cleared
                        task.accumulated_headers = None
                        task.response_headers = {}
                finally:
                    exc_info = None

            # Prepare the headers for output
            if not isinstance(status, str):
                raise ValueError('status %s is not a string' % status)

            status, reason = re.match('([0-9]*) (.*)', status).groups()
            task.setResponseStatus(status, reason)

            for k, v in headers:
                task.appendResponseHeader(k, v)

            # Return the write method used to write the response data.
            return fakeWrite

        # Call the application to handle the request and write a response
        app_iter = self.application(env, start_response)

        # By iterating manually at this point, we execute task.write()
        # multiple times, allowing partial data to be sent.
        try:
            for value in app_iter:
                task.write(value)
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()

    def run(self):
        try:
            asyncore.loop()
        except (SystemError, KeyboardInterrupt):
            self.task_dispatcher.shutdown()

    def pull_trigger(self):
        self.trigger.pull_trigger()

def fakeWrite(body):
    raise NotImplementedError(
        "the waitress HTTP Server does not support the WSGI write() function.")

