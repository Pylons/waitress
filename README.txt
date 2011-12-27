Introduction
------------

Waitress is meant to be a production-quality pure-Python WSGI server with
very acceptable performance.  It has no dependencies except ones which live
in the Python standard library.  It runs on CPython on Unix and Windows under
Python 2.6+ and Python 3.2.  It is also known to run on PyPy 1.6.0 on UNIX.
It supports HTTP/1.0 and HTTP/1.1.

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
PyPy vs. CPython) and resulting user confusion imposed by spotty platform
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
and requiring a non-CherryPy web framework to depend on the CherryPy web
framework distribution simply for its server component is awkward.  The test
suite of the CherryPy server also depends on the CherryPy web framework, so
even if we forked its server component into a separate distribution, we would
have still needed to backfill for all of its tests.

Finally, I wanted the control that is provided by maintaining my own server.
A WSGI server is an important dependency of my web framework, and being able
to make arbitrary changes (add features, fix bugs, etc) without anyone else's
permission is nice.

Waitress is a fork of the WSGI-related components which existed in
``zope.server``.  ``zope.server`` had passable framework-independent test
coverage out of the box, and a good bit more coverage was added during the
fork.  ``zope.server`` has existed in one form or another since about 2001,
and has seen production usage since then, so Waitress is not exactly
"another" server, it's more a repackaging of an old one that was already
known to work fairly well.

Known Issues
------------

- The server does not support the ``wsgi.file_wrapper`` protocol.

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
  import serve; serve(app)`` and convenience ``server.serve()`` function.

- Returns a "real" write method from start_response.

- Provides a getsockname method of the server FBO figuring out which port the
  server is listening on when it's bound to port 0.

- Warns when app_iter bytestream numbytes less than or greater than specified
  Content-Length.

- Set content-length header if len(app_iter) == 1 and none provided.

- Raise an exception if start_response isnt called before any body write.

- channel.write does not accept non-byte-sequences.

.. _PasteDeploy: http://pythonpaste.org/deploy/

