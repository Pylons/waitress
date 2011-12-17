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
"""Zope 3's Servers

This package contains generic base classes for channel-based servers, the
servers themselves and helper objects, such as tasks and requests.
"""
import asyncore

from zope.server.interfaces import IDispatcher
from zope.interface import classImplements

# Tell the the async.dispatcher that it implements IDispatcher.
classImplements(asyncore.dispatcher, IDispatcher)
