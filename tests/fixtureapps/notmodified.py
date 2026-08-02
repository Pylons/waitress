def app(environ, start_response):  # pragma: no cover
    if environ["PATH_INFO"] == "/nocontent":
        start_response("204 No Content", [])
    else:
        start_response("304 Not Modified", [("ETag", '"abc"')])

    return [b""]
