Design
------

Waitress uses a combination of asynchronous and synchronous code to do its
job.  It handles I/O to and from clients using the :term:`asyncore` library.
It services requests via threads.

The :term:`asyncore` module in the Python standard library:

- Uses the ``select.select`` function to wait for connections from clients
  and determine if a connected client is ready to receive output.

- Creates a channel whenever a new connection is made to the server.

- Executes methods of a channel whenever it believes data can be read from or
  written to the channel.

A "channel" is created for each connection from a client to the server.  The
channel handles all requests over the same connection from that client.  A
channel will handle some number of requests during its lifetime: zero to how
ever many HTTP requests are sent to the server by the client over a single
connection.  For example, an HTTP/1.1 client may issue a theoretically
infinite number of requests over the same connection; each of these will be
handled by the same channel.  An HTTP/1.0 client without a "Connection:
keep-alive" header will request usually only one over a single TCP
connection, however, and when the request has completed, the client
disconnects and reconnects (which will create another channel).  When the
connection related to a channel is closed, the channel is destroyed and
garbage collected.

When a channel determines the client has sent at least one full valid HTTP
request, it schedules a "task" with a "thread dispatcher".  The thread
dispatcher maintains a fixed pool of worker threads available to do client
work (by default, 4 threads).  If a worker thread is available when a task is
scheduled, the worker thread runs the task.  The task has access to the
channel, and can write back to the channel's output buffer.  When all worker
threads are in use, scheduled tasks will wait in a queue for a worker thread
to become available.

I/O is always done asynchronously (by asyncore) in the main thread.  Worker
threads never do any I/O.  This means that 1) a large number of clients can
be connected to the server at once and 2) worker threads will never be hung
up trying to send data to a slow client.

No attempt is made to kill a "hung thread".  It's assumed that when a task
(application logic) starts that it will eventually complete.  If for some
reason WSGI application logic never completes and spins forever, the worker
thread related to that WSGI application will be consumed "forever", and if
enough worker threads are consumed like this, the server will stop responding
entirely.

Periodic maintenance is done by the main thread (the thread handling I/O).
If a channel hasn't sent or received any data in a while, the channel's
connection is closed, and the channel is destroyed.
