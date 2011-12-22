Introduction
------------

This package is a production quality WSGI server with acceptable performance
that runs on Unix and Windows under Python 2.6+ and Python 3.2.

Using
-----

Here's normal usage of the server::

   from waitress import serve
   serve(wsgiapp, host='0.0.0.0', port=8080)

Press Ctrl-C to exit the server.

There's an entry point for PasteDeploy_ that lets you use waitress's WSGI
gateway from a configuration file, e.g.::

  [server:main]
  use = egg:waitress
  host = 127.0.0.1
  port = 8080

.. _PasteDeploy: http://pythonpaste.org/deploy/
