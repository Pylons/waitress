from waitress.server import WSGIServer

def serve(app, **kw):
    _server = kw.pop('_server', WSGIServer) # test shim
    _quiet = kw.pop('_quiet', False)
    server = _server(app, **kw)
    if not _quiet: # pragma: no cover
        print('serving on http://%s:%s' % (server.effective_host,
                                           server.effective_port))
    server.run()

def serve_paste(app, global_conf, **kw):
    serve(app, **kw)
    return 0

