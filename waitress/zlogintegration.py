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
"""Make asyncore log to the logging module.

As a side effect of importing this module, asyncore's logging will be
redirected to the logging module.
"""

import logging

logger = logging.getLogger("zope.server")

severity = {
    'info': logging.INFO,
    'warning': logging.WARN,
    'error': logging.ERROR,
    }

def log_info(self, message, type='info'):
    logger.log(severity.get(type, logging.INFO), message)

import asyncore
asyncore.dispatcher.log_info = log_info
