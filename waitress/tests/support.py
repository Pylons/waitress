"""
Support code for tests.
"""

import logging
import sys

import waitress


TEST_PORT = 61523
TEST_SOCKET_PATH = '/tmp/waitress.test.sock'

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
