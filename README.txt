This package contains generic base classes for channel-based servers, the
servers themselves and helper objects, such as tasks and requests.

============
WSGI Support
============

`zope.server`'s HTTP server comes with WSGI_ support.
``zope.server.http.wsgihttpserver.WSGIHTTPServer`` can act as a WSGI gateway.
There's also an entry point for PasteDeploy_ that lets you use zope.server's
WSGI gateway from a configuration file, e.g.::

  [server:main]
  use = egg:zope.server
  host = 127.0.0.1
  port = 8080

.. _WSGI: http://www.python.org/dev/peps/pep-0333/
.. _PasteDeploy: http://pythonpaste.org/deploy/
