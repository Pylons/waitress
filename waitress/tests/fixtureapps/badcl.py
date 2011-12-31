def app(environ, start_response):
    body = b'abcdefghi'
    cl = len(body)
    if environ['PATH_INFO'] == '/short_body':
        cl = len(body) +1
    if environ['PATH_INFO'] == '/long_body':
        cl = len(body) -1
    start_response(
        '200 OK',
        [('Content-Length', str(cl)), ('Content-Type', 'text/plain')]
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
    
