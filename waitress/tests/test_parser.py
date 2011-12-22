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
"""HTTP Request Parser tests
"""
import unittest

class TestHTTPRequestParser(unittest.TestCase):
    def setUp(self):
        from waitress.parser import HTTPRequestParser
        from waitress.adjustments import Adjustments
        my_adj = Adjustments()
        self.parser = HTTPRequestParser(my_adj)

    def test_getBodyStream_None(self):
        self.parser.body_recv = None
        result = self.parser.getBodyStream()
        self.assertEqual(result.getvalue(), '')

    def test_getBodyStream_nonNone(self):
        body_rcv = DummyBodyStream()
        self.parser.body_rcv = body_rcv
        result = self.parser.getBodyStream()
        self.assertEqual(result, body_rcv)

    def test_split_uri_unquoting_unneeded(self):
        self.parser.uri = 'http://localhost:8080/abc def'
        self.parser.split_uri()
        self.assertEqual(self.parser.path, '/abc def')

    def test_split_uri_unquoting_needed(self):
        self.parser.uri = 'http://localhost:8080/abc%20def'
        self.parser.split_uri()
        self.assertEqual(self.parser.path, '/abc def')

    def test_split_url_with_query(self):
        self.parser.uri = 'http://localhost:8080/abc?a=1&b=2'
        self.parser.split_uri()
        self.assertEqual(self.parser.path, '/abc')
        self.assertEqual(self.parser.query, 'a=1&b=2')

    def test_split_url_with_query_empty(self):
        self.parser.uri = 'http://localhost:8080/abc?'
        self.parser.split_uri()
        self.assertEqual(self.parser.path, '/abc')
        self.assertEqual(self.parser.query, None)

    def test_split_url_with_fragment(self):
        self.parser.uri = 'http://localhost:8080/#foo'
        self.parser.split_uri()
        self.assertEqual(self.parser.path, '/')
        self.assertEqual(self.parser.fragment, 'foo')

    def test_split_url_https(self):
        self.parser.uri = 'https://localhost:8080/'
        self.parser.split_uri()
        self.assertEqual(self.parser.path, '/')
        self.assertEqual(self.parser.proxy_scheme, 'https')
        self.assertEqual(self.parser.proxy_netloc, 'localhost:8080')

    def test_crack_first_line_matchok(self):
        self.parser.first_line = 'get / HTTP/1.0'
        result = self.parser.crack_first_line()
        self.assertEqual(result, ('GET', '/', '1.0'))

    def test_crack_first_line_nomatch(self):
        self.parser.first_line = 'get / bleh'
        result = self.parser.crack_first_line()
        self.assertEqual(result, (None, None, None))

    def test_crack_first_line_missing_version(self):
        self.parser.first_line = 'get /'
        result = self.parser.crack_first_line()
        self.assertEqual(result, ('GET', '/', None))

    def test_get_header_lines(self):
        self.parser.header = 'slam\nslim'
        result = self.parser.get_header_lines()
        self.assertEqual(result, ['slam', 'slim'])

    def test_get_header_lines_tabbed(self):
        self.parser.header = 'slam\n\tslim'
        result = self.parser.get_header_lines()
        self.assertEqual(result, ['slamslim'])

    def test_received_nonsense_with_double_cr(self):
        data = """\
HTTP/1.0 GET /foobar


"""
        result = self.parser.received(data)
        self.assertEqual(result, 22)
        self.assertTrue(self.parser.completed)
        self.assertEqual(self.parser.headers, {})

    def test_received_nonsense_nothing(self):
        data = """\


"""
        result = self.parser.received(data)
        self.assertEqual(result, 2)
        self.assertTrue(self.parser.completed)
        self.assertEqual(self.parser.headers, {})

    def test_received_no_doublecr(self):
        data = """\
GET /foobar HTTP/8.4
"""
        result = self.parser.received(data)
        self.assertEqual(result, 21)
        self.assertFalse(self.parser.completed)
        self.assertEqual(self.parser.headers, {})

    def test_received_already_completed(self):
        self.parser.completed = True
        result = self.parser.received('a')
        self.assertEqual(result, 0)

    def test_parse_header_gardenpath(self):
        data = """\
GET /foobar HTTP/8.4
foo: bar"""
        self.parser.parse_header(data)
        self.assertEqual(self.parser.first_line, 'GET /foobar HTTP/8.4')
        self.assertEqual(self.parser.headers['FOO'], 'bar')

    def test_parse_header_no_cr_in_headerplus(self):
        data = "GET /foobar HTTP/8.4"
        self.parser.parse_header(data)
        self.assertEqual(self.parser.first_line, data)
        self.assertEqual(self.parser.header, '')

    def test_parse_header_bad_content_length(self):
        data = "GET /foobar HTTP/8.4\ncontent-length: abc"
        self.parser.parse_header(data)
        self.assertEqual(self.parser.body_rcv, None)
        

class TestHTTPRequestParserIntegration(unittest.TestCase):

    def setUp(self):
        from waitress.parser import HTTPRequestParser
        from waitress.adjustments import Adjustments
        my_adj = Adjustments()
        self.parser = HTTPRequestParser(my_adj)

    def feed(self, data):
        parser = self.parser
        for n in xrange(100): # make sure we never loop forever
            consumed = parser.received(data)
            data = data[consumed:]
            if parser.completed:
                return
        raise ValueError('Looping') # pragma: no cover

    def testSimpleGET(self):
        data = """\
GET /foobar HTTP/8.4
FirstName: mickey
lastname: Mouse
content-length: 7

Hello.
"""
        parser = self.parser
        self.feed(data)
        self.failUnless(parser.completed)
        self.assertEqual(parser.version, '8.4')
        self.failIf(parser.empty)
        self.assertEqual(parser.headers,
                         {'FIRSTNAME': 'mickey',
                          'LASTNAME': 'Mouse',
                          'CONTENT_LENGTH': '7',
                          })
        self.assertEqual(parser.path, '/foobar')
        self.assertEqual(parser.command, 'GET')
        self.assertEqual(parser.query, None)
        self.assertEqual(parser.proxy_scheme, '')
        self.assertEqual(parser.proxy_netloc, '')
        self.assertEqual(parser.getBodyStream().getvalue(), 'Hello.\n')

    def testComplexGET(self):
        data = """\
GET /foo/a+%2B%2F%C3%A4%3D%26a%3Aint?d=b+%2B%2F%3D%26b%3Aint&c+%2B%2F%3D%26c%3Aint=6 HTTP/8.4
FirstName: mickey
lastname: Mouse
content-length: 10

Hello mickey.
"""
        parser = self.parser
        self.feed(data)
        self.assertEqual(parser.command, 'GET')
        self.assertEqual(parser.version, '8.4')
        self.failIf(parser.empty)
        self.assertEqual(parser.headers,
                         {'FIRSTNAME': 'mickey',
                          'LASTNAME': 'Mouse',
                          'CONTENT_LENGTH': '10',
                          })
        # path should be utf-8 encoded
        self.assertEqual(parser.path, '/foo/a++/\xc3\xa4=&a:int')
        self.assertEqual(parser.query,
                         'd=b+%2B%2F%3D%26b%3Aint&c+%2B%2F%3D%26c%3Aint=6')
        self.assertEqual(parser.getBodyStream().getvalue(), 'Hello mick')

    def testProxyGET(self):
        data = """\
GET https://example.com:8080/foobar HTTP/8.4
content-length: 7

Hello.
"""
        parser = self.parser
        self.feed(data)
        self.failUnless(parser.completed)
        self.assertEqual(parser.version, '8.4')
        self.failIf(parser.empty)
        self.assertEqual(parser.headers,
                         {'CONTENT_LENGTH': '7',
                          })
        self.assertEqual(parser.path, '/foobar')
        self.assertEqual(parser.command, 'GET')
        self.assertEqual(parser.proxy_scheme, 'https')
        self.assertEqual(parser.proxy_netloc, 'example.com:8080')
        self.assertEqual(parser.command, 'GET')
        self.assertEqual(parser.query, None)
        self.assertEqual(parser.getBodyStream().getvalue(), 'Hello.\n')

    def testDuplicateHeaders(self):
        # Ensure that headers with the same key get concatenated as per
        # RFC2616.
        data = """\
GET /foobar HTTP/8.4
x-forwarded-for: 10.11.12.13
x-forwarded-for: unknown,127.0.0.1
X-Forwarded_for: 255.255.255.255
content-length: 7

Hello.
"""
        self.feed(data)
        self.failUnless(self.parser.completed)
        self.assertEqual(self.parser.headers, {
                'CONTENT_LENGTH': '7',
                'X_FORWARDED_FOR':
                    '10.11.12.13, unknown,127.0.0.1, 255.255.255.255',
                })

class DummyBodyStream(object):
    def getfile(self):
        return self
