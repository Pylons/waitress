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
"""HTTP Request Parser

This server uses asyncore to accept connections and do initial
processing but threads to do work.
"""
import re

from waitress.compat import (
    toascii,
    urlparse,
    unquote,
    StringIO,
    )
from waitress.buffers import OverflowableBuffer
from waitress.receiver import (
    FixedStreamReceiver,
    ChunkedReceiver,
    )
from waitress.utilities import find_double_newline

class HTTPRequestParser(object):
    """A structure that collects the HTTP request.

    Once the stream is completed, the instance is passed to
    a server task constructor.

    See waitress.interfaces.IStreamConsumer
    """

    completed = False  # Set once request is completed.
    empty = False        # Set if no request was made.
    header_plus = b''
    chunked = False
    content_length = 0
    body_rcv = None
    # Other attributes: first_line, header, headers, command, uri, version,
    # path, query, fragment

    def __init__(self, adj):
        """
        adj is an Adjustments object.
        """
        # headers is a mapping containing keys translated to uppercase
        # with dashes turned into underscores.
        self.headers = {}
        self.adj = adj

    def received(self, data):
        """
        Receives the HTTP stream for one request.  Returns the number of
        bytes consumed.  Sets the completed flag once both the header and the
        body have been received.
        """
        if self.completed:
            return 0  # Can't consume any more.
        datalen = len(data)
        br = self.body_rcv
        if br is None:
            # In header.
            s = self.header_plus + data
            index = find_double_newline(s)
            if index >= 0:
                # Header finished.
                header_plus = s[:index]
                consumed = len(data) - (len(s) - index)
                # Remove preceeding blank lines.
                header_plus = header_plus.lstrip()
                if not header_plus:
                    self.empty = True
                    self.completed = True
                else:
                    self.parse_header(header_plus)
                    if self.body_rcv is None:
                        self.completed = True
                return consumed
            else:
                # Header not finished yet.
                self.header_plus = s
                return datalen
        else:
            # In body.
            consumed = br.received(data)
            if br.completed:
                self.completed = True
            return consumed


    def parse_header(self, header_plus):
        """
        Parses the header_plus block of text (the headers plus the
        first line of the request).
        """
        index = header_plus.find(b'\n')
        if index >= 0:
            first_line = toascii(header_plus[:index].rstrip())
            header = header_plus[index + 1:]
        else:
            first_line = toascii(header_plus.rstrip())
            header = b''
        self.first_line = first_line

        lines = self.get_header_lines(header)

        headers = self.headers
        for line in lines:
            index = line.find(b':')
            if index > 0:
                key = line[:index]
                value = line[index + 1:].strip()
                key1 = key.upper().replace(b'-', b'_')
                # If a header already exists, we append subsequent values
                # seperated by a comma. Applications already need to handle
                # the comma seperated values, as HTTP front ends might do 
                # the concatenation for you (behavior specified in RFC2616).
                try:
                    headers[key1] += toascii(b', ' + value)
                except KeyError:
                    headers[key1] = toascii(value)
            # else there's garbage in the headers?

        command, uri, version = self.crack_first_line()
        self.command = command
        self.uri = uri
        self.version = version
        self.split_uri()
        self.url_scheme = 'http' # use Paste#prefix middleware to change

        if version == '1.1':
            te = headers.get('TRANSFER_ENCODING', '')
            if te == 'chunked':
                self.chunked = True
                buf = OverflowableBuffer(self.adj.inbuf_overflow)
                self.body_rcv = ChunkedReceiver(buf)
        if not self.chunked:
            try:
                cl = int(headers.get('CONTENT_LENGTH', 0))
            except ValueError:
                cl = 0
            self.content_length = cl
            if cl > 0:
                buf = OverflowableBuffer(self.adj.inbuf_overflow)
                self.body_rcv = FixedStreamReceiver(cl, buf)


    def get_header_lines(self, header):
        """
        Splits the header into lines, putting multi-line headers together.
        """
        r = []
        lines = header.split(b'\n')
        for line in lines:
            if line and line[0] in (b' ', b'\t'):
                r[-1] = r[-1] + line[1:]
            else:
                r.append(line)
        return r

    first_line_re = re.compile(
        '([^ ]+) ((?:[^ :?#]+://[^ ?#/]*(?:[0-9]{1,5})?)?[^ ]+)(( HTTP/([0-9.]+))$|$)')

    def crack_first_line(self):
        r = self.first_line
        m = self.first_line_re.match(r)
        if m is not None and m.end() == len(r):
            if m.group(3):
                version = m.group(5)
            else:
                version = None
            command = m.group(1).upper()
            path = m.group(2)
            return command, path, version
        else:
            return '', '', ''

    def split_uri(self):
        (self.proxy_scheme,
         self.proxy_netloc,
         path,
         self.query,
         self.fragment) = urlparse.urlsplit(self.uri)
        if path and '%' in path:
            path = unquote(path)
        self.path = path
        if self.query == '':
            self.query = None

    def getBodyStream(self):
        body_rcv = self.body_rcv
        if body_rcv is not None:
            return body_rcv.getfile()
        else:
            return StringIO(b'')
