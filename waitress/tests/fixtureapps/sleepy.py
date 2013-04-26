import time

def app(environ, start_response):
    if environ['PATH_INFO'] == '/sleepy':
        time.sleep(2)
        body = b'sleepy returned'
    else:
        body = b'notsleepy returned'
    cl = str(len(body))
    start_response(
        '200 OK',
        [('Content-Length', cl), ('Content-Type', 'text/plain')]
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
    serve(app, _quiet=True, **kwargs)
