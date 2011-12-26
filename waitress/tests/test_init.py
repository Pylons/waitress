import unittest

class Test_asbool(unittest.TestCase):
    def _callFUT(self, s):
        from waitress import asbool
        return asbool(s)

    def test_s_is_None(self):
        result = self._callFUT(None)
        self.assertEqual(result, False)
        
    def test_s_is_True(self):
        result = self._callFUT(True)
        self.assertEqual(result, True)
        
    def test_s_is_False(self):
        result = self._callFUT(False)
        self.assertEqual(result, False)

    def test_s_is_true(self):
        result = self._callFUT('True')
        self.assertEqual(result, True)

    def test_s_is_false(self):
        result = self._callFUT('False')
        self.assertEqual(result, False)

    def test_s_is_yes(self):
        result = self._callFUT('yes')
        self.assertEqual(result, True)

    def test_s_is_on(self):
        result = self._callFUT('on')
        self.assertEqual(result, True)

    def test_s_is_1(self):
        result = self._callFUT(1)
        self.assertEqual(result, True)

class Test_serve(unittest.TestCase):
    def _callFUT(self, app, **kw):
        from waitress import serve
        return serve(app, **kw)

    def test_it(self):
        server = DummyServerFactory()
        app = object()
        
        result = self._callFUT(app, server=server,
                               dispatcher=DummyTaskDispatcher, verbose=False)

        self.assertEqual(result, None)
        self.assertEqual(server.ran, True)
        self.assertEqual(server.host, '0.0.0.0')
        self.assertEqual(server.port, 8080)
        self.assertEqual(server.task_dispatcher.threads, 4)

class Test_serve_paste(unittest.TestCase):
    def _callFUT(self, app, **kw):
        from waitress import serve_paste
        return serve_paste(app, None, **kw)

    def test_it(self):
        server = DummyServerFactory()
        app = object()
        
        result = self._callFUT(app, server=server,
                               dispatcher=DummyTaskDispatcher, verbose=False)

        self.assertEqual(result, 0)
        self.assertEqual(server.ran, True)
        self.assertEqual(server.host, '0.0.0.0')
        self.assertEqual(server.port, 8080)
        self.assertEqual(server.task_dispatcher.threads, 4)
        
class DummyServerFactory(object):
    ran = False
    def __call__(self, app, host, port, task_dispatcher, **kw):
        self.app = app
        self.host = host
        self.port = port
        self.task_dispatcher = task_dispatcher
        self.kw = kw
        return self
    def run(self):
        self.ran = True
        
class DummyTaskDispatcher(object):
    def set_thread_count(self, num):
        self.threads = num
        
