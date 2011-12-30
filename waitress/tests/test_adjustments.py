import unittest

class Test_asbool(unittest.TestCase):
    def _callFUT(self, s):
        from waitress.adjustments import asbool
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

class TestAdjustments(unittest.TestCase):
    def _makeOne(self, **kw):
        from waitress.adjustments import Adjustments
        return Adjustments(**kw)
    
    def test_goodvars(self):
        inst = self._makeOne(
            host='host', port='8080', threads='5',
            url_scheme='https', backlog='20', recv_bytes='200',
            send_bytes='300', outbuf_overflow='400', inbuf_overflow='500',
            connection_limit='1000', cleanup_interval='1100',
            channel_timeout='1200', log_socket_errors='true',
            max_request_header_size='1300', max_request_body_size='1400',
            expose_tracebacks='true')
        self.assertEqual(inst.host, 'host')
        self.assertEqual(inst.port, 8080)
        self.assertEqual(inst.threads, 5)
        self.assertEqual(inst.url_scheme, 'https')
        self.assertEqual(inst.backlog, 20)
        self.assertEqual(inst.recv_bytes, 200)
        self.assertEqual(inst.send_bytes, 300)
        self.assertEqual(inst.outbuf_overflow, 400)
        self.assertEqual(inst.inbuf_overflow, 500)
        self.assertEqual(inst.connection_limit, 1000)
        self.assertEqual(inst.cleanup_interval, 1100)
        self.assertEqual(inst.channel_timeout, 1200)
        self.assertEqual(inst.log_socket_errors, True)
        self.assertEqual(inst.max_request_header_size, 1300)
        self.assertEqual(inst.max_request_body_size, 1400)
        self.assertEqual(inst.expose_tracebacks, True)

    def test_badvar(self):
        self.assertRaises(ValueError, self._makeOne, nope=True)

