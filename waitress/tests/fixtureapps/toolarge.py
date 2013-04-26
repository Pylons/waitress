def app(environ, start_response):
    body = b'abcdef'
    cl = len(body)
    start_response(
        '200 OK',
        [('Content-Length', str(cl)), ('Content-Type', 'text/plain')]
        )
    return [body]

if __name__ == '__main__':
    import logging
    import sys
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    from waitress import serve
    if len(sys.argv) > 1 and sys.argv[1] == '-u':
        kwargs = {'unix_socket': '/tmp/waitress.functional.sock'}
    else:
        kwargs = {'port': 61523}
    serve(app, _quiet=True, max_request_header_size=1000,
          max_request_body_size=1000, **kwargs)
