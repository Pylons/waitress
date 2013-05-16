"""
Support code for tests.
"""

import logging
import os
import sys

import waitress

PID = os.getpid()
port = os.environ.get('WAITRESS_TEST_PORT')
if port is None:  # main process
    # To permit parallel testing under 'detox', use a PID-dependent port:
    # Subtract least-significant 20 bits of the PID from the top of the
    # allowed port range
    TEST_PORT = 0xffff - (PID & 0x7ff)
    TEST_SOCKET_PATH = '/tmp/waitress.test-%d.sock' % PID
    os.environ['WAITRESS_TEST_PORT'] = str(TEST_PORT)
else:               # pragma NO COVER subprocess
    TEST_PORT = int(port)

socket = os.environ.get('WAITRESS_TEST_SOCKET')
if socket is None:  # main process
    # To permit parallel testing under 'detox', use a PID-dependent socket.
    TEST_SOCKET_PATH = '/tmp/waitress.test-%d.sock' % PID
    os.environ['WAITRESS_TEST_SOCKET'] = TEST_SOCKET_PATH
else:               # pragma NO COVER subprocess
    TEST_SOCKET_PATH = socket

class NullHandler(logging.Handler):  # pragma: no cover
    """A logging handler that swallows all emitted messages."""
    def emit(self, record):
        pass

def start_server(app, **kwargs):  # pragma: no cover
    """Run a fixture application."""
    if len(sys.argv) == 2 and sys.argv[1] == '-u':
        kwargs.update({
            'unix_socket': TEST_SOCKET_PATH,
            'unix_socket_perms': '600',
        })
    else:
        kwargs['port'] = TEST_PORT
    logging.getLogger('waitress').addHandler(NullHandler())
    waitress.serve(app, _quiet=True, **kwargs)
