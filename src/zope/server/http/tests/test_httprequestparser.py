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
from zope.server.http.httprequestparser import HTTPRequestParser
from zope.server.adjustments import Adjustments


my_adj = Adjustments()

class Tests(unittest.TestCase):

    def setUp(self):
        self.parser = HTTPRequestParser(my_adj)

    def feed(self, data):
        parser = self.parser
        for n in xrange(100): # make sure we never loop forever
            consumed = parser.received(data)
            data = data[consumed:]
            if parser.completed:
                return
        raise ValueError('Looping')

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

def test_suite():
    loader = unittest.TestLoader()
    return loader.loadTestsFromTestCase(Tests)

if __name__=='__main__':
    unittest.TextTestRunner().run(test_suite())
