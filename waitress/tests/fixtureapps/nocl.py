def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in range(0, len(l), n):
        yield l[i:i+n]

def gen(body):
    for chunk in chunks(body, 10):
        yield chunk

def app(environ, start_response):
    cl = environ.get('CONTENT_LENGTH', None)
    if cl is not None:
        cl = int(cl)
    body = environ['wsgi.input'].read(cl)
    start_response(
        '200 OK',
        [('Content-Type', 'text/plain')]
        )
    if environ['PATH_INFO'] == '/list':
        return [body]
    if environ['PATH_INFO'] == '/list_lentwo':
        return [body[0:1], body[1:]]
    return gen(body)

if __name__ == '__main__':
    import logging
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    from waitress import serve
    serve(app, port=61523, _quiet=True, expose_tracebacks=True)
    
