# a WSGI app for testing

def test_app(environ, start_response):
    status = '200 OK'
    response_headers = [('Content-type', 'text/plain')]
    start_response(status, response_headers)
    return ["Hello world! zope.server is delivering WSGI v%s.%s using %s."
            % (environ['wsgi.version'] + (environ['wsgi.url_scheme'],))]

def test_app_factory(global_config, **local_config):
    return test_app
