import logging

def app(environ, start_response):
    cl = environ.get('CONTENT_LENGTH', None)
    if cl is not None:
        cl = int(cl)
    body = environ['wsgi.input'].read(cl)
    cl = str(len(body))
    if environ['PATH_INFO'] == '/before_start_response':
        raise ValueError('wrong')
    write = start_response(
        '200 OK',
        [('Content-Length', cl), ('Content-Type', 'text/plain')]
        )
    if environ['PATH_INFO'] == '/after_write_cb':
        write('abc')
    if environ['PATH_INFO'] == '/in_generator':
        def foo():
            yield 'abc'
            raise ValueError
        return foo()
    raise ValueError('wrong')

if __name__ == '__main__':
    from waitress import serve
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    serve(app, port=61523, _quiet=True, expose_tracebacks=True)
    
    
