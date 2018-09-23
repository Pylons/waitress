.. _access-logging:

==============
Access Logging
==============

The WSGI design is modular.  Waitress logs error conditions, debugging
output, etc., but not web traffic.  For web traffic logging, Paste
provides `TransLogger
<https://web.archive.org/web/20160707041338/http://pythonpaste.org/modules/translogger.html>`_
:term:`middleware`.  TransLogger produces logs in the `Apache Combined
Log Format <https://httpd.apache.org/docs/current/logs.html#combined>`_.


.. _logging-to-the-console-using-python:

Logging to the Console Using Python
-----------------------------------

``waitress.serve`` calls ``logging.basicConfig()`` to set up logging to the
console when the server starts up.  Assuming no other logging configuration
has already been done, this sets the logging default level to
``logging.WARNING``.  The Waitress logger will inherit the root logger's
level information (it logs at level ``WARNING`` or above).

Waitress sends its logging output (including application exception
renderings) to the Python logger object named ``waitress``.  You can
influence the logger level and output stream using the normal Python
``logging`` module API.  For example:

.. code-block:: python

   import logging
   logger = logging.getLogger('waitress')
   logger.setLevel(logging.INFO)

Within a PasteDeploy configuration file, you can use the normal Python
``logging`` module ``.ini`` file format to change similar Waitress logging
options.  For example:

.. code-block:: ini

   [logger_waitress]
   level = INFO


.. _logging-to-the-console-using-pastedeploy:

Logging to the Console Using PasteDeploy
----------------------------------------

TransLogger will automatically setup a logging handler to the console when called with no arguments.
It "just works" in environments that don't configure logging.
This is by virtue of its default configuration setting of ``setup_console_handler = True``.


.. TODO:
.. .. _logging-to-a-file-using-python:

.. Logging to a File Using Python
.. ------------------------------

.. Show how to configure the WSGI logger via python.


.. _logging-to-a-file-using-pastedeploy:

Logging to a File Using PasteDeploy
------------------------------------

TransLogger does not write to files, and the Python logging system
must be configured to do this.  The Python class :class:`FileHandler`
logging handler can be used alongside TransLogger to create an
``access.log`` file similar to Apache's.

Like any standard :term:`middleware` with a Paste entry point,
TransLogger can be configured to wrap your application using ``.ini``
file syntax.  First add a
``[filter:translogger]`` section, then use a ``[pipeline:main]``
section file to form a WSGI pipeline with both the translogger and
your application in it.  For instance, if you have this:

.. code-block:: ini

   [app:wsgiapp]
   use = egg:mypackage#wsgiapp

   [server:main]
   use = egg:waitress#main
   host = 127.0.0.1
   port = 8080

Add this:

.. code-block:: ini

   [filter:translogger]
   use = egg:Paste#translogger
   setup_console_handler = False

   [pipeline:main]
   pipeline = translogger
              wsgiapp

Using PasteDeploy this way to form and serve a pipeline is equivalent to
wrapping your app in a TransLogger instance via the bottom of the ``main``
function of your project's ``__init__`` file:

.. code-block:: python

    from mypackage import wsgiapp
    from waitress import serve
    from paste.translogger import TransLogger
    serve(TransLogger(wsgiapp, setup_console_handler=False))

.. note::
    TransLogger will automatically set up a logging handler to the console when
    called with no arguments, so it "just works" in environments that don't
    configure logging. Since our logging handlers are configured, we disable
    the automation via ``setup_console_handler = False``.

With the filter in place, TransLogger's logger (named the ``wsgi`` logger) will
propagate its log messages to the parent logger (the root logger), sending
its output to the console when we request a page:

.. code-block:: text

    00:50:53,694 INFO [wsgiapp] Returning: Hello World!
                      (content-type: text/plain)
    00:50:53,695 INFO [wsgi] 192.168.1.111 - - [11/Aug/2011:20:09:33 -0700] "GET /hello
    HTTP/1.1" 404 - "-"
    "Mozilla/5.0 (Macintosh; U; Intel Mac OS X; en-US; rv:1.8.1.6) Gecko/20070725
    Firefox/2.0.0.6"

To direct TransLogger to an ``access.log`` FileHandler, we need the
following to add a FileHandler (named ``accesslog``) to the list of
handlers, and ensure that the ``wsgi`` logger is configured and uses
this handler accordingly:

.. code-block:: ini

    # Begin logging configuration

    [loggers]
    keys = root, wsgiapp, wsgi

    [handlers]
    keys = console, accesslog

    [logger_wsgi]
    level = INFO
    handlers = accesslog
    qualname = wsgi
    propagate = 0

    [handler_accesslog]
    class = FileHandler
    args = ('%(here)s/access.log','a')
    level = INFO
    formatter = generic

As mentioned above, non-root loggers by default propagate their log records
to the root logger's handlers (currently the console handler). Setting
``propagate`` to ``0`` (``False``) here disables this; so the ``wsgi`` logger
directs its records only to the ``accesslog`` handler.

Finally, there's no need to use the ``generic`` formatter with
TransLogger, as TransLogger itself provides all the information we
need. We'll use a formatter that passes-through the log messages as
is. Add a new formatter called ``accesslog`` by including the
following in your configuration file:

.. code-block:: ini

    [formatters]
    keys = generic, accesslog

    [formatter_accesslog]
    format = %(message)s

Finally alter the existing configuration to wire this new
``accesslog`` formatter into the FileHandler:

.. code-block:: ini

    [handler_accesslog]
    class = FileHandler
    args = ('%(here)s/access.log','a')
    level = INFO
    formatter = accesslog
