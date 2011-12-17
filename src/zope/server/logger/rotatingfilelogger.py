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
"""Rotating File Logger

Rotates a log file in time intervals.
"""
import time
import os
import stat

from zope.server.logger.filelogger import FileLogger

class RotatingFileLogger(FileLogger):
    """ If freq is non-None we back up 'daily', 'weekly', or
        'monthly'.  Else if maxsize is non-None we back up whenever
        the log gets to big.  If both are None we never back up.

        Like a FileLogger, but it must be attached to a filename.
        When the log gets too full, or a certain time has passed, it
        backs up the log and starts a new one.  Note that backing up
        the log is done via 'mv' because anything else (cp, gzip)
        would take time, during which medusa would do nothing else.
    """

    def __init__(self, file, freq=None, maxsize=None, flush=1, mode='a'):
        self.filename = file
        self.mode = mode
        self.file = open(file, mode)
        self.freq = freq
        self.maxsize = maxsize
        self.rotate_when = self.next_backup(self.freq)
        self.do_flush = flush

    def __repr__(self):
        return '<rotating-file logger: %s>' % self.file

    # We back up at midnight every 1) day, 2) monday, or 3) 1st of month
    def next_backup(self, freq):
        (yr, mo, day, hr, min, sec, wd, jday, dst) = \
             time.localtime(time.time())
        if freq == 'daily':
            return time.mktime((yr,mo,day+1, 0,0,0, 0,0,-1))
        elif freq == 'weekly':
            # wd(monday)==0
            return time.mktime((yr,mo,day-wd+7, 0,0,0, 0,0,-1))
        elif freq == 'monthly':
            return time.mktime((yr,mo+1,1, 0,0,0, 0,0,-1))
        else:
            return None                  # not a date-based backup

    def maybe_flush(self):              # rotate first if necessary
        self.maybe_rotate()
        if self.do_flush:                # from file_logger()
            self.file.flush()

    def maybe_rotate(self):
        if self.freq and time.time() > self.rotate_when:
            self.rotate()
            self.rotate_when = self.next_backup(self.freq)
        elif self.maxsize:               # rotate when we get too big
            try:
                if os.stat(self.filename)[stat.ST_SIZE] > self.maxsize:
                    self.rotate()
            except os.error:             # file not found, probably
                self.rotate()            # will create a new file

    def rotate(self):
        yr, mo, day, hr, min, sec, wd, jday, dst = time.localtime(time.time())
        try:
            self.file.close()
            newname = '%s.ends%04d%02d%02d' % (self.filename, yr, mo, day)
            try:
                open(newname, "r").close()      # check if file exists
                newname = newname + "-%02d%02d%02d" % (hr, min, sec)
            except IOError:     # concatenation of YEAR MO DY is unique
                pass
            os.rename(self.filename, newname)
            self.file = open(self.filename, self.mode)
        except IOError:
            pass
