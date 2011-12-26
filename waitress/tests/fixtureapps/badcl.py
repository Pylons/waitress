def app(environ, start_response):
    body = 'abcdefghi'
    cl = len(body)
    if environ['PATH_INFO'] == '/short':
        cl = len(body) - 1
    if environ['PATH_INFO'] == '/long':
        cl = len(body) + 1
    start_response(
        '200 OK',
        [('Content-Length', str(cl)), ('Content-Type', 'text/plain')]
        )
    return [body]

if __name__ == '__main__':
    from waitress import serve
    serve(app, port=61523, verbose=False)
    
