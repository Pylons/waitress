def app(environ, start_response):
    body = b'abcdefghi'
    app_iter = [body]
    if environ['PATH_INFO'] == '/generator':
        def gen():
            yield body
        app_iter = gen()
    start_response('200 OK', [])
    return app_iter

if __name__ == '__main__':
    from waitress import serve
    serve(app, port=61523, _quiet=True)
    
