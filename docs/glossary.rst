.. _glossary:

Glossary
========

.. glossary::
    :sorted:

    PasteDeploy
        A system for configuration of WSGI web components in declarative ``.ini`` format.
        See https://docs.pylonsproject.org/projects/pastedeploy/en/latest/.

    asyncore
        A Python standard library module for asynchronous communications.  See :mod:`asyncore`.

        .. versionchanged:: 1.2.0
            Waitress has now "vendored" ``asyncore`` into itself as ``waitress.wasyncore``.
            This is to cope with the eventuality that ``asyncore`` will be removed from the Python standard library in Python 3.8 or so.

    middleware
        *Middleware* is a :term:`WSGI` concept.
        It is a WSGI component that acts both as a server and an application.
        Interesting uses for middleware exist, such as caching, content-transport encoding, and other functions.
        See `WSGI.org <https://wsgi.readthedocs.io/en/latest/>`_ or `PyPI <https://pypi.org/search/?c=Topic+%3A%3A+Internet+%3A%3A+WWW%2FHTTP+%3A%3A+WSGI+%3A%3A+Middleware>`_ to find middleware for your application.

    WSGI
        `Web Server Gateway Interface <https://wsgi.readthedocs.io/en/latest/>`_.
        This is a Python standard for connecting web applications to web servers, similar to the concept of Java Servlets.
        Waitress requires that your application be served as a WSGI application.

    wasyncore
        .. versionchanged:: 1.2.0
            Waitress has now "vendored" :term:`asyncore` into itself as ``waitress.wasyncore``.
            This is to cope with the eventuality that ``asyncore`` will be removed from the Python standard library in Python 3.8 or so.
