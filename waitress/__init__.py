from waitress.task import ThreadedTaskDispatcher
from waitress.server import WSGIHTTPServer

def serve(
        app,
        host='0.0.0.0',
        port=8080,
        threads=4,
        ident=None,
        verbose=True,
        server=WSGIHTTPServer,             # test shim
        dispatcher=ThreadedTaskDispatcher, # test shim
        ):
    port = int(port)
    threads = int(threads)
    task_dispatcher = dispatcher()
    task_dispatcher.setThreadCount(threads)
    server = server(app, host, port, task_dispatcher, ident=ident)
    if verbose: # pragma: no cover
        print('serving on http://%s:%s' % (server.ip, server.port))
    server.run()

def serve_paste(
        app,
        global_conf,
        host='0.0.0.0',
        port=8080,
        threads=4,
        verbose=True,
        ident=None,
        server=WSGIHTTPServer,
        dispatcher=ThreadedTaskDispatcher, # test shim
        ):
    serve(app, host=host, port=port, threads=threads, verbose=verbose,
          ident=ident, server=server, dispatcher=dispatcher)
    return 0

