Differences from ``zope.server``
--------------------------------

- Has no non-stdlib dependencies.

- No support for non-WSGI servers (no FTP, plain-HTTP, etc); refactorings and
  slight interface changes as a result.  Non-WSGI-supporting code removed.

- Slight cleanup in the way application response headers are handled (no more
  "accumulated headers").

- Supports the HTTP 1.1 "expect/continue" mechanism (required by WSGI spec).

- Calls "close()" on the app_iter object returned by the WSGI application.

- Supports an explicit ``wsgi.url_scheme`` parameter for ease of deployment
  behind SSL proxies.

- Different adjustment defaults (less conservative).

- Python 3 compatible.

- More test coverage (unit tests added, functional tests refactored and more
  added).

- Supports convenience ``waitress.serve`` function (e.g. ``from waitress
  import serve; serve(app)`` and convenience ``server.run()`` function.

- Returns a "real" write method from start_response.

- Provides a getsockname method of the server FBO figuring out which port the
  server is listening on when it's bound to port 0.

- Warns when app_iter bytestream numbytes less than or greater than specified
  Content-Length.

- Set content-length header if len(app_iter) == 1 and none provided.

- Raise an exception if start_response isnt called before any body write.

- channel.write does not accept non-byte-sequences.

- Put maintenance check on server rather than channel to avoid a class of
  DOS.

- wsgi.multiprocess set (correctly) to False.

- Ensures header total can not exceed a maximum size.

- Ensures body total can not exceed a maximum size.

- Broken chunked encoding request bodies don't crash the server.

- Handles keepalive/pipelining properly (no out of order responses, no
  premature channel closes).

- Send a 500 error to the client when a task raises an uncaught exception
  (with optional traceback rendering via "expose_traceback" adjustment).

- Supports HTTP/1.1 chunked responses when application doesn't set a
  Content-Length header.

- Dont hang a thread up trying to send data to slow clients.

- Supports ``wsgi.file_wrapper`` protocol.
