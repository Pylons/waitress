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
"""Resolving Logger
"""
from zope.server.interfaces.logger import IRequestLogger
from zope.interface import implements


class ResolvingLogger(object):
    """Feed (ip, message) combinations into this logger to get a
    resolved hostname in front of the message.  The message will not
    be logged until the PTR request finishes (or fails)."""

    implements(IRequestLogger)

    def __init__(self, resolver, logger):
        self.resolver = resolver
        # logger is an IMessageLogger
        self.logger = logger

    class logger_thunk(object):
        def __init__(self, message, logger):
            self.message = message
            self.logger = logger

        def __call__(self, host, ttl, answer):
            if not answer:
                answer = host
            self.logger.logMessage('%s%s' % (answer, self.message))

    def logRequest(self, ip, message):
        'See IRequestLogger'
        self.resolver.resolve_ptr(
                ip,
                self.logger_thunk(
                        message,
                        self.logger
                        )
                )
