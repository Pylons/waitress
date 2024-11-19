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

from argparse import ArgumentParser, BooleanOptionalAction
import logging
import operator as op
import os
import os.path
import pathlib
import pkgutil
import sys
from urllib.parse import urlparse

from waitress import adjustments, serve
from waitress.utilities import logger

host_and_port = op.attrgetter("hostname", "port")


def _valid_socket(value):
    # NOTE: without dummy scheme, `urlparse` will not pick up netloc cerrectly
    res = urlparse(f"scheme://{value}")

    if not all(host_and_port(res)):
        raise ValueError("Not a valid host and port! Should HOST:PORT", value)

    return res.hostname, str(res.port)


def make_parser():
    parser = ArgumentParser()
    # Standard options
    parser.add_argument(
        "--call",
        action="store_true",
        help="Call the given object to get the WSGI application.",
    )
    listener = parser.add_mutually_exclusive_group(required=False)
    listener.add_argument(
        "--listen",
        action="append",
        type=_valid_socket,
        metavar="HOST:PORT",
        help="Tell waitress to listen on an ip port combination.",
    )
    listener.add_argument(
        "--unix-socket",
        type=pathlib.Path,
        help="""Path of Unix socket. If a socket path is specified, a
Unix domain socket is made instead of the usual inet domain socket.

Not available on Windows.""",
    )
    listener.add_argument(
        "--host",
        type=str,
        default=adjustments.Adjustments.host,
        help="""Hostname or IP address on which to listen.
Note: may not be used together with `--listen`.

Default is %(default)s, which means "all IP addresses on this host".""",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=adjustments.Adjustments.port,
        help="""TCP port on which to listen. Ignored if --listen or --unix-socket are used.

Default is %(default)s.""",
    )

    parser.add_argument(
        "--ipv4",
        action=BooleanOptionalAction,
        help="Toggle on/off IPv4 support.",
    )
    parser.add_argument(
        "--ipv6",
        action=BooleanOptionalAction,
        help="Toggle on/off IPv6 support.",
    )
    parser.add_argument(
        "--unix-socket-perms",
        type=adjustments.asoctal,
        default=oct(adjustments.Adjustments.unix_socket_perms),
        help="""Octal permissions to use for the Unix domain socket.
Default is %(default)s.""",
    )
    parser.add_argument(
        "--url-scheme",
        default=adjustments.Adjustments.url_scheme,
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
        default=adjustments.Adjustments.ident,
        help="""Server identity used in the 'Server' header in responses.
Default is %(default)r.""",
    )
    # Tuning options
    parser.add_argument(
        "--threads",
        type=int,
        default=adjustments.Adjustments.threads,
        help="""Number of threads used to process application logic.
Default is %(default)s.""",
    )
    parser.add_argument(
        "--backlog",
        type=int,
        default=adjustments.Adjustments.backlog,
        help="""Connection backlog for the server. Default is %(default)s.""",
    )
    parser.add_argument(
        "--recv-bytes",
        type=int,
        default=adjustments.Adjustments.recv_bytes,
        help="""Number of bytes to request when calling `socket.recv()`.
Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--send-bytes",
        type=int,
        default=adjustments.Adjustments.send_bytes,
        help="""Number of bytes to send to `socket.send()`.
Note: multiples of 9000 should avoid partly-filled TCP packets.

Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--outbuf-overflow",
        type=int,
        default=adjustments.Adjustments.outbuf_overflow,
        help="""A temporary file should be created if the pending output is larger
than this.

Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--outbuf-high-watermark",
        type=int,
        default=adjustments.Adjustments.outbuf_high_watermark,
        help="""The `app_iter` will pause when pending output is larger than
this value and will resume once enough data is written to the socket to fall
below this threshold.

Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--inbuf-overflow",
        type=int,
        default=adjustments.Adjustments.inbuf_overflow,
        help="""A temporary file should be created if the pending input is larger
than this.

Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--connection-limit",
        type=int,
        default=adjustments.Adjustments.connection_limit,
        help="""Stop creating new channels if too many are already active.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--cleanup-interval",
        type=int,
        default=adjustments.Adjustments.cleanup_interval,
        help="""Minimum seconds between cleaning up inactive channels.
See `--channel-timeout` option.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--channel-timeout",
        type=int,
        default=adjustments.Adjustments.channel_timeout,
        help="""Maximum number of seconds to leave inactive connections open.
'Inactive' is defined as 'has received no data from the client and has sent
no data to the client'.

Default is %(default)s.""",
    )
    parser.add_argument(
        "--max-request-header-size",
        type=int,
        default=adjustments.Adjustments.max_request_header_size,
        help="""Maximum size of all request headers combined.
Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--max-request-body-size",
        type=int,
        default=adjustments.Adjustments.max_request_body_size,
        help="""Maximum size of request body.
Default is %(default)s bytes.""",
    )
    parser.add_argument(
        "--asyncore-loop-timeout",
        type=int,
        default=adjustments.Adjustments.asyncore_loop_timeout,
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
        default=adjustments.Adjustments.channel_request_lookahead,
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

    # This hack is needed to support the use of a flag and the legacy
    # positional syntax.
    parser.add_argument(
        "--app",
        required=False,
        action="append",
        help="Specify WSGI application to run. Required, but can be given without the flag for backward compatibility.",
    )
    parser.add_argument(
        "app",
        nargs="?",
        action="append",
        metavar="APP",
        help="Legacy method for specifying the WSGI application to run.",
    )
    return parser


def run(argv=sys.argv, _serve=serve):
    """Command line runner."""
    parser = make_parser()
    args = parser.parse_args(argv[1:])

    # set a default level for the logger only if it hasn't been set explicitly
    # note that this level does not override any parent logger levels,
    # handlers, etc but without it no log messages are emitted by default
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

    # Add the current directory onto sys.path
    sys.path.append(os.getcwd())

    apps = list(filter(None, args.app))
    if len(apps) != 1:
        print("Error: Specify one and only one WSGI application", file=sys.stderr)
        parser.print_help(file=sys.stderr)
        return 1
    app_name = apps[0]
    del args.app

    # Get the WSGI function.
    try:
        app = pkgutil.resolve_name(app_name)
    except (ImportError, AttributeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        parser.print_help(file=sys.stderr)
        return 1
    if args.call:
        app = app()
    del args.call
    if args.listen:
        del args.port
        del args.host

    opts = {k: v for k, v in vars(args).items() if v is not None}
    _serve(app, **opts)

    return 0
