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

import unittest

class HTTPDateTests(unittest.TestCase):
    # test roundtrip conversion.
    def testDateRoundTrip(self):
        from waitress.utilities import build_http_date, parse_http_date
        from time import time
        t = int(time())
        self.assertEquals(t, parse_http_date(build_http_date(t)))


def test_suite():
    loader = unittest.TestLoader()
    return loader.loadTestsFromTestCase(HTTPDateTests)

if __name__=='__main__':
    unittest.TextTestRunner().run(test_suite())
