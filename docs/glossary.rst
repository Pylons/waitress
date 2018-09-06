.. _glossary:

Glossary
========

.. glossary::
   :sorted:

   PasteDeploy
      A system for configuration of WSGI web components in declarative
      ``.ini`` format.  See http://pythonpaste.org/deploy/.

   asyncore
      A standard library module for asynchronous communications.  See
      http://docs.python.org/library/asyncore.html .

   middleware
     *Middleware* is a :term:`WSGI` concept.  It is a WSGI component
     that acts both as a server and an application.  Interesting uses
     for middleware exist, such as caching, content-transport
     encoding, and other functions.  See `WSGI.org <http://www.wsgi.org>`_
     or `PyPI <http://python.org/pypi>`_ to find middleware for your
     application.

   WSGI
     `Web Server Gateway Interface <http://www.wsgi.org/>`_.  This is a
     Python standard for connecting web applications to web servers,
     similar to the concept of Java Servlets.  Waitress requires
     that your application be served as a WSGI application.
