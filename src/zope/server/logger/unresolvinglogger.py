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
"""Unresolving Logger
"""
from zope.server.interfaces.logger import IRequestLogger
from zope.interface import implements

class UnresolvingLogger(object):
    """Just in case you don't want to resolve"""

    implements(IRequestLogger)

    def __init__(self, logger):
        self.logger = logger

    def logRequest(self, ip, message):
        'See IRequestLogger'
        self.logger.logMessage('%s%s' % (ip, message))
