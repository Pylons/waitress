def app(environ, start_response):
    cl = environ.get('CONTENT_LENGTH', None)
    if cl is not None:
        cl = int(cl)
    body = environ['wsgi.input'].read(cl)
    cl = str(len(body))
    start_response(
        '200 OK',
        [('Content-Length', cl), ('Content-Type', 'text/plain')]
        )
    return [body]

if __name__ == '__main__':
    import logging
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    from waitress import serve
    serve(app, port=61523, _quiet=True)
    
    
