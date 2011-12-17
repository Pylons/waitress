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
"""Tail Logger
"""
from zope.server.interfaces.logger import IMessageLogger
from zope.interface import implements

class TailLogger(object):
    """Keep track of the last <size> log messages"""

    implements(IMessageLogger)

    def __init__(self, logger, size=500):
        self.size = size
        self.logger = logger
        self.messages = []

    def logMessage(self, message):
        'See IMessageLogger'
        self.messages.append(strip_eol(message))
        if len(self.messages) > self.size:
            del self.messages[0]
        self.logger.logMessage(message)


def strip_eol(line):
    while line and line[-1] in '\r\n':
        line = line[:-1]
    return line
