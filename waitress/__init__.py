from waitress.task import ThreadedTaskDispatcher
from waitress.server import WSGIHTTPServer
from waitress.adjustments import Adjustments

truthy = frozenset(('t', 'true', 'y', 'yes', 'on', '1'))

def asbool(s):
    """ Return the boolean value ``True`` if the case-lowered value of string
    input ``s`` is any of ``t``, ``true``, ``y``, ``on``, or ``1``, otherwise
    return the boolean value ``False``.  If ``s`` is the value ``None``,
    return ``False``.  If ``s`` is already one of the boolean values ``True``
    or ``False``, return it."""
    if s is None:
        return False
    if isinstance(s, bool):
        return s
    s = str(s).strip()
    return s.lower() in truthy

def serve(
        app,
        host='0.0.0.0',
        port=8080,
        threads=4,
        url_scheme='http',
        connection_limit=100,
        log_socket_errors=True,
        ident=None,
        verbose=True,
        server=WSGIHTTPServer,             # test shim
        dispatcher=ThreadedTaskDispatcher, # test shim
        ):
    port = int(port)
    threads = int(threads)
    task_dispatcher = dispatcher()
    task_dispatcher.set_thread_count(threads)
    adj = Adjustments()
    adj.url_scheme = url_scheme
    adj.connection_limit = int(connection_limit)
    adj.log_socket_errors = asbool(log_socket_errors)
    server = server(app, host, port, task_dispatcher, ident=ident, adj=adj)
    if verbose: # pragma: no cover
        print('serving on http://%s:%s' % (server.ip, server.port))
    server.run()

def serve_paste(
        app,
        global_conf,
        **kw
        ):
    serve(app, **kw)
    return 0

