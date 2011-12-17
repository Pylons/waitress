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
"""Line receiver channel

This channels evaluates requests line by line. This is particular useful for
protocols that use a line-based command structure.
"""

from asyncore import compact_traceback
import os
import sys

from zope.server.serverchannelbase import ServerChannelBase
from zope.server.linereceiver.linecommandparser import LineCommandParser
from zope.server.linereceiver.linetask import LineTask

DEBUG = os.environ.get('ZOPE_SERVER_DEBUG')

class LineServerChannel(ServerChannelBase):
    """The Line Server Channel represents a connection to a particular
       client. We can therefore store information here."""

    # Wrapper class that is used to execute a command in a different thread
    task_class = LineTask

    # Class that is being initialized to parse the input
    parser_class = LineCommandParser

    # List of commands that are always available
    special_commands = ('cmd_quit')

    # Commands that are run in a separate thread
    thread_commands = ()

    # Define the authentication status of the channel. Note that only the
    # "special commands" can be executed without having authenticated.
    authenticated = 0

    # Define the reply code for non-authenticated responses
    not_auth_reply = 'LOGIN_REQUIRED'

    # Define the reply code for an unrecognized command
    unknown_reply = 'CMD_UNKNOWN'

    # Define the error message that occurs, when the reply code was not found.
    reply_error = '500 Unknown Reply Code: %s.'

    # Define the status messages
    status_messages = {
        'CMD_UNKNOWN'      : "500 '%s': command not understood.",
        'INTERNAL_ERROR'   : "500 Internal error: %s",
        'LOGIN_REQUIRED'   : '530 Please log in with USER and PASS',
        }


    def handle_request(self, command):
        """Processes a command.

        Some commands use an alternate thread.
        """
        assert isinstance(command, LineCommandParser)
        cmd = command.cmd
        method = 'cmd_' + cmd.lower()
        if (not self.authenticated and method not in self.special_commands):
            # The user is not logged in, therefore don't allow anything
            self.reply(self.not_auth_reply)

        elif method in self.thread_commands:
            # Process in another thread.
            task = self.task_class(self, command, method)
            self.queue_task(task)

        elif hasattr(self, method):
            try:
                getattr(self, method)(command.args)
            except:
                self.exception()
        else:
            self.reply(self.unknown_reply, cmd.upper())


    def reply(self, code, args=(), flush=1):
        """ """
        try:
            msg = self.status_messages[code] %args
        except:
            msg = self.reply_error %code

        self.write('%s\r\n' %msg)

        if flush:
            self.flush(0)

        # TODO: Some logging should go on here.


    def handle_error_no_close(self):
        """See asyncore.dispatcher.handle_error()"""
        nil, t, v, tbinfo = compact_traceback()

        # sometimes a user repr method will crash.
        try:
            self_repr = repr(self)
        except:
            self_repr = '<__repr__(self) failed for object at %0x>' % id(self)

        self.log_info(
            'uncaptured python exception, closing channel %s (%s:%s %s)' % (
                self_repr,
                t,
                v,
                tbinfo
                ),
            'error'
            )


    def exception(self):
        if DEBUG:
            import traceback
            traceback.print_exc()
        t, v = sys.exc_info()[:2]
        try:
            info = '%s: %s' % (getattr(t, '__name__', t), v)
        except:
            info = str(t)
        self.reply('INTERNAL_ERROR', info)
        self.handle_error_no_close()
        self.close_when_done()
