.. _arguments:

Arguments to ``waitress.serve``
-------------------------------

Here are the arguments you can pass to the `waitress.serve`` function or use
in :term:`PasteDeploy` configuration (interchangeably):

host
    hostname or IP address (string) on which to listen, default ``0.0.0.0``,
    which means "all IP addresses on this host".

port
    TCP port (integer) on which to listen, default ``8080``

threads
    mumber of threads used to process application logic (integer), default
    ``4``

url_scheme
    default ``wsgi.url_scheme`` value (string), default ``http``

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
    default ``9000``.  Multiples of 9000 should avoid partly-filled TCP
    packets, but don't set this larger than the TCP write buffer size.  In
    Linux, /proc/sys/net/ipv4/tcp_wmem controls the minimum, default, and
    maximum sizes of TCP write buffers.

outbuf_overflow
    A tempfile should be created if the pending output is larger than
    outbuf_overflow, which is measured in bytes. The default is 1MB
    (``104856``).  This is conservative.

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

