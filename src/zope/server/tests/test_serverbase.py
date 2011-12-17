##############################################################################
#
# Copyright (c) 2005 Zope Foundation and Contributors.
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
"""Tests for zope.server.serverbase
"""
import doctest
import unittest


def doctest_ServerBase():
    r"""Regression test for ServerBase

    Bug: if the `ip` argument of ServerBase is a string containing a numberic
    IP address, and the verbose argument is enabled, ServerBase.__init__
    would try to use self.logger before it was initialized.

    We will use a subclass of ServerBase so that unit tests do not actually try
    to bind to ports.

        >>> from zope.server.serverbase import ServerBase
        >>> class ServerBaseForTest(ServerBase):
        ...     def bind(self, (ip, port)):
        ...         print "Listening on %s:%d" % (ip or '*', port)
        >>> sb = ServerBaseForTest('127.0.0.1', 80, start=False, verbose=True)
        Listening on 127.0.0.1:80

    """

class FakeSocket:
    data        = ''
    setblocking = lambda *_: None
    fileno      = lambda *_: 42
    getpeername = lambda *_: ('localhost', 42)

    def send(self, data):
        self.data += data
        return len(data)


def channels_accept_iterables():
    r"""
Channels accept iterables (they special-case strings).

    >>> from zope.server.dualmodechannel import DualModeChannel
    >>> socket = FakeSocket()
    >>> channel = DualModeChannel(socket, ('localhost', 42))

    >>> channel.write("First")
    5

    >>> channel.flush()
    >>> print socket.data
    First

    >>> channel.write(["\n", "Second", "\n", "Third"])
    13

    >>> channel.flush()
    >>> print socket.data
    First
    Second
    Third

    >>> def count():
    ...     yield '\n1\n2\n3\n'
    ...     yield 'I love to count. Ha ha ha.'

    >>> channel.write(count())
    33

    >>> channel.flush()
    >>> print socket.data
    First
    Second
    Third
    1
    2
    3
    I love to count. Ha ha ha.

"""

def test_suite():
    return doctest.DocTestSuite()


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
