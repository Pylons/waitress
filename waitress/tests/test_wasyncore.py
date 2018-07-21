import unittest


class Test__strerror(unittest.TestCase):
    def _callFUT(self, err):
        from waitress.wasyncore import _strerror
        return _strerror(err)

    def test_gardenpath(self):
        self.assertEqual(self._callFUT(1), 'Operation not permitted')

    def test_unknown(self):
        self.assertEqual(self._callFUT('wut'), 'Unknown error wut')
        
class Test_read(unittest.TestCase):
    def _callFUT(self, dispatcher):
        from waitress.wasyncore import read
        return read(dispatcher)

    def test_gardenpath(self):
        inst = DummyDispatcher()
        self._callFUT(inst)
        self.assertTrue(inst.read_event_handled)
        self.assertFalse(inst.error_handled)

    def test_reraised(self):
        from waitress.wasyncore import ExitNow
        inst = DummyDispatcher(ExitNow)
        self.assertRaises(ExitNow,self._callFUT, inst)
        self.assertTrue(inst.read_event_handled)
        self.assertFalse(inst.error_handled)

    def test_non_reraised(self):
        inst = DummyDispatcher(OSError)
        self._callFUT(inst)
        self.assertTrue(inst.read_event_handled)
        self.assertTrue(inst.error_handled)

class Test_write(unittest.TestCase):
    def _callFUT(self, dispatcher):
        from waitress.wasyncore import write
        return write(dispatcher)

    def test_gardenpath(self):
        inst = DummyDispatcher()
        self._callFUT(inst)
        self.assertTrue(inst.write_event_handled)
        self.assertFalse(inst.error_handled)

    def test_reraised(self):
        from waitress.wasyncore import ExitNow
        inst = DummyDispatcher(ExitNow)
        self.assertRaises(ExitNow,self._callFUT, inst)
        self.assertTrue(inst.write_event_handled)
        self.assertFalse(inst.error_handled)

    def test_non_reraised(self):
        inst = DummyDispatcher(OSError)
        self._callFUT(inst)
        self.assertTrue(inst.write_event_handled)
        self.assertTrue(inst.error_handled)

class Test__exception(unittest.TestCase):
    def _callFUT(self, dispatcher):
        from waitress.wasyncore import _exception
        return _exception(dispatcher)

    def test_gardenpath(self):
        inst = DummyDispatcher()
        self._callFUT(inst)
        self.assertTrue(inst.expt_event_handled)
        self.assertFalse(inst.error_handled)

    def test_reraised(self):
        from waitress.wasyncore import ExitNow
        inst = DummyDispatcher(ExitNow)
        self.assertRaises(ExitNow,self._callFUT, inst)
        self.assertTrue(inst.expt_event_handled)
        self.assertFalse(inst.error_handled)

    def test_non_reraised(self):
        inst = DummyDispatcher(OSError)
        self._callFUT(inst)
        self.assertTrue(inst.expt_event_handled)
        self.assertTrue(inst.error_handled)
        
class DummyDispatcher(object):
    read_event_handled = False
    write_event_handled = False
    expt_event_handled = False
    error_handled = False
    close_handled = False
    def __init__(self, exc=None):
        self.exc = exc

    def handle_read_event(self):
        self.read_event_handled = True
        if self.exc is not None:
            raise self.exc

    def handle_write_event(self):
        self.write_event_handled = True
        if self.exc is not None:
            raise self.exc

    def handle_expt_event(self):
        self.expt_event_handled = True
        if self.exc is not None:
            raise self.exc
        
    def handle_error(self):
        self.error_handled = True

    def handle_close(self):
        self.close_handled = True
        
        
        
        
