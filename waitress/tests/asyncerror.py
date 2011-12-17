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
"""Mixin class to turn uncaught asyncore errors into test failues.

By default, asyncore handles uncaught exceptions in dispatchers by
printing a message to the console.  If a test causes such uncaught
exceptions, the test is marked as a failure, because asyncore handles
the exception.  This framework causes the unit test to fail.  If code
being tested expects the errors to occur, it can add code to prevent
the error from propagating all the way back to asyncore.
"""
import asyncore
import sys
import traceback

class AsyncoreErrorHook(object):
    """Convert asyncore errors into unittest failures.

    Call hook_asyncore_error in setUp() and unhook_asyncore_error() in
    tearDown(), or use super() to call setUp() and tearDown() here.
    """

    def setUp(self):
        self.hook_asyncore_error()

    def tearDown(self):
        self.unhook_asycnore_error()

    def hook_asyncore_error(self):
        self._asyncore_traceback = asyncore.compact_traceback
        asyncore.compact_traceback = self.handle_asyncore_error

    def unhook_asyncore_error(self):
        asyncore.compact_traceback = self._asyncore_traceback

    def handle_asyncore_error(self):
        L = traceback.format_exception(*sys.exc_info())
        self.fail("".join(L))
