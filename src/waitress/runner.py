##############################################################################
#
# Copyright (c) 2013 Zope Foundation and Contributors.
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
"""Command line runner."""
import warnings
import re
import getopt
import logging
import operator as op
import os
import os.path
import pathlib
import sys
from argparse import ArgumentParser, BooleanOptionalAction
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse
import importlib
from waitress import serve
from waitress.adjustments import Adjustments
from waitress.utilities import logger

RUNNER_PATTERN = re.compile(
    r"""
    ^
    (?P<module>
        [a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*
    )
    :
    (?P<object>
        [a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*
    )
    $
    """,
    re.I | re.X,
)


def match(obj_name):
    matches = RUNNER_PATTERN.match(obj_name)

    if not matches:
        raise ValueError(f"Malformed application '{obj_name}'")

    return matches.group("module"), matches.group("object")


def resolve(module_name, object_name):
    return getattr(importlib.import_module(module_name), object_name)


def show_exception(stream):
    exc_type, exc_value = sys.exc_info()[:2]
    args = getattr(exc_value, "args", None)
    print(
        ("There was an exception ({}) importing your module.\n").format(
            exc_type.__name__,
        ),
        file=stream,
    )
    if args:
        print("It had these arguments: ", file=stream)
        for idx, arg in enumerate(args, start=1):
            print(f"{idx}. {arg}\n", file=stream)
    else:
        print("It had no arguments.", file=stream)


host_and_port = op.attrgetter("hostname", "port")


def _valid_socket(value):
    # NOTE: without dummy scheme, `urlparse` will not pick up netloc cerrectly
    res = urlparse(f"scheme://{value}")

    if not all(host_and_port(res)):
        raise ValueError("Not a socket! Should HOST:PORT", value)

    return str(ip_address(res.hostname)), str(res.port)


def _validate_opts(opts):
    if hasattr(opts, 'listen') and (hasattr(opts, 'host') or hasattr(opts, 'port')):
        raise ValueError("host or port may not be set if listen is set.")

    if hasattr(opts, 'unix_socket') and (hasattr(opts, 'host') or hasattr(opts, 'port')):
        raise ValueError("unix_socket may not be set if host or port is set")

    if hasattr(opts, 'unix_socket') and hasattr(opts, 'listen'):
        raise ValueError("unix_socket may not be set if listen is set")


@dataclass(frozen=True)
class DEFAULTS:
    BACKLOG = 1024
    HOST = "0.0.0.0"
    IDENT = "waitress"
    PORT = 8080
    THREADS = 4
    UNIX_SOCKET_PERMS = "600"
    URL_SCHEME = "http"
    # fmt: off
    ASYNCORE_LOOP_TIMEOUT   = 1     # second
    CHANNEL_TIMEOUT         = 120   # seconds
    CHANNEL_REQUEST_LOOKAHEAD = 0
    CLEANUP_INTERVAL        = 30    # seconds
    CONNECTION_LIMIT        = 100
    INBUF_HIGH_WATERMARK    = 16777216    # 16  MB
    INBUF_OVERFLOW          = 524288      # 512 KB
    MAX_REQUEST_BODY_SIZE   = 1073741824  # 1   GB
    MAX_REQUEST_HEADER_SIZE = 262144      # 256 KB
    OUTBUF_HIGH_WATERMARK   = 16777216    # 16  MB
    OUTBUF_OVERFLOW         = 1048576     # 1   MB
    RECV_BYTES              = 8192        # 8   KB
    SEND_BYTES              = 18000
    # fmt: on


def run(argv=sys.argv, _serve=serve):
    parser = ArgumentParser()
    # Standard options
    parser.add_argument(
        "--app",
        required=True,
        help="Specify WSGI application to run. Required. Can be passed at any position.",
    )
    parser.add_argument(
        "--call",
        action="store_true",
        help="Call the given object to get the WSGI application.",
    )
    parser.add_argument(
        "--host",
        type=ip_address,
        default=DEFAULTS.HOST,
        help="""Hostname or IP address on which to listen.
Note: may not be used together with `--listen`.

Default is %(default)s, which means "all IP addresses on this host".""",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULTS.PORT,
        help="""TCP port on which to listen.
Note: may not be used together with `--listen`.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--listen",
        type=_valid_socket,
        action='append',
        help="Tell waitress to listen on an ip port combination.",
    )
    parser.add_argument(
        "--ipv4", action=BooleanOptionalAction, help="Toggle on/off IPv4 support."
    )
    parser.add_argument(
        "--ipv6", action=BooleanOptionalAction, help="Toggle on/off IPv6 support."
    )
    parser.add_argument(
        "--unix-socket",
        type=pathlib.Path,
        help="""Path of Unix socket. If a socket path is specified, a
Unix domain socket is made instead of the usual inet domain socket.

Not available on Windows.""",
    )
    parser.add_argument(
        "--unix-socket-perms",
        type=lambda v: int(v, base=8),
        default=DEFAULTS.UNIX_SOCKET_PERMS,
        help="""Octal permissions to use for the Unix domain socket.
Default is %(default)s.""",
    )
    parser.add_argument(
        "--url-scheme",
        default=DEFAULTS.URL_SCHEME,
        help="Default `wsgi.url_scheme` value. Default is %(default)r.",
    )
    parser.add_argument(
        "--url-prefix",
        help="""The `SCRIPT_NAME` WSGI environment value. Setting this to
anything except the empty string will cause the WSGI `SCRIPT_NAME` value to be
the value passed minus any trailing slashes you add, and it will cause
the `PATH_INFO` of any request which is prefixed with this value to be
stripped of the prefix.""",
    )
    parser.add_argument(
        "--ident",
        default=DEFAULTS.IDENT,
        help="""Server identity used in the 'Server' header in responses.
Default is %(default)r.""",
    )
    # Tuning options
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULTS.THREADS,
        help="""Number of threads used to process application logic.
Default is %(default)s.""",
    )
    parser.add_argument(
        "--backlog",
        type=int,
        default=DEFAULTS.BACKLOG,
        help="""Connection backlog for the server. Default is %(default)s.""",
    )
    parser.add_argument(
        "--recv-bytes",
        type=int,
        default=DEFAULTS.RECV_BYTES,
        help="""Number of bytes to request when calling `socket.recv()`.
Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--send-bytes",
        type=int,
        default=DEFAULTS.SEND_BYTES,
        help="""Number of bytes to send to `socket.send()`.
Note: multiples of 9000 should avoid partly-filled TCP packets.

Default is %(default)s bytes.""",

    )
    parser.add_argument(
        "--outbuf-overflow",
        type=int,
        default=DEFAULTS.OUTBUF_OVERFLOW,
        help="""A temporary file should be created if the pending output is larger
than this.

Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--outbuf-high-watermark",
        type=int,
        default=DEFAULTS.OUTBUF_HIGH_WATERMARK,
        help="""The `app_iter` will pause when pending output is larger than
this value and will resume once enough data is written to the socket to fall
below this threshold.

Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--inbuf-overflow",
        type=int,
        default=DEFAULTS.INBUF_OVERFLOW,
        help="""A temporary file should be created if the pending input is larger
than this.

Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--connection-limit",
        type=int,
        default=DEFAULTS.CONNECTION_LIMIT,
        help="""Stop creating new channels if too many are already active.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--cleanup-interval",
        type=int,
        default=DEFAULTS.CLEANUP_INTERVAL,
        help="""Minimum seconds between cleaning up inactive channels.
See `--channel-timeout` option.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--channel-timeout",
        type=int,
        default=DEFAULTS.CHANNEL_TIMEOUT,
        help="""Maximum number of seconds to leave inactive connections open.
'Inactive' is defined as 'has received no data from the client and has sent
no data to the client'.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--max-request-header-size",
        type=int,
        default=DEFAULTS.MAX_REQUEST_HEADER_SIZE,
        help="""Maximum size of all request headers combined.
Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--max-request-body-size",
        type=int,
        default=DEFAULTS.MAX_REQUEST_BODY_SIZE,
        help="""Maximum size of request body.
Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--asyncore-loop-timeout",
        type=int,
        default=DEFAULTS.ASYNCORE_LOOP_TIMEOUT,
        help="""The timeout value in seconds passed to `asyncore.loop()`.
Default is %(default)s.""",
    )
    parser.add_argument(
        "--asyncore-use-poll",
        action="store_true",
        help="""The `use_poll` argument passed to `asyncore.loop()`. Helps overcome
open file descriptors limit.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--channel-request-lookahead",
        type=int,
        default=DEFAULTS.CHANNEL_REQUEST_LOOKAHEAD,
        help="""Allows channels to stay readable and buffer more requests up to
the given maximum even if a request is already being processed. This allows
detecting if a client closed the connection while its request is being processed.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--log-socket-errors",
        action=BooleanOptionalAction,
        help="""Toggle whether premature client disconnect tracebacks ought to be
logged.

Default is 'no'.""",
    )
    parser.add_argument(
        "--expose-tracebacks",
        action=BooleanOptionalAction,
        help="""Toggle whether to expose tracebacks of unhandled exceptions to the
client.

Default is 'no'.""",
    )

    args = parser.parse_args(argv)

    """Command line runner."""

    # set a default level for the logger only if it hasn't been set explicitly
    # note that this level does not override any parent logger levels,
    # handlers, etc but without it no log messages are emitted by default
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

    try:
        module, obj_name = match(args.app)
        del args.app
    except ValueError as exc:
        print(exc, file=sys.stderr)
        parser.print_help(file=sys.stderr)
        show_exception(sys.stderr)
        return 1

    # Add the current directory onto sys.path
    sys.path.append(os.getcwd())

    # Get the WSGI function.
    try:
        app = resolve(module, obj_name)
    except ImportError:
        print(f"Bad module {module!r}", file=sys.stderr)
        parser.print_help(file=sys.stderr)
        show_exception(sys.stderr)
        return 1
    except AttributeError:
        print(f"Bad object name {obj_name!r}", file=sys.stderr)
        parser.print_help(file=sys.stderr)
        show_exception(sys.stderr)
        return 1
    if args.call:
        app = app()
    del args.call

    from pprint import pprint as pp; pp(vars(args))
    opts = {k: v for k, v in vars(args).items() if v is not None}
    _validate_opts(opts)
    _serve(app, opts)

    return 0
