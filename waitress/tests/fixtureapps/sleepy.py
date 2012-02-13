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
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    from waitress import serve
    serve(app, port=61523, _quiet=True)
    
    
