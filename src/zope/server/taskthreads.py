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
"""Threaded Task Dispatcher
"""
from Queue import Queue, Empty
from thread import allocate_lock, start_new_thread
from time import time, sleep
import logging

from zope.server.interfaces import ITaskDispatcher
from zope.interface import implements


log = logging.getLogger(__name__)


class ThreadedTaskDispatcher(object):
    """A Task Dispatcher that creates a thread for each task."""

    implements(ITaskDispatcher)

    stop_count = 0  # Number of threads that will stop soon.

    def __init__(self):
        self.threads = {}  # { thread number -> 1 }
        self.queue = Queue()
        self.thread_mgmt_lock = allocate_lock()

    def handlerThread(self, thread_no):
        threads = self.threads
        try:
            while threads.get(thread_no):
                task = self.queue.get()
                if task is None:
                    # Special value: kill this thread.
                    break
                try:
                    task.service()
                except:
                    log.exception('Exception during task')
        finally:
            mlock = self.thread_mgmt_lock
            mlock.acquire()
            try:
                self.stop_count -= 1
                try: del threads[thread_no]
                except KeyError: pass
            finally:
                mlock.release()

    def setThreadCount(self, count):
        """See zope.server.interfaces.ITaskDispatcher"""
        mlock = self.thread_mgmt_lock
        mlock.acquire()
        try:
            threads = self.threads
            thread_no = 0
            running = len(threads) - self.stop_count
            while running < count:
                # Start threads.
                while thread_no in threads:
                    thread_no = thread_no + 1
                threads[thread_no] = 1
                running += 1
                start_new_thread(self.handlerThread, (thread_no,))
                thread_no = thread_no + 1
            if running > count:
                # Stop threads.
                to_stop = running - count
                self.stop_count += to_stop
                for n in range(to_stop):
                    self.queue.put(None)
                    running -= 1
        finally:
            mlock.release()

    def addTask(self, task):
        """See zope.server.interfaces.ITaskDispatcher"""
        if task is None:
            raise ValueError("No task passed to addTask().")
        # assert ITask.providedBy(task)
        try:
            task.defer()
            self.queue.put(task)
        except:
            task.cancel()
            raise

    def shutdown(self, cancel_pending=True, timeout=5):
        """See zope.server.interfaces.ITaskDispatcher"""
        self.setThreadCount(0)
        # Ensure the threads shut down.
        threads = self.threads
        expiration = time() + timeout
        while threads:
            if time() >= expiration:
                log.error("%d thread(s) still running" % len(threads))
                break
            sleep(0.1)
        if cancel_pending:
            # Cancel remaining tasks.
            try:
                queue = self.queue
                while not queue.empty():
                    task = queue.get()
                    if task is not None:
                        task.cancel()
            except Empty:
                pass

    def getPendingTasksEstimate(self):
        """See zope.server.interfaces.ITaskDispatcher"""
        return self.queue.qsize()
