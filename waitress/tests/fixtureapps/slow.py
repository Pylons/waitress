import time

def app(environ, start_response):
    path_info = environ['PATH_INFO']
    if path_info == '/slow':
        time.sleep(1)
        body = b'slow'
    else:
        body = b'quick'
    cl = str(len(body))
    start_response(
        '200 OK',
        [('Content-Length', cl), ('Content-Type', 'text/plain')])
    return [body]

if __name__ == '__main__':
    import logging
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    from waitress import serve
    serve(app, port=61523, _quiet=True, expose_tracebacks=True)
