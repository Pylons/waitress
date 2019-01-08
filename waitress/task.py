##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################

import socket
import sys
import threading
import time

from .buffers import ReadOnlyFileBasedBuffer
from .compat import Empty, Queue, reraise, tobytes
from .utilities import (
    Forwarded,
    PROXY_HEADERS,
    build_http_date,
    clear_untrusted_headers,
    logger,
    queue_logger,
    undquote,
)

rename_headers = {  # or keep them without the HTTP_ prefix added
    'CONTENT_LENGTH': 'CONTENT_LENGTH',
    'CONTENT_TYPE': 'CONTENT_TYPE',
}

hop_by_hop = frozenset((
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade'
))


class JustTesting(Exception):
    pass

class ThreadedTaskDispatcher(object):
    """A Task Dispatcher that creates a thread for each task.
    """
    stop_count = 0 # Number of threads that will stop soon.
    logger = logger
    queue_logger = queue_logger

    def __init__(self):
        self.threads = {} # { thread number -> 1 }
        self.queue = Queue()
        self.thread_mgmt_lock = threading.Lock()

    def start_new_thread(self, target, args):
        t = threading.Thread(target=target, name='waitress', args=args)
        t.daemon = True
        t.start()

    def handler_thread(self, thread_no):
        threads = self.threads
        try:
            while threads.get(thread_no):
                task = self.queue.get()
                if task is None:
                    # Special value: kill this thread.
                    break
                try:
                    task.service()
                except Exception as e:
                    self.logger.exception(
                        'Exception when servicing %r' % task)
                    if isinstance(e, JustTesting):
                        break
        finally:
            with self.thread_mgmt_lock:
                self.stop_count -= 1
                threads.pop(thread_no, None)

    def set_thread_count(self, count):
        with self.thread_mgmt_lock:
            threads = self.threads
            thread_no = 0
            running = len(threads) - self.stop_count
            while running < count:
                # Start threads.
                while thread_no in threads:
                    thread_no = thread_no + 1
                threads[thread_no] = 1
                running += 1
                self.start_new_thread(self.handler_thread, (thread_no,))
                thread_no = thread_no + 1
            if running > count:
                # Stop threads.
                to_stop = running - count
                self.stop_count += to_stop
                for n in range(to_stop):
                    self.queue.put(None)
                    running -= 1

    def add_task(self, task):
        queue_depth = self.queue.qsize()
        if queue_depth > 0:
            self.queue_logger.warning(
                "Task queue depth is %d" %
                queue_depth)
        try:
            task.defer()
            self.queue.put(task)
        except:
            task.cancel()
            raise

    def shutdown(self, cancel_pending=True, timeout=5):
        self.set_thread_count(0)
        # Ensure the threads shut down.
        threads = self.threads
        expiration = time.time() + timeout
        while threads:
            if time.time() >= expiration:
                self.logger.warning(
                    "%d thread(s) still running" %
                    len(threads))
                break
            time.sleep(0.1)
        if cancel_pending:
            # Cancel remaining tasks.
            try:
                queue = self.queue
                while not queue.empty():
                    task = queue.get()
                    if task is not None:
                        task.cancel()
            except Empty: # pragma: no cover
                pass
            return True
        return False

class Task(object):
    close_on_finish = False
    status = '200 OK'
    wrote_header = False
    start_time = 0
    content_length = None
    content_bytes_written = 0
    logged_write_excess = False
    logged_write_no_body = False
    complete = False
    chunked_response = False
    logger = logger

    def __init__(self, channel, request):
        self.channel = channel
        self.request = request
        self.response_headers = []
        version = request.version
        if version not in ('1.0', '1.1'):
            # fall back to a version we support.
            version = '1.0'
        self.version = version

    def service(self):
        try:
            try:
                self.start()
                self.execute()
                self.finish()
            except socket.error:
                self.close_on_finish = True
                if self.channel.adj.log_socket_errors:
                    raise
        finally:
            pass

    @property
    def has_body(self):
        return not (self.status.startswith('1') or
                    self.status.startswith('204') or
                    self.status.startswith('304')
                    )

    def cancel(self):
        self.close_on_finish = True

    def defer(self):
        pass

    def build_response_header(self):
        version = self.version
        # Figure out whether the connection should be closed.
        connection = self.request.headers.get('CONNECTION', '').lower()
        response_headers = []
        content_length_header = None
        date_header = None
        server_header = None
        connection_close_header = None

        for (headername, headerval) in self.response_headers:
            headername = '-'.join(
                [x.capitalize() for x in headername.split('-')]
            )

            if headername == 'Content-Length':
                if self.has_body:
                    content_length_header = headerval
                else:
                    continue  # pragma: no cover

            if headername == 'Date':
                date_header = headerval

            if headername == 'Server':
                server_header = headerval

            if headername == 'Connection':
                connection_close_header = headerval.lower()
            # replace with properly capitalized version
            response_headers.append((headername, headerval))

        if (
            content_length_header is None and
            self.content_length is not None and
            self.has_body
        ):
            content_length_header = str(self.content_length)
            response_headers.append(
                ('Content-Length', content_length_header)
            )

        def close_on_finish():
            if connection_close_header is None:
                response_headers.append(('Connection', 'close'))
            self.close_on_finish = True

        if version == '1.0':
            if connection == 'keep-alive':
                if not content_length_header:
                    close_on_finish()
                else:
                    response_headers.append(('Connection', 'Keep-Alive'))
            else:
                close_on_finish()

        elif version == '1.1':
            if connection == 'close':
                close_on_finish()

            if not content_length_header:
                # RFC 7230: MUST NOT send Transfer-Encoding or Content-Length
                # for any response with a status code of 1xx, 204 or 304.

                if self.has_body:
                    response_headers.append(('Transfer-Encoding', 'chunked'))
                    self.chunked_response = True

                if not self.close_on_finish:
                    close_on_finish()

            # under HTTP 1.1 keep-alive is default, no need to set the header
        else:
            raise AssertionError('neither HTTP/1.0 or HTTP/1.1')

        # Set the Server and Date field, if not yet specified. This is needed
        # if the server is used as a proxy.
        ident = self.channel.server.adj.ident

        if not server_header:
            if ident:
                response_headers.append(('Server', ident))
        else:
            response_headers.append(('Via', ident or 'waitress'))

        if not date_header:
            response_headers.append(('Date', build_http_date(self.start_time)))

        self.response_headers = response_headers

        first_line = 'HTTP/%s %s' % (self.version, self.status)
        # NB: sorting headers needs to preserve same-named-header order
        # as per RFC 2616 section 4.2; thus the key=lambda x: x[0] here;
        # rely on stable sort to keep relative position of same-named headers
        next_lines = ['%s: %s' % hv for hv in sorted(
            self.response_headers, key=lambda x: x[0])]
        lines = [first_line] + next_lines
        res = '%s\r\n\r\n' % '\r\n'.join(lines)

        return tobytes(res)

    def remove_content_length_header(self):
        response_headers = []

        for header_name, header_value in self.response_headers:
            if header_name.lower() == 'content-length':
                continue  # pragma: nocover
            response_headers.append((header_name, header_value))

        self.response_headers = response_headers

    def start(self):
        self.start_time = time.time()

    def finish(self):
        if not self.wrote_header:
            self.write(b'')
        if self.chunked_response:
            # not self.write, it will chunk it!
            self.channel.write_soon(b'0\r\n\r\n')

    def write(self, data):
        if not self.complete:
            raise RuntimeError('start_response was not called before body '
                               'written')
        channel = self.channel
        if not self.wrote_header:
            rh = self.build_response_header()
            channel.write_soon(rh)
            self.wrote_header = True

        if data and self.has_body:
            towrite = data
            cl = self.content_length
            if self.chunked_response:
                # use chunked encoding response
                towrite = tobytes(hex(len(data))[2:].upper()) + b'\r\n'
                towrite += data + b'\r\n'
            elif cl is not None:
                towrite = data[:cl - self.content_bytes_written]
                self.content_bytes_written += len(towrite)
                if towrite != data and not self.logged_write_excess:
                    self.logger.warning(
                        'application-written content exceeded the number of '
                        'bytes specified by Content-Length header (%s)' % cl)
                    self.logged_write_excess = True
            if towrite:
                channel.write_soon(towrite)
        elif data:
            # Cheat, and tell the application we have written all of the bytes,
            # even though the response shouldn't have a body and we are
            # ignoring it entirely.
            self.content_bytes_written += len(data)

            if not self.logged_write_no_body:
                self.logger.warning(
                    'application-written content was ignored due to HTTP '
                    'response that may not contain a message-body: (%s)' % self.status)
                self.logged_write_no_body = True


class ErrorTask(Task):
    """ An error task produces an error response
    """
    complete = True

    def execute(self):
        e = self.request.error
        body = '%s\r\n\r\n%s' % (e.reason, e.body)
        tag = '\r\n\r\n(generated by waitress)'
        body = body + tag
        self.status = '%s %s' % (e.code, e.reason)
        cl = len(body)
        self.content_length = cl
        self.response_headers.append(('Content-Length', str(cl)))
        self.response_headers.append(('Content-Type', 'text/plain'))
        if self.version == '1.1':
            connection = self.request.headers.get('CONNECTION', '').lower()
            if connection == 'close':
                self.response_headers.append(('Connection', 'close'))
            # under HTTP 1.1 keep-alive is default, no need to set the header
        else:
            # HTTP 1.0
            self.response_headers.append(('Connection', 'close'))
        self.close_on_finish = True
        self.write(tobytes(body))

class WSGITask(Task):
    """A WSGI task produces a response from a WSGI application.
    """
    environ = None

    def execute(self):
        env = self.get_environment()

        def start_response(status, headers, exc_info=None):
            if self.complete and not exc_info:
                raise AssertionError("start_response called a second time "
                                     "without providing exc_info.")
            if exc_info:
                try:
                    if self.wrote_header:
                        # higher levels will catch and handle raised exception:
                        # 1. "service" method in task.py
                        # 2. "service" method in channel.py
                        # 3. "handler_thread" method in task.py
                        reraise(exc_info[0], exc_info[1], exc_info[2])
                    else:
                        # As per WSGI spec existing headers must be cleared
                        self.response_headers = []
                finally:
                    exc_info = None

            self.complete = True

            if not status.__class__ is str:
                raise AssertionError('status %s is not a string' % status)
            if '\n' in status or '\r' in status:
                raise ValueError("carriage return/line "
                                 "feed character present in status")

            self.status = status

            # Prepare the headers for output
            for k, v in headers:
                if not k.__class__ is str:
                    raise AssertionError(
                        'Header name %r is not a string in %r' % (k, (k, v))
                    )
                if not v.__class__ is str:
                    raise AssertionError(
                        'Header value %r is not a string in %r' % (v, (k, v))
                    )

                if '\n' in v or '\r' in v:
                    raise ValueError("carriage return/line "
                                     "feed character present in header value")
                if '\n' in k or '\r' in k:
                    raise ValueError("carriage return/line "
                                     "feed character present in header name")

                kl = k.lower()
                if kl == 'content-length':
                    self.content_length = int(v)
                elif kl in hop_by_hop:
                    raise AssertionError(
                        '%s is a "hop-by-hop" header; it cannot be used by '
                        'a WSGI application (see PEP 3333)' % k)

            self.response_headers.extend(headers)

            # Return a method used to write the response data.
            return self.write

        # Call the application to handle the request and write a response
        app_iter = self.channel.server.application(env, start_response)

        if app_iter.__class__ is ReadOnlyFileBasedBuffer:
            # NB: do not put this inside the below try: finally: which closes
            # the app_iter; we need to defer closing the underlying file.  It's
            # intention that we don't want to call ``close`` here if the
            # app_iter is a ROFBB; the buffer (and therefore the file) will
            # eventually be closed within channel.py's _flush_some or
            # handle_close instead.
            cl = self.content_length
            size = app_iter.prepare(cl)
            if size:
                if cl != size:
                    if cl is not None:
                        self.remove_content_length_header()
                    self.content_length = size
                self.write(b'') # generate headers
                self.channel.write_soon(app_iter)
                return

        try:
            first_chunk_len = None
            for chunk in app_iter:
                if first_chunk_len is None:
                    first_chunk_len = len(chunk)
                    # Set a Content-Length header if one is not supplied.
                    # start_response may not have been called until first
                    # iteration as per PEP, so we must reinterrogate
                    # self.content_length here
                    if self.content_length is None:
                        app_iter_len = None
                        if hasattr(app_iter, '__len__'):
                            app_iter_len = len(app_iter)
                        if app_iter_len == 1:
                            self.content_length = first_chunk_len
                # transmit headers only after first iteration of the iterable
                # that returns a non-empty bytestring (PEP 3333)
                if chunk:
                    self.write(chunk)

            cl = self.content_length
            if cl is not None:
                if self.content_bytes_written != cl:
                    # close the connection so the client isn't sitting around
                    # waiting for more data when there are too few bytes
                    # to service content-length
                    self.close_on_finish = True
                    if self.request.command != 'HEAD':
                        self.logger.warning(
                            'application returned too few bytes (%s) '
                            'for specified Content-Length (%s) via app_iter' % (
                                self.content_bytes_written, cl),
                        )
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()

    def parse_proxy_headers(
        self,
        environ,
        headers,
        trusted_proxy_count=1,
        trusted_proxy_headers=None,
    ):
        if trusted_proxy_headers is None:
            trusted_proxy_headers = set()

        forwarded_for = []
        forwarded_host = forwarded_proto = forwarded_port = forwarded = ""
        client_addr = None
        untrusted_headers = set(PROXY_HEADERS)

        def warn_unspecified_behavior(header):
            self.logger.warning(
                "Found multiple values in %s, this has unspecified behaviour. "
                "Ignoring header value.",
                header,
            )

        if "x-forwarded-for" in trusted_proxy_headers and "X_FORWARDED_FOR" in headers:
            forwarded_for = []

            for forward_hop in headers["X_FORWARDED_FOR"].split(","):
                forward_hop = forward_hop.strip()
                forward_hop = undquote(forward_hop)

                # Make sure that all IPv6 addresses are surrounded by brackets

                if ":" in forward_hop and forward_hop[-1] != "]":
                    forwarded_for.append("[{}]".format(forward_hop))
                else:
                    forwarded_for.append(forward_hop)

            forwarded_for = forwarded_for[-trusted_proxy_count:]
            client_addr = forwarded_for[0]

            untrusted_headers.remove("X_FORWARDED_FOR")

        if "x-forwarded-host" in trusted_proxy_headers and "X_FORWARDED_HOST" in headers:
            forwarded_host_multiple = []

            for forward_host in headers["X_FORWARDED_HOST"].split(","):
                forward_host = forward_host.strip()
                forward_host = undquote(forward_host)
                forwarded_host_multiple.append(forward_host)

            forwarded_host_multiple = forwarded_host_multiple[-trusted_proxy_count:]
            forwarded_host = forwarded_host_multiple[0]

            untrusted_headers.remove("X_FORWARDED_HOST")

        if "x-forwarded-proto" in trusted_proxy_headers:
            forwarded_proto = undquote(headers.get("X_FORWARDED_PROTO", ""))
            untrusted_headers.remove("X_FORWARDED_PROTO")

            if "," in forwarded_proto:
                forwarded_proto = ""
                warn_unspecified_behavior("X-Forwarded-Proto")

        if "x-forwarded-port" in trusted_proxy_headers:
            forwarded_port = undquote(headers.get("X_FORWARDED_PORT", ""))
            untrusted_headers.remove("X_FORWARDED_PORT")

            if "," in forwarded_port:
                forwarded_port = ""
                warn_unspecified_behavior("X-Forwarded-Port")

        if "x-forwarded-by" in trusted_proxy_headers:
            # Waitress itself does not use X-Forwarded-By, but we can not
            # remove it so it can get set in the environ
            untrusted_headers.remove("X_FORWARDED_BY")

        if "forwarded" in trusted_proxy_headers:
            forwarded = headers.get("FORWARDED", None)
            untrusted_headers = PROXY_HEADERS - {"FORWARDED"}

        # If the Forwarded header exists, it gets priority
        if forwarded:
            proxies = []

            for forwarded_element in forwarded.split(","):
                # Remove whitespace that may have been introduced when
                # appending a new entry
                forwarded_element = forwarded_element.strip()

                forwarded_for = forwarded_host = forwarded_proto = ""
                forwarded_port = forwarded_by = ""

                for pair in forwarded_element.split(";"):
                    pair = pair.lower()

                    if not pair:
                        continue

                    token, equals, value = pair.partition("=")

                    if equals != "=":
                        raise ValueError("Invalid forwarded-pair in Forwarded element")

                    if token.strip() != token:
                        raise ValueError("token may not be surrounded by whitespace")

                    if value.strip() != value:
                        raise ValueError("value may not be surrounded by whitespace")

                    if token == "by":
                        forwarded_by = undquote(value)

                    elif token == "for":
                        forwarded_for = undquote(value)

                    elif token == "host":
                        forwarded_host = undquote(value)

                    elif token == "proto":
                        forwarded_proto = undquote(value)

                    else:
                        self.logger.warning("Unknown Forwarded token: %s" % token)

                proxies.append(
                    Forwarded(
                        forwarded_by, forwarded_for, forwarded_host, forwarded_proto
                    )
                )

            proxies = proxies[-trusted_proxy_count:]

            # Iterate backwards and fill in some values, the oldest entry that
            # contains the information we expect is the one we use. We expect
            # that intermediate proxies may re-write the host header or proto,
            # but the oldest entry is the one that contains the information the
            # client expects when generating URL's
            #
            # Forwarded: for="[2001:db8::1]";host="example.com:8443";proto="https"
            # Forwarded: for=192.0.2.1;host="example.internal:8080"
            #
            # (After HTTPS header folding) should mean that we use as values:
            #
            # Host: example.com
            # Protocol: https
            # Port: 8443

            for proxy in proxies[::-1]:
                client_addr = proxy.for_ or client_addr
                forwarded_host = proxy.host or forwarded_host
                forwarded_proto = proxy.proto or forwarded_proto

        if forwarded_proto:
            forwarded_proto = forwarded_proto.lower()

            if forwarded_proto not in {"http", "https"}:
                raise ValueError(
                    'Invalid "Forwarded Proto=" or "X-Forwarded-Proto" value.'
                )

            # Set the URL scheme to the proxy provided proto
            environ["wsgi.url_scheme"] = forwarded_proto

            if not forwarded_port:
                if forwarded_proto == "http":
                    forwarded_port = "80"

                if forwarded_proto == "https":
                    forwarded_port = "443"

        if forwarded_host:
            if ":" in forwarded_host and forwarded_host[-1] != "]":
                host, port = forwarded_host.rsplit(":", 1)
                host, port = host.strip(), str(port)

                # We trust the port in the Forwarded Host/X-Forwarded-Host over
                # X-Forwarded-Port, or whatever we got from Forwarded
                # Proto/X-Forwarded-Proto.

                if forwarded_port != port:
                    forwarded_port = port

                # We trust the proxy server's forwarded Host
                environ["SERVER_NAME"] = host
                environ["HTTP_HOST"] = forwarded_host
            else:
                # We trust the proxy server's forwarded Host
                environ["SERVER_NAME"] = forwarded_host
                environ["HTTP_HOST"] = forwarded_host

                if forwarded_port:
                    if forwarded_port not in {"443", "80"}:
                        environ["HTTP_HOST"] = "{}:{}".format(
                            forwarded_host, forwarded_port
                        )
                    elif (
                        forwarded_port == "80" and environ["wsgi.url_scheme"] != "http"
                    ):
                        environ["HTTP_HOST"] = "{}:{}".format(
                            forwarded_host, forwarded_port
                        )
                    elif (
                        forwarded_port == "443"
                        and environ["wsgi.url_scheme"] != "https"
                    ):
                        environ["HTTP_HOST"] = "{}:{}".format(
                            forwarded_host, forwarded_port
                        )

        if forwarded_port:
            environ["SERVER_PORT"] = str(forwarded_port)

        if client_addr:
            if ":" in client_addr and client_addr[-1] != "]":
                addr, port = client_addr.rsplit(":", 1)
                environ["REMOTE_ADDR"] = addr.strip()
                environ["REMOTE_PORT"] = port.strip()
            else:
                environ["REMOTE_ADDR"] = client_addr.strip()

        return untrusted_headers

    def get_environment(self):
        """Returns a WSGI environment."""
        environ = self.environ
        if environ is not None:
            # Return the cached copy.
            return environ

        request = self.request
        path = request.path
        channel = self.channel
        server = channel.server
        url_prefix = server.adj.url_prefix

        if path.startswith('/'):
            # strip extra slashes at the beginning of a path that starts
            # with any number of slashes
            path = '/' + path.lstrip('/')

        if url_prefix:
            # NB: url_prefix is guaranteed by the configuration machinery to
            # be either the empty string or a string that starts with a single
            # slash and ends without any slashes
            if path == url_prefix:
                # if the path is the same as the url prefix, the SCRIPT_NAME
                # should be the url_prefix and PATH_INFO should be empty
                path = ''
            else:
                # if the path starts with the url prefix plus a slash,
                # the SCRIPT_NAME should be the url_prefix and PATH_INFO should
                # the value of path from the slash until its end
                url_prefix_with_trailing_slash = url_prefix + '/'
                if path.startswith(url_prefix_with_trailing_slash):
                    path = path[len(url_prefix):]

        environ = {
            'REQUEST_METHOD': request.command.upper(),
            'SERVER_PORT': str(server.effective_port),
            'SERVER_NAME': server.server_name,
            'SERVER_SOFTWARE': server.adj.ident,
            'SERVER_PROTOCOL': 'HTTP/%s' % self.version,
            'SCRIPT_NAME': url_prefix,
            'PATH_INFO': path,
            'QUERY_STRING': request.query,
            'wsgi.url_scheme': request.url_scheme,

            # the following environment variables are required by the WSGI spec
            'wsgi.version': (1, 0),

            # apps should use the logging module
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.input': request.get_body_stream(),
            'wsgi.file_wrapper': ReadOnlyFileBasedBuffer,
            'wsgi.input_terminated': True,  # wsgi.input is EOF terminated
        }
        remote_peer = environ['REMOTE_ADDR'] = channel.addr[0]

        headers = dict(request.headers)

        untrusted_headers = PROXY_HEADERS
        if server.adj.trusted_proxy == '*' or remote_peer == server.adj.trusted_proxy:
            untrusted_headers = self.parse_proxy_headers(
                environ,
                headers,
                trusted_proxy_count=server.adj.trusted_proxy_count,
                trusted_proxy_headers=server.adj.trusted_proxy_headers,
            )
        else:
            # If we are not relying on a proxy, we still want to try and set
            # the REMOTE_PORT to something useful, maybe None though.
            environ["REMOTE_PORT"] = str(channel.addr[1])

        # Nah, we aren't actually going to look up the reverse DNS for
        # REMOTE_ADDR, but we will happily set this environment variable for
        # the WSGI application. Spec says we can just set this to REMOTE_ADDR,
        # so we do.
        environ["REMOTE_HOST"] = environ["REMOTE_ADDR"]

        # Clear out the untrusted proxy headers
        if server.adj.clear_untrusted_proxy_headers:
            clear_untrusted_headers(
                headers,
                untrusted_headers,
                log_warning=server.adj.log_untrusted_proxy_headers,
                logger=self.logger,
            )

        for key, value in headers.items():
            value = value.strip()
            mykey = rename_headers.get(key, None)
            if mykey is None:
                mykey = 'HTTP_%s' % key
            if mykey not in environ:
                environ[mykey] = value

        # cache the environ for this request
        self.environ = environ
        return environ
