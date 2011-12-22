Introduction
------------

This package is a production quality pure-Python WSGI server with very
acceptable performance that runs on Unix and Windows under Python 2.6+ and
Python 3.2.  It runs on CPython and PyPy.  It is meant to be used as a
dependency by web framework authors who require broad platform support.  It's
neither the fastest nor the fanciest WSGI server vailable but it can help
eliminate the N-by-M documentation burden (e.g. production vs. deployment,
Windows vs. Unix, Python 3 vs. Python 2, PyPI vs. CPython) and resulting user
confusion imposed by spotty platform support and/or inappropriate dependency
trees of the current (2012-ish) crop of WSGI servers.  It depends only on the
Python standard library and has very good test coverage.  It is a fork of the
WSGI-related components which existed in ``zope.server``.

Usage
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
