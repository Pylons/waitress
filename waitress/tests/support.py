"""
Support code for tests.
"""

import logging

import waitress


TEST_PORT = 61523

class NullHandler(logging.Handler):  # pragma: no cover
    """A logging handler that swallows all emitted messages."""
    def emit(self, record):
        pass

def start_server(app, **kwargs):  # pragma: no cover
    """Run a fixture application."""
    kwargs['port'] = TEST_PORT
    logging.getLogger('waitress').addHandler(NullHandler())
    waitress.serve(app, _quiet=True, **kwargs)
