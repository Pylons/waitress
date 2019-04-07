##############################################################################
#
# Copyright (c) 2001-2004 Zope Foundation and Contributors.
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
"""Buffers
"""
from io import BytesIO
from tempfile import TemporaryFile

# copy_bytes controls the size of temp. strings for shuffling data around.
COPY_BYTES = 1 << 18 # 256K

# The maximum number of bytes to buffer in a simple string.
STRBUF_LIMIT = 8192

class FileBasedBuffer(object):
    seekable = True
    remaining = 0  # -1 would indicate an infinite stream

    def append(self, s):
        assert self.seekable
        # unsupported for remaining == -1
        file = self.file
        read_pos = file.tell()
        file.seek(0, 2)
        file.write(s)
        file.seek(read_pos)
        self.remaining += len(s)

    def read(self, numbytes=-1):
        file = self.file
        if numbytes < 0:
            # Read all
            res = file.read()
        else:
            res = file.read(numbytes)
        numres = len(res)
        if self.remaining == -1:
            # keep remaining at -1 until EOF
            if not numres and numbytes != 0:
                self.remaining = 0
        else:
            self.remaining -= numres
        return res

    def rollback(self, numbytes):
        assert self.seekable
        # unsupported for remaining == -1
        self.file.seek(-numbytes, 1)
        self.remaining += numbytes

    def close(self):
        self.remaining = 0
        if hasattr(self.file, 'close'):
            self.file.close()

class TempfileBasedBuffer(FileBasedBuffer):

    def __init__(self, from_buffer=None):
        file = TemporaryFile('w+b')
        if from_buffer is not None:
            while True:
                data = from_buffer.read(COPY_BYTES)
                if not data:
                    break
                file.write(data)
                self.remaining += len(data)
            file.seek(0)
        self.file = file

class BytesIOBasedBuffer(FileBasedBuffer):

    def __init__(self, value=None):
        self.file = BytesIO(value)
        if value is not None:
            self.remaining = len(value)

def _is_seekable(fp):
    if hasattr(fp, 'seekable'):
        return fp.seekable()
    return hasattr(fp, 'seek') and hasattr(fp, 'tell')

class ReadOnlyFileBasedBuffer(FileBasedBuffer):
    # used as wsgi.file_wrapper
    remaining = -1

    def __init__(self, file, block_size=32768):
        self.file = file
        self.block_size = block_size # for __iter__
        self.seekable = _is_seekable(file)

    def prepare(self, size=None):
        if self.seekable:
            start_pos = self.file.tell()
            self.file.seek(0, 2)
            end_pos = self.file.tell()
            self.file.seek(start_pos)
            fsize = end_pos - start_pos
            if size is None:
                self.remaining = fsize
            else:
                self.remaining = min(fsize, size)
        return self.remaining

    def __iter__(self): # called by task if self.filelike has no seek/tell
        return self

    def next(self):
        val = self.read(self.block_size)
        if not val:
            raise StopIteration
        return val

    __next__ = next # py3

    def append(self, s):
        raise NotImplementedError

class OverflowableBuffer(object):
    """
    This buffer implementation has four stages:
    - No data
    - Bytes-based buffer
    - BytesIO-based buffer
    - Temporary file storage
    The first two stages are fastest for simple transfers.
    """

    seekable = True
    remaining = 0

    overflowed = False
    buf = None
    strbuf = b'' # Bytes-based buffer.

    def __init__(self, overflow):
        # overflow is the maximum to be stored in a BytesIO buffer.
        self.overflow = overflow

    def append(self, s):
        buf = self.buf
        if buf is None:
            strbuf = self.strbuf
            if len(strbuf) + len(s) < STRBUF_LIMIT:
                self.strbuf += s
                self.remaining += len(s)
                return
            else:
                buf = BytesIOBasedBuffer(self.strbuf + s)
                self.buf = buf
                self.strbuf = b''
        else:
            buf.append(s)
        remaining = buf.remaining
        self.remaining = remaining
        if not self.overflowed and remaining > self.overflow:
            self.buf = TempfileBasedBuffer(buf)
            self.overflowed = True

    def read(self, numbytes=-1):
        if self.buf is None:
            if self.remaining < numbytes or numbytes == -1:
                self.remaining = 0
                return self.strbuf
            self.buf = BytesIOBasedBuffer(self.strbuf)
        buf = self.buf
        data = buf.read(numbytes)
        self.remaining = buf.remaining
        return data

    def rollback(self, numbytes):
        # never called unless read returns something indicating we have a buf
        buf = self.buf
        if buf is None:
            self.strbuf = self.strbuf[numbytes:]
            self.remaining = len(self.strbuf)
            return
        buf.rollback(numbytes)
        self.remaining = buf.remaining

    def close(self):
        self.remaining = 0
        self.strbuf = b''
        buf = self.buf
        if buf is not None:
            buf.close()
