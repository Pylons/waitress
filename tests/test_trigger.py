import os
import sys
import unittest

if not sys.platform.startswith("win"):

    class Test_trigger(unittest.TestCase):
        def _makeOne(self, map):
            from waitress.trigger import trigger

            self.inst = trigger(map)
            return self.inst

        def tearDown(self):
            self.inst.close()  # prevent __del__ warning from file_dispatcher

        def test__close(self):
            map = {}
            inst = self._makeOne(map)
            fd1, fd2 = inst._fds
            inst.close()
            self.assertRaises(OSError, os.read, fd1, 1)
            self.assertRaises(OSError, os.read, fd2, 1)

        def test__physical_pull(self):
            map = {}
            inst = self._makeOne(map)
            inst._physical_pull()
            r = os.read(inst._fds[0], 1)
            self.assertEqual(r, b"x")

        def test_readable(self):
            map = {}
            inst = self._makeOne(map)
            self.assertTrue(inst.readable())

        def test_writable(self):
            map = {}
            inst = self._makeOne(map)
            self.assertFalse(inst.writable())

        def test_handle_connect(self):
            map = {}
            inst = self._makeOne(map)
            self.assertIsNone(inst.handle_connect())

        def test_close(self):
            map = {}
            inst = self._makeOne(map)
            self.assertIsNone(inst.close())
            self.assertTrue(inst._closed)

        def test_handle_close(self):
            map = {}
            inst = self._makeOne(map)
            self.assertIsNone(inst.handle_close())
            self.assertTrue(inst._closed)

        def test_pull_trigger_nothunk(self):
            map = {}
            inst = self._makeOne(map)
            self.assertIsNone(inst.pull_trigger())
            r = os.read(inst._fds[0], 1)
            self.assertEqual(r, b"x")

        def test_pull_trigger_thunk(self):
            map = {}
            inst = self._makeOne(map)
            self.assertIsNone(inst.pull_trigger(True))
            self.assertEqual(len(inst.thunks), 1)
            r = os.read(inst._fds[0], 1)
            self.assertEqual(r, b"x")

        def test_handle_read_socket_error(self):
            map = {}
            inst = self._makeOne(map)
            result = inst.handle_read()
            self.assertIsNone(result)

        def test_handle_read_no_socket_error(self):
            map = {}
            inst = self._makeOne(map)
            inst.pull_trigger()
            result = inst.handle_read()
            self.assertIsNone(result)

        def test_handle_read_thunk(self):
            map = {}
            inst = self._makeOne(map)
            inst.pull_trigger()
            L = []
            inst.thunks = [lambda: L.append(True)]
            result = inst.handle_read()
            self.assertIsNone(result)
            self.assertListEqual(L, [True])
            self.assertListEqual(inst.thunks, [])

        def test_handle_read_thunk_error(self):
            map = {}
            inst = self._makeOne(map)

            def errorthunk():
                raise ValueError

            inst.pull_trigger(errorthunk)
            L = []
            inst.log_info = lambda *arg: L.append(arg)
            result = inst.handle_read()
            self.assertIsNone(result)
            self.assertEqual(len(L), 1)
            self.assertListEqual(inst.thunks, [])
