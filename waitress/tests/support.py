"""
Support code for tests.
"""

import getopt
import logging
import sys

import waitress


class NullHandler(logging.Handler): # pragma: no cover
    """A logging handler that swallows all emitted messages.
    """
    def emit(self, record):
        pass

def start_server(app, **kwargs):  # pragma: no cover
    """Run a fixture application.

    There are three flags: `-p` to specify a port to listen on, `-u` to
    specify a Unix socket to listen on, and `-v` prevent logging from being
    disabled.
    """
    opts, _args = getopt.getopt(sys.argv[1:], 'p:u:v')
    quiet = True
    for opt, value in opts:
        if opt == '-p':
            kwargs['port'] = int(value)
        elif opt == '-u':
            kwargs.update({
                'unix_socket': value,
                'unix_socket_perms': '600',
            })
        elif opt == '-v':
            quiet = False
    if quiet:
        logging.getLogger('waitress').addHandler(NullHandler())
    waitress.serve(app, _quiet=quiet, **kwargs)
