def app(environ, start_response):
    body = b'abcdef'
    cl = len(body)
    start_response(
        '200 OK',
        [('Content-Length', str(cl)), ('Content-Type', 'text/plain')]
    )
    return [body]

if __name__ == '__main__':
    from waitress.tests.support import start_server
    start_server(app, max_request_header_size=1000, max_request_body_size=1000)
