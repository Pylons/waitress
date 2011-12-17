##############################################################################
#
# Copyright (c) 2001 Zope Foundation and Contributors.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
##############################################################################
"""Test Publisher-based HTTP Server
"""
import StringIO
import sys
import unittest
from asyncore import socket_map, poll
from threading import Thread
from time import sleep
from httplib import HTTPConnection

from zope.server.taskthreads import ThreadedTaskDispatcher

from zope.component.testing import PlacelessSetup
import zope.component

from zope.i18n.interfaces import IUserPreferredCharsets

from zope.publisher.publish import publish
from zope.publisher.http import IHTTPRequest
from zope.publisher.http import HTTPCharsets
from zope.publisher.browser import BrowserRequest
from zope.publisher.base import DefaultPublication
from zope.publisher.interfaces import Redirect, Retry
from zope.publisher.http import HTTPRequest

td = ThreadedTaskDispatcher()

LOCALHOST = '127.0.0.1'

HTTPRequest.STAGGER_RETRIES = 0  # Don't pause.


class Conflict(Exception):
    """
    Pseudo ZODB conflict error.
    """

ERROR_RESPONSE = "error occurred"
RESPONSE = "normal response"

class DummyException(Exception):
    value = "Dummy Exception to test start_response"
    def __str__(self):
        return repr(self.value)

class PublicationWithConflict(DefaultPublication):

    def handleException(self, object, request, exc_info, retry_allowed=1):
        if exc_info[0] is Conflict and retry_allowed:
            # This simulates a ZODB retry.
            raise Retry(exc_info)
        else:
            DefaultPublication.handleException(self, object, request, exc_info,
                                               retry_allowed)

class Accepted(Exception):
    pass

class tested_object(object):
    """Docstring required by publisher."""
    tries = 0

    def __call__(self, REQUEST):
        return 'URL invoked: %s' % REQUEST.URL

    def redirect_method(self, REQUEST):
        "Generates a redirect using the redirect() method."
        REQUEST.response.redirect("/redirect")

    def redirect_exception(self):
        "Generates a redirect using an exception."
        raise Redirect("/exception")

    def conflict(self, REQUEST, wait_tries):
        """
        Returns 202 status only after (wait_tries) tries.
        """
        if self.tries >= int(wait_tries):
            raise Accepted
        else:
            self.tries += 1
            raise Conflict

    def proxy(self, REQUEST):
        """Behaves like a real proxy response."""
        REQUEST.response.addHeader('Server', 'Fake/1.0')
        REQUEST.response.addHeader('Date', 'Thu, 01 Apr 2010 12:00:00 GMT')
        return 'Proxied Content'

class WSGIInfo(object):
    """Docstring required by publisher"""

    def __call__(self, REQUEST):
        """Return a list of variables beginning with 'wsgi.'"""
        r = []
        for name in REQUEST.keys():
            if name.startswith('wsgi.'):
                r.append(name)
        return ' '.join(r)

    def version(self, REQUEST):
        """Return WSGI version"""
        return str(REQUEST['wsgi.version'])

    def url_scheme(self, REQUEST):
        """Return WSGI URL scheme"""
        return REQUEST['wsgi.url_scheme']

    def multithread(self, REQUEST):
        """Return WSGI multithreadedness"""
        return str(bool(REQUEST['wsgi.multithread']))

    def multiprocess(self, REQUEST):
        """Return WSGI multiprocessedness"""
        return str(bool(REQUEST['wsgi.multiprocess']))

    def run_once(self, REQUEST):
        """Return whether WSGI app is invoked only once or not"""
        return str(bool(REQUEST['wsgi.run_once']))

    def proxy_scheme(self, REQUEST):
        """Return the proxy scheme."""
        return REQUEST['zserver.proxy.scheme']

    def proxy_host(self, REQUEST):
        """Return the proxy host."""
        return REQUEST['zserver.proxy.host']

class Tests(PlacelessSetup, unittest.TestCase):

    def _getServerClass(self):
        # import only now to prevent the testrunner from importing it too early
        # Otherwise dualmodechannel.the_trigger is closed by the ZEO tests
        from zope.server.http.wsgihttpserver import WSGIHTTPServer
        return WSGIHTTPServer

    def setUp(self):
        super(Tests, self).setUp()
        zope.component.provideAdapter(HTTPCharsets, [IHTTPRequest],
                                      IUserPreferredCharsets, '')
        obj = tested_object()
        obj.folder = tested_object()
        obj.folder.item = tested_object()
        obj._protected = tested_object()
        obj.wsgi = WSGIInfo()

        pub = PublicationWithConflict(obj)

        def application(environ, start_response):
            request = BrowserRequest(environ['wsgi.input'], environ)
            request.setPublication(pub)
            request = publish(request)
            response = request.response
            start_response(response.getStatusString(), response.getHeaders())
            return response.consumeBodyIter()

        td.setThreadCount(4)
        # Bind to any port on localhost.
        ServerClass = self._getServerClass()
        self.server = ServerClass(application, 'Browser',
                                  LOCALHOST, 0, task_dispatcher=td)

        self.port = self.server.socket.getsockname()[1]
        self.run_loop = 1
        self.thread = Thread(target=self.loop)
        self.thread.start()
        sleep(0.1)  # Give the thread some time to start.

    def tearDown(self):
        self.run_loop = 0
        self.thread.join()
        td.shutdown()
        self.server.close()
        super(Tests, self).tearDown()

    def loop(self):
        while self.run_loop:
            poll(0.1, socket_map)

    def invokeRequest(self, path='/', add_headers=None, request_body='',
                      return_response=False):
        h = HTTPConnection(LOCALHOST, self.port)
        h.putrequest('GET', path)
        h.putheader('Accept', 'text/plain')
        if add_headers:
            for k, v in add_headers.items():
                h.putheader(k, v)
        if request_body:
            h.putheader('Content-Length', str(int(len(request_body))))
        h.endheaders()
        if request_body:
            h.send(request_body)
        response = h.getresponse()
        if return_response:
            return response
        length = int(response.getheader('Content-Length', '0'))
        if length:
            response_body = response.read(length)
        else:
            response_body = ''

        self.assertEqual(length, len(response_body))

        return response.status, response_body


    def testDeeperPath(self):
        status, response_body = self.invokeRequest('/folder/item')
        self.assertEqual(status, 200)
        expect_response = 'URL invoked: http://%s:%d/folder/item' % (
            LOCALHOST, self.port)
        self.assertEqual(response_body, expect_response)

    def testNotFound(self):
        status, response_body = self.invokeRequest('/foo/bar')
        self.assertEqual(status, 404)

    def testUnauthorized(self):
        status, response_body = self.invokeRequest('/_protected')
        self.assertEqual(status, 401)

    def testRedirectMethod(self):
        status, response_body = self.invokeRequest('/redirect_method')
        self.assertEqual(status, 303)

    def testRedirectException(self):
        status, response_body = self.invokeRequest('/redirect_exception')
        self.assertEqual(status, 303)
        status, response_body = self.invokeRequest('/folder/redirect_exception')
        self.assertEqual(status, 303)

    def testConflictRetry(self):
        status, response_body = self.invokeRequest('/conflict?wait_tries=2')
        # Expect the "Accepted" response since the retries will succeed.
        self.assertEqual(status, 202)

    def testFailedConflictRetry(self):
        status, response_body = self.invokeRequest('/conflict?wait_tries=10')
        # Expect a "Conflict" response since there will be too many
        # conflicts.
        self.assertEqual(status, 409)

    def testServerAsProxy(self):
        response = self.invokeRequest(
            '/proxy', return_response=True)
        # The headers set by the proxy are honored,
        self.assertEqual(
            response.getheader('Server'), 'Fake/1.0')
        self.assertEqual(
            response.getheader('Date'), 'Thu, 01 Apr 2010 12:00:00 GMT')
        # The server adds a Via header.
        self.assertEqual(
            response.getheader('Via'), 'zope.server.http (Browser)')
        # And the content got here too.
        self.assertEqual(response.read(), 'Proxied Content')

    def testWSGIVariables(self):
        # Assert that the environment contains all required WSGI variables
        status, response_body = self.invokeRequest('/wsgi')
        wsgi_variables = set(response_body.split())
        self.assertEqual(wsgi_variables,
                         set(['wsgi.version', 'wsgi.url_scheme', 'wsgi.input',
                              'wsgi.errors', 'wsgi.multithread',
                              'wsgi.multiprocess', 'wsgi.run_once']))

    def testWSGIVersion(self):
        status, response_body = self.invokeRequest('/wsgi/version')
        self.assertEqual("(1, 0)", response_body)

    def testWSGIURLScheme(self):
        status, response_body = self.invokeRequest('/wsgi/url_scheme')
        self.assertEqual('http', response_body)

    def testWSGIMultithread(self):
        status, response_body = self.invokeRequest('/wsgi/multithread')
        self.assertEqual('True', response_body)

    def testWSGIMultiprocess(self):
        status, response_body = self.invokeRequest('/wsgi/multiprocess')
        self.assertEqual('True', response_body)

    def testWSGIRunOnce(self):
        status, response_body = self.invokeRequest('/wsgi/run_once')
        self.assertEqual('False', response_body)

    def testWSGIProxy(self):
        status, response_body = self.invokeRequest(
            'https://zope.org:8080/wsgi/proxy_scheme')
        self.assertEqual('https', response_body)
        status, response_body = self.invokeRequest(
            'https://zope.org:8080/wsgi/proxy_host')
        self.assertEqual('zope.org:8080', response_body)

    def test_ensure_multiple_task_write_calls(self):
        # In order to get data out as fast as possible, the WSGI server needs
        # to call task.write() multiple times.
        orig_app = self.server.application
        def app(eviron, start_response):
            start_response('200 Ok', [])
            return ['This', 'is', 'my', 'response.']
        self.server.application = app

        class FakeTask:
            wrote_header = 0
            counter = 0
            getCGIEnvironment = lambda _: {}
            class request_data:
                getBodyStream = lambda _: StringIO.StringIO()
            request_data = request_data()
            setResponseStatus = appendResponseHeaders = lambda *_: None
            def wroteResponseHeader(self):
                return self.wrote_header
            def write(self, v):
                self.counter += 1

        task = FakeTask()
        self.server.executeRequest(task)
        self.assertEqual(task.counter, 4)

        self.server.application = orig_app

    def _getFakeAppAndTask(self):

        def app(environ, start_response):
            try:
                raise DummyException()
            except DummyException:
                start_response(
                    '500 Internal Error',
                    [('Content-type', 'text/plain')],
                    sys.exc_info())
                return ERROR_RESPONSE.split()
            return RESPONSE.split()

        class FakeTask:
            wrote_header = 0
            status = None
            reason = None
            response = []
            accumulated_headers = None
            def __init__(self):
                self.accumulated_headers = []
                self.response_headers = {}
            getCGIEnvironment = lambda _: {}
            class request_data:
                getBodyStream = lambda _: StringIO.StringIO()
            request_data = request_data()
            def appendResponseHeaders(self, lst):
                accum = self.accumulated_headers
                if accum is None:
                    self.accumulated_headers = accum = []
                accum.extend(lst)
            def setResponseStatus(self, status, reason):
                self.status = status
                self.reason = reason
            def wroteResponseHeader(self):
                return self.wrote_header
            def write(self, v):
                self.response.append(v)

        return app, FakeTask()


    def test_start_response_with_no_headers_sent(self):
        # start_response exc_info if no headers have been sent
        orig_app = self.server.application
        self.server.application, task = self._getFakeAppAndTask()
        task.accumulated_headers = ['header1', 'header2']
        task.accumulated_headers = {'key1': 'value1', 'key2': 'value2'}

        self.server.executeRequest(task)

        self.assertEqual(task.status, "500")
        self.assertEqual(task.response, ERROR_RESPONSE.split())
        # any headers written before are cleared and
        # only the most recent one is added.
        self.assertEqual(task.accumulated_headers, ['Content-type: text/plain'])
        # response headers are cleared. They'll be rebuilt from
        # accumulated_headers in the prepareResponseHeaders method
        self.assertEqual(task.response_headers, {})

        self.server.application = orig_app


    def test_multiple_start_response_calls(self):
        # if start_response is called more than once with no exc_info
        ignore, task = self._getFakeAppAndTask()
        task.wrote_header = 1

        self.assertRaises(AssertionError, self.server.executeRequest, task)


    def test_start_response_with_headers_sent(self):
        # If headers have been sent it raises the exception
        orig_app = self.server.application
        self.server.application, task = self._getFakeAppAndTask()

        # If headers have already been written an exception is raised
        task.wrote_header = 1
        self.assertRaises(DummyException, self.server.executeRequest, task)

        self.server.application = orig_app

class PMDBTests(Tests):

    def _getServerClass(self):
        # import only now to prevent the testrunner from importing it too early
        # Otherwise dualmodechannel.the_trigger is closed by the ZEO tests
        from zope.server.http.wsgihttpserver import PMDBWSGIHTTPServer
        return PMDBWSGIHTTPServer

    def testWSGIVariables(self):
        # Assert that the environment contains all required WSGI variables
        status, response_body = self.invokeRequest('/wsgi')
        wsgi_variables = set(response_body.split())
        self.assertEqual(wsgi_variables,
                         set(['wsgi.version', 'wsgi.url_scheme', 'wsgi.input',
                              'wsgi.errors', 'wsgi.multithread',
                              'wsgi.multiprocess', 'wsgi.handleErrors',
                              'wsgi.run_once']))

    def test_multiple_start_response_calls(self):
        # if start_response is called more than once with no exc_info
        ignore, task = self._getFakeAppAndTask()
        task.wrote_header = 1

        # monkey-patch pdb.post_mortem so we don't go into pdb session.
        pm_traceback = []
        def fake_post_mortem(tb):
            import traceback
            pm_traceback.extend(traceback.format_tb(tb))

        import pdb
        orig_post_mortem = pdb.post_mortem
        pdb.post_mortem = fake_post_mortem

        self.assertRaises(AssertionError, self.server.executeRequest, task)
        expected_msg = "start_response called a second time"
        self.assertTrue(expected_msg in pm_traceback[-1])
        pdb.post_mortem = orig_post_mortem

    def test_start_response_with_headers_sent(self):
        # If headers have been sent it raises the exception, which will
        # be caught by the server and invoke pdb.post_mortem.
        orig_app = self.server.application
        self.server.application, task = self._getFakeAppAndTask()
        task.wrote_header = 1

        # monkey-patch pdb.post_mortem so we don't go into pdb session.
        pm_traceback = []
        def fake_post_mortem(tb):
            import traceback
            pm_traceback.extend(traceback.format_tb(tb))

        import pdb
        orig_post_mortem = pdb.post_mortem
        pdb.post_mortem = fake_post_mortem

        self.assertRaises(DummyException, self.server.executeRequest, task)
        self.assertTrue("raise DummyException" in pm_traceback[-1])

        self.server.application = orig_app
        pdb.post_mortem = orig_post_mortem


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(Tests),
        unittest.makeSuite(PMDBTests),
        ))

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
