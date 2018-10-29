.. _index:

========
Waitress
========

Waitress is meant to be a production-quality pure-Python WSGI server with
very acceptable performance.  It has no dependencies except ones which live
in the Python standard library.  It runs on CPython on Unix and Windows under
Python 2.7+ and Python 3.4+.  It is also known to run on PyPy 1.6.0 on UNIX.
It supports HTTP/1.0 and HTTP/1.1.


Extended Documentation
----------------------

.. toctree::
   :maxdepth: 1

   usage
   logging
   reverse-proxy
   design
   differences
   api
   arguments
   filewrapper
   runner
   socket-activation
   glossary

Change History
--------------

.. include:: ../CHANGES.txt
.. include:: ../HISTORY.txt

Known Issues
------------

- Does not support TLS natively. See :ref:`using-behind-a-reverse-proxy` for more information.

Support and Development
-----------------------

The `Pylons Project web site <https://pylonsproject.org/>`_ is the main online
source of Waitress support and development information.

To report bugs, use the `issue tracker
<https://github.com/Pylons/waitress/issues>`_.

If you've got questions that aren't answered by this documentation,
contact the `Pylons-discuss maillist
<https://groups.google.com/forum/#!forum/pylons-discuss>`_ or join the `#pyramid
IRC channel <https://webchat.freenode.net/?channels=pyramid>`_.

Browse and check out tagged and trunk versions of Waitress via
the `Waitress GitHub repository <https://github.com/Pylons/waitress/>`_.
To check out the trunk via ``git``, use this command:

.. code-block:: text

  git clone git@github.com:Pylons/waitress.git

To find out how to become a contributor to Waitress, please see the guidelines in `contributing.md <https://github.com/Pylons/waitress/blob/master/contributing.md>`_ and `How to Contribute Source Code and Documentation <https://pylonsproject.org/community-how-to-contribute.html>`_.

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
it's single-threaded and has not been audited for security issues.

At the time of this writing, some existing WSGI servers already claim wide
platform support and have serviceable test suites.  The CherryPy WSGI server,
for example, targets Python 2 and Python 3 and it can run on UNIX or Windows.
However, it is not distributed separately from its eponymous web framework,
and requiring a non-CherryPy web framework to depend on the CherryPy web
framework distribution simply for its server component is awkward.  The test
suite of the CherryPy server also depends on the CherryPy web framework, so
even if we forked its server component into a separate distribution, we would
have still needed to backfill for all of its tests.  The CherryPy team has
started work on `Cheroot <https://bitbucket.org/cherrypy/cheroot/src/default/>`_, which
should solve this problem, however.

Waitress is a fork of the WSGI-related components which existed in
``zope.server``.  ``zope.server`` had passable framework-independent test
coverage out of the box, and a good bit more coverage was added during the
fork.  ``zope.server`` has existed in one form or another since about 2001,
and has seen production usage since then, so Waitress is not exactly
"another" server, it's more a repackaging of an old one that was already
known to work fairly well.
