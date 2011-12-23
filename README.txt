Introduction
------------

Waitress is meant to be a production-quality pure-Python WSGI server with
very acceptable performance.  It has no dependencies except ones which live
in the Python standard library.  It runs on CPython on Unix and Windows under
Python 2.6+ and Python 3.2.  It is also known to run on PyPy 1.6.0 on UNIX.
It supports HTTP/1.0 and a subset of HTTP/1.1; see "Known Issues" below for
HTTP/1.1 caveats.

Usage
-----

Here's normal usage of the server::

   from waitress import serve
   serve(wsgiapp, host='0.0.0.0', port=8080)

If you want to serve your application on all IP addresses, on port 8080, you
can omit the ``host`` and ``port`` arguments and just call ``serve`` with the
WSGI app as a single argument::

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
PasteDeploy_ configuration file too::

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

You should instruct your proxy server to send along the original ``Host``
header from the client to your waitress server, as well as sending along a
``X-Forwarded-Proto`` header with the appropriate value for
``wsgi.url_scheme``.  It's ofen nice to set an ``X-Forwarded-For`` header
too; the ``PrefixMiddleware`` uses this to adjust other environment
variables (you'll have to read its docs to find out which ones).

For example, when using Nginx as a reverse proxy, you might add the following
lines in a ``location`` section::

    proxy_set_header        Host $host;

If your proxy accepts HTTPS, and you want your application to generate HTTPS
urls, also set up your proxy to send a ``X-Forwarded-Proto`` with the value
``https`` along with each proxied request::

    proxy_set_header        X-Forwarded-Proto $scheme;

For the ``X-Forwarded-For`` header::

    proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;

Why?
----

At the time of the release of Waitress, there are already many pure-Python
WSGI servers.  Why would we need another?

Waitress is meant to be useful to web framework authors who require broad
platform support.  It's neither the fastest nor the fanciest WSGI server
available but using it helps eliminate the N-by-M documentation burden
(e.g. production vs. deployment, Windows vs. Unix, Python 3 vs. Python 2,
PyPI vs. CPython) and resulting user confusion imposed by spotty platform
support of the current (2012-ish) crop of WSGI servers.  For example,
``gunicorn`` is great, but doesn't run on Windows.  ``paste.httpserver`` is
perfectly serviceable, but doesn't run under Python 3 and has no dedicated
tests suite that would allow someone who did a Python 3 port to know it
worked after a port was completed.  ``wsgiref`` works fine under most any
Python, but it's a little slow and it's not recommended for production use as
it has not been audited for security issues.

At the time of this writing, some existing WSGI servers already claim wide
platform support and have serviceable test suites.  The CherryPy WSGI server,
for example, targets Python 2 and Python 3 and it can run on UNIX or Windows.
However, it is not distributed separately from its eponymous web framework,
and asking a non-CherryPy web framework to depend on the CherryPy web
framework distribution simply for its server component is awkward.  The test
suite of the CherryPy server also depends on the CherryPy web framework, so
even if we forked its server component into a separate distribution, we would
have still needed to backfill for all of its tests.

Waitress is a fork of the WSGI-related components which existed in
``zope.server``.  ``zope.server`` had passable framework-independent test
coverage out of the box, anda good bit more coverage was added during the
fork.  ``zope.server`` has existed in one form or another since about 2001,
and has seen production usage since then, so Waitress is not exactly
"another" server, it's more a repackaging of an old one that was already
known to work fairly well.

Finally, I wanted some control.  I am a web framework author.  A WSGI server
is an important dependency of my web framework, and being able to make
arbitrary changes to one is important to me, especially as we transition from
Python 2 to Python 3 over the next few years.

Known Issues
------------

- The server returns a ``write`` callable from ``start_response`` which
  raises a ``NotImplementedError`` exception when called.  It does not
  support the write callable.

- This server claims to support HTTP/1.1 but does not implement the
  Expect/Continue protocol required by WSGI.

- This server does not support the ``wsgi.file_wrapper`` protocol.

.. _PasteDeploy: http://pythonpaste.org/deploy/
