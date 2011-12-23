Introduction
------------

Waitress is a production-quality pure-Python WSGI server with very acceptable
performance that runs on Unix and Windows under Python 2.6+ and Python 3.2.
It runs on CPython and PyPy.  It depends only on the Python standard library
and has very good test coverage.  It is a fork of the WSGI-related components
which existed in ``zope.server``.

It is meant to be used as a dependency by web framework authors who require
broad platform support.  It's neither the fastest nor the fanciest WSGI
server available but it can help eliminate the N-by-M documentation burden
(e.g. production vs. deployment, Windows vs. Unix, Python 3 vs. Python 2,
PyPI vs. CPython) and resulting user confusion imposed by spotty platform
support of the current (2012-ish) crop of WSGI servers (and the inappropriate
dependency trees of servers which claim wide platform support).

It supports HTTP/1.0 and a subset of HTTP/1.1 (see "Known Issues" below).

Usage
-----

Here's normal usage of the server::

   from waitress import serve
   serve(wsgiapp, host='0.0.0.0', port=8080)

If you want to serve your application on all IP addresses, on port 8080, you
need just call ``serve`` with the WSGI app as a single argument::

   from waitress import serve
   serve(wsgiapp)

Press Ctrl-C to exit the server.

There's an entry point for PasteDeploy_ (``egg:waitress#main``) that lets you
use waitress's WSGI gateway from a configuration file, e.g.::

  [server:main]
  use = egg:waitress#main
  host = 127.0.0.1
  port = 8080

Using Behind a Reverse Proxy
----------------------------

To use waitress as a target for a reverse proxy to a WSGI application that
generates URLs based on the value of the ``Host`` header sent by the client
and the value of the WSGI ``wsgi.url_scheme`` environment variable, use the
PasteDeploy_ PrefixMiddleware::

  from waitress import serve
  from paste.deploy.config import PrefixMiddleware
  app = PrefixMiddleware(app)
  serve(app)

Once you wrap your application in the the ``PrefixMiddleware``, the
middleware will notice certain headers sent from your proxy and will change
the ``wsgi.url_scheme`` and possibly other WSGI environment variables
appropriately.

You can wrap your application in the PrefixMiddleware declaratively in a
PasteDeploy_ configuration file too:

   [app:myapp]
   use = egg:mypackage#myapp

   [filter:paste_prefix]
   use = egg:PasteDeploy#prefix

   [pipeline:main]
   pipeline =
       paste_prefix
       myapp

  [server:main]
  use = egg:waitress#main
  host = 127.0.0.1
  port = 8080

You should instruct it to send along the original ``Host`` header from the
client to your waitress server, as well as sending along a
``X-Forwarded-Proto`` header with the appropriate value for
``wsgi.url_scheme``.  It's ofen nice to set an ``X-Forwarded-For`` header
too; the ``PrefixMiddleware`` uses this to adjust other environment
variables.

For example, when using Nginx as a reverse proxy, you might add the following
lines in a ``location`` section::

    proxy_set_header        Host $host;

If your proxy accepts HTTPS, and you want your application to generate HTTPS
urls, also set up your proxy to send a ``X-Forwarded-Proto`` with the value
``https`` along with each proxied request::

    proxy_set_header        X-Forwarded-Proto $scheme;

For the ``X-Forwarded-For`` header::

    proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;

Known Issues
------------

- The server returns a ``write`` callable from ``start_response`` which
  raises a ``NotImplementedError`` exception when called.  It does not
  support the write callable.

- This server claims to support HTTP/1.1 but does not implement the
  Expect/Continue protocol required by WSGI.

- This server does not support the ``wsgi.file_wrapper`` protocol.

.. _PasteDeploy: http://pythonpaste.org/deploy/
