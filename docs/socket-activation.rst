Socket Activation
-----------------

While waitress does not support the various implementations of socket activation,
e.g. using systemd or launchd, it is prepared to receive pre-bound applications
from an init system.

The following shows a code example starting waitress with three different,
pre-bound sockets.

.. code-block:: python

    import socket
    import waitress


    def app(environ, start_response):
        content_length = environ.get('CONTENT_LENGTH', None)
        if content_length is not None:
            content_length = int(content_length)
        body = environ['wsgi.input'].read(content_length)
        content_length = str(len(body))
        start_response(
            '200 OK',
            [('Content-Length', content_length), ('Content-Type', 'text/plain')]
        )
        return [body]


    if __name__ == '__main__':
        sockets = [
            socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)]
        sockets[0].bind(('127.0.0.1', 8080))
        sockets[1].bind(('127.0.0.1', 9090))
        sockets[2].bind('./test_socket')
        waitress.serve(app, sockets=sockets)
        for socket in sockets:
            socket.close()

Generally, to implement socket activation for a given init system, a wrapper
script uses the init system specific libraries to retrieve the sockets from
the init system and the starts waitress passing the sockets using the parameter
``sockets``. Note that the sockets have to be bound, which all init systems
supporting socket activation do.

