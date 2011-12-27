from waitress.server import WSGIServer

def serve(app, _server=WSGIServer, **kw):
    # _server is a test shim
    server = _server(app, **kw)
    if server.adj.verbose: # pragma: no cover
        print('serving on http://%s:%s' % (server.effective_host,
                                           server.effective_port))
    server.run()

def serve_paste(app, global_conf, **kw):
    serve(app, **kw)
    return 0

