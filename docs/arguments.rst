.. _arguments:

Arguments to ``waitress.serve``
-------------------------------

Here are the arguments you can pass to the `waitress.serve`` function or use
in :term:`PasteDeploy` configuration (interchangeably):

host
    hostname or IP address (string), default ``0.0.0.0``.

port
    TCP port (integer), default ``8080``

threads
    mumber of threads used to process application logic (integer), default
    ``4``

url_scheme
    default ``wsgi.url_scheme`` value (string), default ``http``

ident
    server identity (string) used in responses,  default ``waitress``

backlog
    backlog is the value waitress passes to pass to socket.listen()
    (integer), default ``1024``

recv_bytes
    recv_bytes is the argument waitress passes to socket.recv() (integer),
    default ``8192``

send_bytes
    send_bytes is the number of bytes to send to socket.send() (integer),
    default ``9000``.  Multiples of 9000 should avoid partly-filled packets,
    but don't set this larger than the TCP write buffer size.  In Linux,
    /proc/sys/net/ipv4/tcp_wmem controls the minimum, default, and maximum
    sizes of TCP write buffers.

outbuf_overflow
    A tempfile should be created if the pending output is larger than
    outbuf_overflow, which is measured in bytes. The default is 1MB
    (``104856``).  This is conservative.

inbuf_overflow
    A tempfile should be created if the pending input is larger than
    inbuf_overflow, which is measured in bytes. The default is 512K
    (``524288``).  This is conservative.

connection_limit
    Stop accepting new connections if too many are already active (integer).
    Default is ``1000``.

cleanup_interval
    Minimum seconds between cleaning up inactive channels (integer), default
    ``30``.

channel_timeout
    Maximum seconds to leave an inactive connection open (integer), default
    ``120``.

log_socket_errors 
    Boolean: turn off to not log premature client disconnects.  Default:
    ``True``.

max_request_header_size
    maximum number of bytes of all request headers combined (integer), 256K
    (``262144``) default)

max_request_body_size
    maximum number of bytes in request body (integer), 1GB (``1073741824``)
    default.

expose_tracebacks
    Boolean:  expose tracebacks of uncaught exceptions.  Default: ``False``.

