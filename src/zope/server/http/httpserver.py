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
"""HTTP Server

This server uses asyncore to accept connections and do initial
processing but threads to do work.
"""

from zope.server.serverbase import ServerBase
from zope.server.http.httpserverchannel import HTTPServerChannel


class HTTPServer(ServerBase):
    """This is a generic HTTP Server."""

    channel_class = HTTPServerChannel
    SERVER_IDENT = 'zope.server.http'

    def executeRequest(self, task):
        """Execute an HTTP request."""
        # This is a default implementation, meant to be overridden.
        body = "The HTTP server is running!\r\n" * 10
        task.response_headers['Content-Type'] = 'text/plain'
        task.response_headers['Content-Length'] = str(len(body))
        task.write(body)


if __name__ == '__main__':

    from zope.server.taskthreads import ThreadedTaskDispatcher
    td = ThreadedTaskDispatcher()
    td.setThreadCount(4)
    HTTPServer('', 8080, task_dispatcher=td)

    try:
        import asyncore
        while 1:
            asyncore.poll(5)

    except KeyboardInterrupt:
        print 'shutting down...'
        td.shutdown()
