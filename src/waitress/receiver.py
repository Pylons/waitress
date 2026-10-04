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
"""Data Chunk Receiver"""

from waitress.rfc7230 import CHUNK_EXT_RE, ONLY_HEXDIG_RE
from waitress.utilities import BadRequest, find_double_newline

MAX_CONTROL_LINE = 1024
MAX_TRAILER = 65536
# RFC 7230 allows chunk sizes up to 2**64-1; cap hex digits to limit abuse.
MAX_CHUNK_SIZE_HEX_LEN = 16


class FixedStreamReceiver:
    # See IStreamConsumer
    completed = False
    error = None

    def __init__(self, cl, buf):
        self.remain = cl
        self.buf = buf

    def __len__(self):
        return self.buf.__len__()

    def received(self, data):
        "See IStreamConsumer"
        rm = self.remain

        if rm < 1:
            self.completed = True  # Avoid any chance of spinning

            return 0
        datalen = len(data)

        if rm <= datalen:
            self.buf.append(data[:rm])
            self.remain = 0
            self.completed = True

            return rm
        else:
            self.buf.append(data)
            self.remain -= datalen

            return datalen

    def getfile(self):
        return self.buf.getfile()

    def getbuf(self):
        return self.buf


class ChunkedReceiver:
    chunk_remainder = 0
    validate_chunk_end = False
    control_line = b""
    chunk_end = b""
    all_chunks_received = False
    trailer = b""
    completed = False
    error = None

    def __init__(self, buf):
        self.buf = buf

    def __len__(self):
        return self.buf.__len__()

    def received(self, s):
        # Returns the number of bytes consumed.

        if self.completed:
            return 0
        orig_size = len(s)

        while s:
            rm = self.chunk_remainder

            if rm > 0:
                # Receive the remainder of a chunk.
                to_write = s[:rm]
                self.buf.append(to_write)
                written = len(to_write)
                s = s[written:]

                self.chunk_remainder -= written

                if self.chunk_remainder == 0:
                    self.validate_chunk_end = True
            elif self.validate_chunk_end:
                s = self.chunk_end + s

                pos = s.find(b"\r\n")

                if pos < 0 and len(s) < 2:
                    self.chunk_end = s
                    s = b""
                else:
                    self.chunk_end = b""

                    if pos == 0:
                        # Chop off the terminating CR LF from the chunk
                        s = s[2:]
                    else:
                        self.error = BadRequest("Chunk not properly terminated")
                        self.all_chunks_received = True

                    # Always exit this loop
                    self.validate_chunk_end = False
            elif not self.all_chunks_received:
                # Receive a control line.
                s = self.control_line + s
                pos = s.find(b"\r\n")

                if pos < 0:
                    # Control line not finished.
                    if len(s) > MAX_CONTROL_LINE:
                        self.error = BadRequest("Chunk control line too long")
                        self.completed = True
                        break
                    self.control_line = s
                    s = b""
                else:
                    # Control line finished.
                    line = s[:pos]
                    s = s[pos + 2 :]
                    self.control_line = b""

                    if len(line) > MAX_CONTROL_LINE:
                        self.error = BadRequest("Chunk control line too long")
                        self.completed = True
                        break

                    if line:
                        # Begin a new chunk.
                        semi = line.find(b";")

                        if semi >= 0:
                            extinfo = line[semi:]
                            valid_ext_info = CHUNK_EXT_RE.match(extinfo)

                            if not valid_ext_info:
                                self.error = BadRequest("Invalid chunk extension")
                                self.all_chunks_received = True

                                break

                            line = line[:semi]

                        if len(line) > MAX_CHUNK_SIZE_HEX_LEN:
                            self.error = BadRequest("Invalid chunk size")
                            self.all_chunks_received = True

                            break

                        if not ONLY_HEXDIG_RE.match(line):
                            self.error = BadRequest("Invalid chunk size")
                            self.all_chunks_received = True

                            break

                        # Can not fail due to matching against the regular
                        # expression above
                        sz = int(line, 16)  # hexadecimal

                        if sz > 0:
                            # Start a new chunk.
                            self.chunk_remainder = sz
                        else:
                            # Finished chunks.
                            self.all_chunks_received = True
                    # else expect a control line.
            else:
                # Receive the trailer.
                trailer = self.trailer + s

                if trailer.startswith(b"\r\n"):
                    # No trailer.
                    self.completed = True

                    return orig_size - (len(trailer) - 2)
                pos = find_double_newline(trailer)

                if pos < 0:
                    # Trailer not finished.
                    if len(trailer) > MAX_TRAILER:
                        self.error = BadRequest("Chunk trailer too long")
                        self.completed = True
                        break
                    self.trailer = trailer
                    s = b""
                else:
                    # Finished the trailer.
                    self.completed = True
                    self.trailer = trailer[:pos]

                    return orig_size - (len(trailer) - pos)

        return orig_size

    def getfile(self):
        return self.buf.getfile()

    def getbuf(self):
        return self.buf
