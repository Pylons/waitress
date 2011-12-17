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
"""HTTP Server Channel
"""
from zope.server.serverchannelbase import ServerChannelBase
from zope.server.http.httptask import HTTPTask
from zope.server.http.httprequestparser import HTTPRequestParser


class HTTPServerChannel(ServerChannelBase):
    """HTTP-specific Server Channel"""

    task_class = HTTPTask
    parser_class = HTTPRequestParser
