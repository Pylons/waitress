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
"""Syslog Logger

Writes log messages to syslog.
"""

import os
from zope.server.logger import m_syslog

from zope.server.interfaces.logger import IMessageLogger
from zope.interface import implements


class SyslogLogger(m_syslog.syslog_client):
    """syslog is a line-oriented log protocol - this class would be
       appropriate for FTP or HTTP logs, but not for dumping stderr
       to.

       TODO: a simple safety wrapper that will ensure that the line
       sent to syslog is reasonable.

       TODO: async version of syslog_client: now, log entries use
       blocking send()
    """

    implements(IMessageLogger)

    svc_name = 'zope'
    pid_str  = str(os.getpid())

    def __init__ (self, address, facility='user'):
        m_syslog.syslog_client.__init__ (self, address)
        self.facility = m_syslog.facility_names[facility]
        self.address=address

    def __repr__ (self):
        return '<syslog logger address=%s>' % (repr(self.address))

    def logMessage(self, message):
        'See IMessageLogger'
        m_syslog.syslog_client.log (
            self,
            '%s[%s]: %s' % (self.svc_name, self.pid_str, message),
            facility=self.facility,
            priority=m_syslog.LOG_INFO
            )
