import os

here = os.path.dirname(os.path.abspath(__file__))
fn = os.path.join(here, 'groundhog1.jpg')

class KindaFilelike(object):
    def __init__(self, bytes):
        self.bytes = bytes

    def read(self, n):
        bytes = self.bytes[:n]
        self.bytes = self.bytes[n:]
        return bytes

def app(environ, start_response):
    if environ['PATH_INFO'].startswith('/filelike'):
        f = open(fn, 'rb')
        f.seek(0, 2)
        cl = f.tell()
        f.seek(0)
        if environ['PATH_INFO'] == '/filelike':
            headers = [
                ('Content-Length', str(cl)), ('Content-Type', 'image/jpeg')
                ]
        else:
            headers = [('Content-Type', 'image/jpeg')]
    else:
        data = open(fn, 'rb').read()
        f = KindaFilelike(data)
        if environ['PATH_INFO'] == '/notfilelike':
            headers =  [('Content-Length', str(len(data))),
                        ('Content-Type', 'image/jpeg')]
            
        else:
            headers = [('Content-Type', 'image/jpeg')]

    start_response(
        '200 OK',
        headers
        )
    return environ['wsgi.file_wrapper'](f, 8192)

if __name__ == '__main__':
    import logging
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    from waitress import serve
    serve(app, port=61523, _quiet=True)
    
