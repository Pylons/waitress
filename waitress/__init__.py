import asyncore

from waitress.task import ThreadedTaskDispatcher
from waitress.server import WSGIHTTPServer

def serve(
        app,
        host='127.0.0.1',
        port=8080,
        threads=4,
        verbose=True,
        ident=None
        ):
    port = int(port)
    threads = int(threads)
    task_dispatcher = ThreadedTaskDispatcher()
    task_dispatcher.setThreadCount(threads)
    WSGIHTTPServer(app, host, port, task_dispatcher=task_dispatcher,
                   verbose=verbose, ident=ident)
    asyncore.loop()
    
def serve_paste(
        app,
        global_conf,
        host='127.0.0.1',
        port=8080,
        threads=4,
        verbose=True,
        ident=None,
        ):
    return serve(app, host=host, port=port, threads=threads, verbose=verbose,
                 ident=ident)

