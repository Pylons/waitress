.. _runner:

waitress-serve
--------------

Waitress comes bundled with a thin command-line wrapper around the
``waitress.serve`` function called ``waitress-serve``. This is useful for
development, and in production situations where serving of static assets is
delegated to a reverse proxy, such as Nginx or Apache.

.. note::

   This feature is new as of Waitress 0.8.4.

``waitress-serve`` takes the very same :ref:`arguments <arguments>` as the
``waitress.serve`` function, but where the function's arguments have
underscores, ``waitress-serve`` uses hyphens. Thus::

    import myapp

    waitress.serve(myapp.wsgifunc, port=8041, url_scheme='https')

Is equivalent to::

    waitress-serve --port=8041 --url-scheme=https myapp:wsgifunc

The full argument list is :ref:`given below <invocation>`.

Boolean arguments are represented by flags. If you wish to explicitly set a
flag, simply use it by its name. Thus the flag::

    --expose-tracebacks

Is equivalent to passing ``expose_tracebacks=True`` to ``waitress.serve``.

All flags have a negative equivalent. These are prefixed with ``no-``; thus
using the flag::

    --no-expose-tracebacks

Is equivalent to passing ``expose_tracebacks=False`` to ``waitress.serve``.

If at any time you want the full argument list, use the ``--help`` flag.

Applications are specified similarly to PasteDeploy, where the format is
``myapp.mymodule:wsgifunc``. As some application frameworks use application
objects, you can use dots to resolve attributes like so:
``myapp.mymodule:appobj.wsgifunc``.

A number of frameworks, *web.py* being an example, have factory methods on
their application objects that return usable WSGI functions when called. For
cases like these, ``waitress-serve`` has the ``--call`` flag. Thus::

    waitress-serve --call myapp.mymodule.app.wsgi_factory

Would load the ``myapp.mymodule`` module, and call ``app.wsgi_factory`` to get
a WSGI application function to be passed to ``waitress.server``.

.. note::

   As of 0.8.6, the current directory is automatically included on
   ``sys.path``.

.. _invocation:

Invocation
~~~~~~~~~~

Usage::

    waitress-serve [OPTS] MODULE:OBJECT

Common options:

``--help``
    Show this information.

``--call``
    Call the given object to get the WSGI application.

``--host=ADDR``
    Hostname or IP address on which to listen, default is '0.0.0.0',
    which means "all IP addresses on this host".

``--port=PORT``
    TCP port on which to listen, default is '8080'

``--listen=host:port``
    Tell waitress to listen on an ip port combination.

    Example:

        --listen=127.0.0.1:8080
        --listen=[::1]:8080
        --listen=*:8080

    This option may be used multiple times to listen on multipe sockets.
    A wildcard for the hostname is also supported and will bind to both
    IPv4/IPv6 depending on whether they are enabled or disabled.

``--[no-]ipv4``
    Toggle on/off IPv4 support.

    This affects wildcard matching when listening on a wildcard address/port
    combination.

``--[no-]ipv6``
    Toggle on/off IPv6 support.

    This affects wildcard matching when listening on a wildcard address/port
    combination.

``--unix-socket=PATH``
    Path of Unix socket. If a socket path is specified, a Unix domain
    socket is made instead of the usual inet domain socket.

    Not available on Windows.

``--unix-socket-perms=PERMS``
    Octal permissions to use for the Unix domain socket, default is
    '600'.

``--url-scheme=STR``
    Default ``wsgi.url_scheme`` value, default is 'http'.

``--url-prefix=STR``
    The ``SCRIPT_NAME`` WSGI environment value.  Setting this to anything
    except the empty string will cause the WSGI ``SCRIPT_NAME`` value to be the
    value passed minus any trailing slashes you add, and it will cause the
    ``PATH_INFO`` of any request which is prefixed with this value to be
    stripped of the prefix.  Default is the empty string.

``--ident=STR``
    Server identity used in the 'Server' header in responses. Default
    is 'waitress'.

Tuning options:

``--threads=INT``
    Number of threads used to process application logic, default is 4.

``--backlog=INT``
    Connection backlog for the server. Default is 1024.

``--recv-bytes=INT``
    Number of bytes to request when calling ``socket.recv()``. Default is
    8192.

``--send-bytes=INT``
    Number of bytes to send to socket.send(). Default is 18000.
    Multiples of 9000 should avoid partly-filled TCP packets.

``--outbuf-overflow=INT``
    A temporary file should be created if the pending output is larger than
    this. Default is 1048576 (1MB).

``--inbuf-overflow=INT``
    A temporary file should be created if the pending input is larger than
    this. Default is 524288 (512KB).

``--connection-limit=INT``
    Stop creating new channelse if too many are already active.  Default is
    100.

``--cleanup-interval=INT``
    Minimum seconds between cleaning up inactive channels. Default is 30. See
    ``--channel-timeout``.

``--channel-timeout=INT``
    Maximum number of seconds to leave inactive connections open.  Default is
    120. 'Inactive' is defined as 'has recieved no data from the client and has
    sent no data to the client'.

``--[no-]log-socket-errors``
    Toggle whether premature client disconnect tracepacks ought to be logged.
    On by default.

``--max-request-header-size=INT``
    Maximum size of all request headers combined. Default is 262144 (256KB).

``--max-request-body-size=INT``
    Maximum size of request body. Default is 1073741824 (1GB).

``--[no-]expose-tracebacks``
    Toggle whether to expose tracebacks of unhandled exceptions to the client.
    Off by default.

``--asyncore-loop-timeout=INT``
    The timeout value in seconds passed to ``asyncore.loop()``. Default is 1.

``--asyncore-use-poll``
    The use_poll argument passed to ``asyncore.loop()``. Helps overcome open
    file descriptors limit. Default is False.
