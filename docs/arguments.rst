.. _arguments:

Arguments to ``waitress.serve``
-------------------------------

Here are the arguments you can pass to the `waitress.serve`` function or use
in :term:`PasteDeploy` configuration (interchangeably):

host
    hostname or IP address (string) on which to listen, default ``0.0.0.0``,
    which means "all IP addresses on this host".

    .. warning::
        May not be used with ``listen``

port
    TCP port (integer) on which to listen, default ``8080``

    .. warning::
        May not be used with ``listen``

listen
    .. versionadded:: 1.0
        Tell waitress to listen on combinations of ``host:port`` arguments.
        Combinations should be a quoted, space-delimited list, as in the following examples.

        .. code-block:: python

            listen="127.0.0.1:8080 [::1]:8080"
            listen="*:8080 *:6543"

        A wildcard for the hostname is also supported and will bind to both
        IPv4/IPv6 depending on whether they are enabled or disabled.

        IPv6 IP addresses are supported by surrounding the IP address with brackets.

ipv4
    Enable or disable IPv4 (boolean)

ipv6
    Enable or disable IPv6 (boolean)

unix_socket
    Path of Unix socket (string), default is ``None``. If a socket path is
    specified, a Unix domain socket is made instead of the usual inet domain
    socket.

    Not available on Windows.

unix_socket_perms
    Octal permissions to use for the Unix domain socket (string), default is
    ``600``. Only used if ``unix_socket`` is not ``None``.

sockets
    .. versionadded:: 1.1.1
        A list of sockets. The sockets can be either Internet or UNIX sockets and have
        to be bound. Internet and UNIX sockets cannot be mixed.
        If the socket list is not empty, waitress creates one server for each socket.
        Default is ``[]``.

        .. warning::
            May not be used with ``listen``, ``host``, ``port`` or ``unix_socket``

threads
    number of threads used to process application logic (integer), default
    ``4``

trusted_proxy
    IP address of a remote peer allowed to override various WSGI environment
    variables using proxy headers.

    For unix sockets, set this value to ``localhost`` instead of an IP address

    default ``None``

trusted_proxy_count
    How many proxies we trust when chained
    
    X-Forwarded-For: 192.0.2.1, "[2001:db8::1]"
    
    or
   
    Forwarded: for=192.0.2.1, For="[2001:db8::1]"
    
    means there were (potentially), two proxies involved. If we know there is
    only 1 valid proxy, then that initial IP address "192.0.2.1" is not trusted
    and we completely ignore it.
    
    If there are two trusted proxies in the path, this value should be set to
    2. If there are more proxies, this value should be set higher.

    default ``1``

    .. versionadded:: 1.2.0

trusted_proxy_headers
    Which of the proxy headers should we trust, this is a set where you
    either specify forwarded or one or more of x-forwarded-host, x-forwarded-for,
    x-forwarded-proto, x-forwarded-port.

    This list of trusted headers is used when ``trusted_proxy`` is set and will
    allow waitress to modify the WSGI environment using the values provided by
    the proxy.

    .. versionadded:: 1.2.0
       If ``trusted_proxy`` is set, the default is ``x-forwarded-proto`` to
       match older versions of Waitress. Users should explicitly opt-in by
       selecting the headers to be trusted as future versions of waitress will
       use an empty default.

    .. warning::
       It is an error to set this value without setting ``trusted_proxy``

log_untrusted_proxy_headers
    Should waitress log warning messages about proxy headers that are being
    sent from upstream that are not trusted by ``trusted_proxy_headers`` but
    are being cleared due to ``clear_untrusted_proxy_headers``?

    This may be useful for debugging if you expect your upstream proxy server
    to only send specific headers.

    default ``False``
   
    .. versionadded:: 1.2.0

    .. warning::
       It is a no-op to set this value without also setting
       ``clear_untrusted_proxy_headers`` and ``trusted_proxy``

clear_untrusted_proxy_headers
   This tells Waitress to remove any untrusted proxy headers ("Forwarded",
   "X-Forwared-For", "X-Forwarded-By", "X-Forwarded-Host", "X-Forwarded-Port",
   "X-Forwarded-Proto") not explicitly allowed by ``trusted_proxy_headers``

   default ``False``

   .. versionadded: 1.2.0
      The default value is set to ``False`` for backwards compatibility. In
      future versions of Waitress this default will be changed to ``True``.
      Warnings will be raised unless the user explicitly provides a value for
      this option, allowing the user to opt-in to the new safety features
      automatically.

   .. warning::
      It is an error to set this value without setting ``trusted_proxy``

url_scheme
    default ``wsgi.url_scheme`` value (string), default ``http``;  can be
    overridden per-request by the value of the ``X_FORWARDED_PROTO`` header,
    but only if the client address matches ``trusted_proxy``.

ident
    server identity (string) used in "Server:" header in responses, default
    ``waitress``

backlog
    backlog is the value waitress passes to pass to socket.listen()
    (integer), default ``1024``.  This is the maximum number of incoming TCP
    connections that will wait in an OS queue for an available channel.  From
    listen(1): "If a connection request arrives when the queue is full, the
    client may receive an error with an indication of ECONNREFUSED or, if the
    underlying protocol supports retransmission, the request may be ignored
    so that a later reattempt at connection succeeds."

recv_bytes
    recv_bytes is the argument waitress passes to socket.recv() (integer),
    default ``8192``

send_bytes
    send_bytes is the number of bytes to send to socket.send() (integer),
    default ``18000``.  Multiples of 9000 should avoid partly-filled TCP
    packets, but don't set this larger than the TCP write buffer size.  In
    Linux, /proc/sys/net/ipv4/tcp_wmem controls the minimum, default, and
    maximum sizes of TCP write buffers.

outbuf_overflow
    A tempfile should be created if the pending output is larger than
    outbuf_overflow, which is measured in bytes. The default is 1MB
    (``1048576``).  This is conservative.

inbuf_overflow
    A tempfile should be created if the pending input is larger than
    inbuf_overflow, which is measured in bytes. The default is 512K
    (``524288``).  This is conservative.

connection_limit
    Stop creating new channels if too many are already active (integer).
    Default is ``100``.  Each channel consumes at least one file descriptor,
    and, depending on the input and output body sizes, potentially up to
    three, plus whatever file descriptors your application logic happens to
    open.  The default is conservative, but you may need to increase the
    number of file descriptors available to the Waitress process on most
    platforms in order to safely change it (see ``ulimit -a`` "open files"
    setting).  Note that this doesn't control the maximum number of TCP
    connections that can be waiting for processing; the ``backlog`` argument
    controls that.

cleanup_interval
    Minimum seconds between cleaning up inactive channels (integer), default
    ``30``.  See "channel_timeout".

channel_timeout
    Maximum seconds to leave an inactive connection open (integer), default
    ``120``.  "Inactive" is defined as "has received no data from a client
    and has sent no data to a client".

log_socket_errors
    Boolean: turn off to not log premature client disconnect tracebacks.
    Default: ``True``.

max_request_header_size
    maximum number of bytes of all request headers combined (integer), 256K
    (``262144``) default)

max_request_body_size
    maximum number of bytes in request body (integer), 1GB (``1073741824``)
    default.

expose_tracebacks
    Boolean: expose tracebacks of unhandled exceptions to client.  Default:
    ``False``.

asyncore_loop_timeout
    .. versionadded:: 0.8.3
        The ``timeout`` value (seconds) passed to ``asyncore.loop`` to run the mainloop.
        Default: 1.

asyncore_use_poll
    .. versionadded:: 0.8.6
        Boolean: switch from using ``select()`` to ``poll()`` in ``asyncore.loop``.
        By default ``asyncore.loop()`` uses ``select()`` which has a limit of 1024 file descriptors.
        ``select()`` and ``poll()`` provide basically the same functionality, but ``poll()`` doesn't have the file descriptors limit.
        Default: False.

url_prefix
    String: the value used as the WSGI ``SCRIPT_NAME`` value.  Setting this to
    anything except the empty string will cause the WSGI ``SCRIPT_NAME`` value
    to be the value passed minus any trailing slashes you add, and it will
    cause the ``PATH_INFO`` of any request which is prefixed with this value to
    be stripped of the prefix.  Default: the empty string.
