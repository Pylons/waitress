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
"""Line Task
"""
import socket
import time
from zope.server.interfaces import ITask
from zope.interface import implements


class LineTask(object):
    """This is a generic task that can be used with command line
       protocols to handle commands in a separate thread.
    """
    implements(ITask)

    def __init__(self, channel, command, m_name):
        self.channel = channel
        self.m_name = m_name
        self.args = command.args

        self.close_on_finish = 0

    def service(self):
        """Called to execute the task.
        """
        try:
            try:
                self.start()
                getattr(self.channel, self.m_name)(self.args)
                self.finish()
            except socket.error:
                self.close_on_finish = 1
                if self.channel.adj.log_socket_errors:
                    raise
            except:
                self.channel.exception()
        finally:
            if self.close_on_finish:
                self.channel.close_when_done()

    def cancel(self):
        'See ITask'
        self.channel.close_when_done()

    def defer(self):
        'See ITask'
        pass

    def start(self):
        now = time.time()
        self.start_time = now

    def finish(self):
        hit_log = self.channel.server.hit_log
        if hit_log is not None:
            hit_log.log(self)
