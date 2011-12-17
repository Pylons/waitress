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
"""Python Logger tests
"""
import unittest
import logging
from zope.interface.verify import verifyObject


class HandlerStub(logging.Handler):

    last_record = None

    def emit(self, record):
        self.last_record = record


class TestPythonLogger(unittest.TestCase):

    name = 'test.pythonlogger'

    def setUp(self):
        self.logger = logging.getLogger(self.name)
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        self.handler = HandlerStub()
        self.logger.addHandler(self.handler)

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    def test(self):
        from zope.server.logger.pythonlogger import PythonLogger
        from zope.server.interfaces.logger import IMessageLogger
        plogger = PythonLogger(self.name)
        verifyObject(IMessageLogger, plogger)
        msg1 = 'test message 1'
        plogger.logMessage(msg1)
        self.assertEquals(self.handler.last_record.msg, msg1)
        self.assertEquals(self.handler.last_record.levelno, logging.INFO)
        msg2 = 'test message 2\r\n'
        plogger.level = logging.ERROR
        plogger.logMessage(msg2)
        self.assertEquals(self.handler.last_record.msg, msg2.rstrip())
        self.assertEquals(self.handler.last_record.levelno, logging.ERROR)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestPythonLogger))
    return suite


if __name__ == '__main__':
    unittest.main()
