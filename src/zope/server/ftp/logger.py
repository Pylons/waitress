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
"""Common FTP Activity Logger
"""
import time

from zope.server.http.commonaccesslogger import CommonAccessLogger

class CommonFTPActivityLogger(CommonAccessLogger):
    """Outputs hits in common HTTP log format."""

    def log(self, task):
        """Receives a completed task and logs it in the common log format."""
        now = time.time()
        message = ' - %s [%s] "%s %s"' % (task.channel.username,
                                       self.log_date_string(now),
                                       task.m_name[4:].upper(),
                                       task.channel.cwd,
                                       )

        self.output.logRequest(task.channel.addr[0], message)
