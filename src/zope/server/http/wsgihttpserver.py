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
"""WSGI-compliant HTTP Server that uses the Zope Publisher for executing a task.
"""
import asyncore
import re
import sys
from zope.server.http.httpserver import HTTPServer
from zope.server.taskthreads import ThreadedTaskDispatcher
import zope.security.management


def fakeWrite(body):
    raise NotImplementedError(
        "Zope 3's HTTP Server does not support the WSGI write() function.")


def curriedStartResponse(task):
    def start_response(status, headers, exc_info=None):
        if task.wroteResponseHeader() and not exc_info:
            raise AssertionError("start_response called a second time "
                                 "without providing exc_info.")
        if exc_info:
            try:
                if task.wroteResponseHeader():
                    # higher levels will catch and handle raised exception:
                    # 1. "service" method in httptask.py
                    # 2. "service" method in severchannelbase.py
                    # 3. "handlerThread" method in taskthreads.py
                    raise exc_info[0], exc_info[1], exc_info[2]
                else:
                    # As per WSGI spec existing headers must be cleared
                    task.accumulated_headers = None
                    task.response_headers = {}
            finally:
                exc_info = None
        # Prepare the headers for output
        status, reason = re.match('([0-9]*) (.*)', status).groups()
        task.setResponseStatus(status, reason)
        task.appendResponseHeaders(['%s: %s' % i for i in headers])

        # Return the write method used to write the response data.
        return fakeWrite
    return start_response


class WSGIHTTPServer(HTTPServer):
    """Zope Publisher-specific WSGI-compliant HTTP Server"""

    application = None

    def __init__(self, application, sub_protocol=None, *args, **kw):

        if sys.platform[:3] == "win" and args[0] == 'localhost':
            args = ('',) + args[1:]

        self.application = application

        if sub_protocol:
            self.SERVER_IDENT += ' (%s)' %str(sub_protocol)

        HTTPServer.__init__(self, *args, **kw)

    def _constructWSGIEnvironment(self, task):
        env = task.getCGIEnvironment()

        # deduce the URL scheme (http or https)
        if (env.get('HTTPS', '').lower() == "on" or
            env.get('SERVER_PORT_SECURE') == "1"):
            protocol = 'https'
        else:
            protocol = 'http'

        # the following environment variables are required by the WSGI spec
        env['wsgi.version'] = (1,0)
        env['wsgi.url_scheme'] = protocol
        env['wsgi.errors'] = sys.stderr # apps should use the logging module
        env['wsgi.multithread'] = True
        env['wsgi.multiprocess'] = True
        env['wsgi.run_once'] = False
        env['wsgi.input'] = task.request_data.getBodyStream()

        # Add some proprietary proxy information.
        # Note: Derived request parsers might not have these new attributes,
        # so fail gracefully.
        try:
            env['zserver.proxy.scheme'] = task.request_data.proxy_scheme
            env['zserver.proxy.host'] = task.request_data.proxy_netloc
        except AttributeError:
            pass
        return env

    def executeRequest(self, task):
        """Overrides HTTPServer.executeRequest()."""
        env = self._constructWSGIEnvironment(task)

        # Call the application to handle the request and write a response
        result = self.application(env, curriedStartResponse(task))

        # By iterating manually at this point, we execute task.write()
        # multiple times, allowing partial data to be sent.
        for value in result:
            task.write(value)


class PMDBWSGIHTTPServer(WSGIHTTPServer):
    """Enter the post-mortem debugger when there's an error"""

    def executeRequest(self, task):
        """Overrides HTTPServer.executeRequest()."""
        env = self._constructWSGIEnvironment(task)
        env['wsgi.handleErrors'] = False

        # Call the application to handle the request and write a response
        try:
            result = self.application(env, curriedStartResponse(task))
            # By iterating manually at this point, we execute task.write()
            # multiple times, allowing partial data to be sent.
            for value in result:
                task.write(value)
        except:
            import sys, pdb
            print "%s:" % sys.exc_info()[0]
            print sys.exc_info()[1]
            zope.security.management.restoreInteraction()
            try:
                pdb.post_mortem(sys.exc_info()[2])
                raise
            finally:
                zope.security.management.endInteraction()


def run_paste(wsgi_app, global_conf, name='zope.server.http',
              host='127.0.0.1', port=8080, threads=4):
    port = int(port)
    threads = int(threads)

    task_dispatcher = ThreadedTaskDispatcher()
    task_dispatcher.setThreadCount(threads)
    server = WSGIHTTPServer(wsgi_app, name, host, port,
                            task_dispatcher=task_dispatcher)
    asyncore.loop()
