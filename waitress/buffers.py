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

from waitress.compat import thread

# copy_bytes controls the size of temp. strings for shuffling data around.
COPY_BYTES = 1 << 18  # 256K

# The maximum number of bytes to buffer in a simple string.
STRBUF_LIMIT = 8192


class FileBasedBuffer(object):

    remain = 0

    def __init__(self, file, from_buffer=None):
        self.file = file
        if from_buffer is not None:
            from_file = from_buffer.getfile()
            read_pos = from_file.tell()
            from_file.seek(0)
            while 1:
                data = from_file.read(COPY_BYTES)
                if not data:
                    break
                file.write(data)
            self.remain = int(file.tell() - read_pos)
            from_file.seek(read_pos)
            file.seek(read_pos)

    def __len__(self):
        return self.remain

    def __nonzero__(self):
        return self.remain > 0

    __bool__ = __nonzero__ # py3

    def append(self, s):
        file = self.file
        read_pos = file.tell()
        file.seek(0, 2)
        file.write(s)
        file.seek(read_pos)
        self.remain = self.remain + len(s)

    def get(self, numbytes=-1, skip=False):
        file = self.file
        if not skip:
            read_pos = file.tell()
        if numbytes < 0:
            # Read all
            res = file.read()
        else:
            res = file.read(numbytes)
        if skip:
            self.remain -= len(res)
        else:
            file.seek(read_pos)
        return res

    def skip(self, numbytes, allow_prune=0):
        if self.remain < numbytes:
            raise ValueError("Can't skip %d bytes in buffer of %d bytes" % (
                numbytes, self.remain)
                )
        self.file.seek(numbytes, 1)
        self.remain = self.remain - numbytes

    def newfile(self):
        raise NotImplementedError()

    def prune(self):
        file = self.file
        if self.remain == 0:
            read_pos = file.tell()
            file.seek(0, 2)
            sz = file.tell()
            file.seek(read_pos)
            if sz == 0:
                # Nothing to prune.
                return
        nf = self.newfile()
        while 1:
            data = file.read(COPY_BYTES)
            if not data:
                break
            nf.write(data)
        self.file = nf

    def getfile(self):
        return self.file



class TempfileBasedBuffer(FileBasedBuffer):

    def __init__(self, from_buffer=None):
        FileBasedBuffer.__init__(self, self.newfile(), from_buffer)

    def newfile(self):
        from tempfile import TemporaryFile
        return TemporaryFile('w+b')



class BytesIOBasedBuffer(FileBasedBuffer):

    def __init__(self, from_buffer=None):
        if from_buffer is not None:
            FileBasedBuffer.__init__(self, BytesIO(), from_buffer)
        else:
            # Shortcut. :-)
            self.file = BytesIO()

    def newfile(self):
        return BytesIO()



class OverflowableBuffer(object):
    """
    This buffer implementation has four stages:
    - No data
    - String-based buffer
    - StringIO-based buffer
    - Temporary file storage
    The first two stages are fastest for simple transfers.
    """

    overflowed = False
    buf = None
    strbuf = b''  # Bytes-based buffer.

    def __init__(self, overflow):
        # overflow is the maximum to be stored in a StringIO buffer.
        self.overflow = overflow
        self.lock = thread.allocate_lock() # API

    def __len__(self):
        buf = self.buf
        if buf is not None:
            return len(buf)
        else:
            return len(self.strbuf)

    def __nonzero__(self):
        return bool(len(self))

    __bool__ = __nonzero__ # py3

    def _create_buffer(self):
        strbuf = self.strbuf
        if len(strbuf) >= self.overflow:
            self._set_large_buffer()
        else:
            self._set_small_buffer()
        buf = self.buf
        if strbuf:
            buf.append(self.strbuf)
            self.strbuf = b''
        return buf

    def _set_small_buffer(self):
        self.buf = BytesIOBasedBuffer(self.buf)
        self.overflowed = False

    def _set_large_buffer(self):
        self.buf = TempfileBasedBuffer(self.buf)
        self.overflowed = True

    def append(self, s):
        buf = self.buf
        if buf is None:
            strbuf = self.strbuf
            if len(strbuf) + len(s) < STRBUF_LIMIT:
                self.strbuf = strbuf + s
                return
            buf = self._create_buffer()
        buf.append(s)
        sz = len(buf)
        if not self.overflowed:
            if sz >= self.overflow:
                self._set_large_buffer()

    def get(self, numbytes=-1, skip=False):
        buf = self.buf
        if buf is None:
            strbuf = self.strbuf
            if not skip:
                return strbuf
            buf = self._create_buffer()
        return buf.get(numbytes, skip)

    def skip(self, numbytes, allow_prune=False):
        buf = self.buf
        if buf is None:
            if allow_prune and numbytes == len(self.strbuf):
                # We could slice instead of converting to
                # a buffer, but that would eat up memory in
                # large transfers.
                self.strbuf = b''
                return
            buf = self._create_buffer()
        buf.skip(numbytes, allow_prune)

    def prune(self):
        """
        A potentially expensive operation that removes all data
        already retrieved from the buffer.
        """
        buf = self.buf
        if buf is None:
            self.strbuf = b''
            return
        buf.prune()
        if self.overflowed:
            sz = len(buf)
            if sz < self.overflow:
                # Revert to a faster buffer.
                self._set_small_buffer()

    def getfile(self):
        buf = self.buf
        if buf is None:
            buf = self._create_buffer()
        return buf.getfile()
