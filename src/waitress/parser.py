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
"""HTTP Request Parser

This server uses asyncore to accept connections and do initial
processing but threads to do work.
"""

from io import BytesIO
import re
from urllib import parse
from urllib.parse import unquote_to_bytes

from waitress.buffers import OverflowableBuffer
from waitress.receiver import ChunkedReceiver, FixedStreamReceiver
from waitress.rfc7230 import AUTHORITY_FORM_RE, HEADER_FIELD_RE, HOST_RE, ONLY_DIGIT_RE
from waitress.utilities import (
    BadRequest,
    RequestEntityTooLarge,
    RequestHeaderFieldsTooLarge,
    ServerNotImplemented,
    find_double_newline,
)

# A list of HEADERS that must not be duplicated per RFC 9112
SINGLETON_FIELDS = frozenset({"HOST", "CONTENT_LENGTH", "CONTENT_TYPE"})


def unquote_bytes_to_wsgi(bytestring):
    return unquote_to_bytes(bytestring).decode("latin-1")


class ParsingError(Exception):
    pass


class TransferEncodingNotImplemented(Exception):
    pass


class HTTPRequestParser:
    """A structure that collects the HTTP request.

    Once the stream is completed, the instance is passed to
    a server task constructor.
    """

    completed = False  # Set once request is completed.
    empty = False  # Set if no request was made.
    expect_continue = False  # client sent "Expect: 100-continue" header
    headers_finished = False  # True when headers have been read
    header_plus = b""
    chunked = False
    content_length = 0
    header_bytes_received = 0
    body_bytes_received = 0
    body_rcv = None
    version = "1.0"
    error = None
    connection_close = False

    # Other attributes: first_line, header, headers, command, uri, version,
    # path, query, fragment

    def __init__(self, adj):
        """
        adj is an Adjustments object.
        """
        # headers is a mapping containing keys translated to uppercase
        # with dashes turned into underscores.
        self.headers = {}
        self.adj = adj

    def received(self, data):
        """
        Receives the HTTP stream for one request.  Returns the number of
        bytes consumed.  Sets the completed flag once both the header and the
        body have been received.
        """

        if self.completed:
            return 0  # Can't consume any more.

        datalen = len(data)
        br = self.body_rcv

        if br is None:
            # In header.
            max_header = self.adj.max_request_header_size

            s = self.header_plus + data
            index = find_double_newline(s)
            consumed = 0

            if index >= 0:
                # If the headers have ended, and we also have part of the body
                # message in data we still want to validate we aren't going
                # over our limit for received headers.
                self.header_bytes_received = index
                consumed = datalen - (len(s) - index)
            else:
                self.header_bytes_received += datalen
                consumed = datalen

            # If the first line + headers is over the max length, we return a
            # RequestHeaderFieldsTooLarge error rather than continuing to
            # attempt to parse the headers.

            if self.header_bytes_received >= max_header:
                self.parse_header(b"GET / HTTP/1.0\r\n")
                self.error = RequestHeaderFieldsTooLarge(
                    "exceeds max_header of %s" % max_header
                )
                self.completed = True

                return consumed

            if index >= 0:
                # Header finished.
                header_plus = s[:index]

                # Remove preceding blank lines. This is suggested by
                # https://tools.ietf.org/html/rfc7230#section-3.5 to support
                # clients sending an extra CR LF after another request when
                # using HTTP pipelining
                header_plus = header_plus.lstrip()

                if not header_plus:
                    self.empty = True
                    self.completed = True
                else:
                    try:
                        self.parse_header(header_plus)
                    except ParsingError as e:
                        self.error = BadRequest(e.args[0])
                        self.completed = True
                    except TransferEncodingNotImplemented as e:
                        self.error = ServerNotImplemented(e.args[0])
                        self.completed = True
                    else:
                        if self.body_rcv is None:
                            # no content-length header and not a t-e: chunked
                            # request
                            self.completed = True

                        if self.content_length > 0:
                            max_body = self.adj.max_request_body_size
                            # we won't accept this request if the content-length
                            # is too large

                            if self.content_length >= max_body:
                                self.error = RequestEntityTooLarge(
                                    "exceeds max_body of %s" % max_body
                                )
                                self.completed = True
                self.headers_finished = True

                return consumed

            # Header not finished yet.
            self.header_plus = s

            return datalen
        else:
            # In body.
            consumed = br.received(data)
            self.body_bytes_received += consumed
            max_body = self.adj.max_request_body_size

            if self.body_bytes_received >= max_body:
                # this will only be raised during t-e: chunked requests
                self.error = RequestEntityTooLarge("exceeds max_body of %s" % max_body)
                self.completed = True
            elif br.error:
                # garbage in chunked encoding input probably
                self.error = br.error
                self.completed = True
            elif br.completed:
                # The request (with the body) is ready to use.
                self.completed = True

                if self.chunked:
                    # We've converted the chunked transfer encoding request
                    # body into a normal request body, so we know its content
                    # length; set the header here.  We already popped the
                    # TRANSFER_ENCODING header in parse_header, so this will
                    # appear to the client to be an entirely non-chunked HTTP
                    # request with a valid content-length.
                    self.headers["CONTENT_LENGTH"] = str(br.__len__())

            return consumed

    def parse_header(self, header_plus):
        """
        Parses the header_plus block of text (the headers plus the
        first line of the request).
        """
        index = header_plus.find(b"\r\n")

        if index >= 0:
            first_line = header_plus[:index].rstrip()
            header = header_plus[index + 2 :]
        else:
            raise ParsingError("HTTP message header invalid")

        if b"\r" in first_line or b"\n" in first_line:
            raise ParsingError("Bare CR or LF found in HTTP message")

        self.first_line = first_line  # for testing

        lines = get_header_lines(header)

        headers = self.headers

        for line in lines:
            header = HEADER_FIELD_RE.match(line)

            if not header:
                raise ParsingError("Invalid header")

            key, value = header.group("name", "value")

            if b"_" in key:
                # TODO(xistence): Should we drop this request instead?

                continue

            # Only strip off whitespace that is considered valid whitespace by
            # RFC7230, don't strip the rest
            value = value.strip(b" \t")
            key1 = key.upper().replace(b"-", b"_").decode("latin-1")

            # Reject duplicate 'Host' headers as per RFC 9112 section 3.2
            if key1 in SINGLETON_FIELDS and key1 in headers:
                raise ParsingError(f"Duplicate header: {key.decode('latin-1')}")

            # If a header already exists, we append subsequent values
            # separated by a comma. Applications already need to handle
            # the comma separated values, as HTTP front ends might do
            # the concatenation for you (behavior specified in RFC2616).
            try:
                headers[key1] += (b", " + value).decode("latin-1")
            except KeyError:
                headers[key1] = value.decode("latin-1")

        # command, uri, version will be bytes
        command, uri, version = crack_first_line(first_line)
        if command == uri == version == b"":
            raise ParsingError("Start line is invalid")

        # self.request_uri is like nginx's request_uri:
        # "full original request URI (with arguments)"
        self.request_uri = uri.decode("latin-1")
        version = version.decode("latin-1")
        command = command.decode("latin-1")
        self.command = command
        self.version = version

        if command == "CONNECT":
            # RFC 9112 section 3.2.3: the request-target of a CONNECT is an
            # authority-form, and a server MUST reject a CONNECT that targets
            # an empty or invalid port number.
            #
            # Waitress leaves it to the WSGI application to decide what to do
            # with a CONNECT, up to and including implementing a proxy with it,
            # but the application can only do that safely if the target it is
            # handed is well formed. This validates the shape of the
            # request-target, it does not reject the method.
            #
            # NB: this has to happen before split_uri() is given a chance to
            # look at the request-target, as urlsplit() parses the
            # authority-form "example.com:443" as the scheme "example.com"
            # followed by the path "443".
            validate_authority_form(uri)

        (
            self.proxy_scheme,
            self.proxy_netloc,
            self.path,
            self.query,
            self.fragment,
        ) = split_uri(uri)

        # NB: a CONNECT is excluded here because its request-target is an
        # authority-form, which urlsplit() reads as a scheme followed by a path
        # ("example.com:443" comes back as the scheme "example.com" and the
        # path "443"). An authority-form is not an absolute-form, and it has
        # been validated as one above already.
        if self.proxy_scheme and command != "CONNECT":
            # This is an absolute-form request-target. RFC 9112 section 3.2.2
            # says that an origin server MUST ignore the received Host header
            # field and use the host information from the request-target
            # instead, so that the two can't disagree about which host the
            # request was meant for.
            #
            # validate_uri_host() rejects a userinfo subcomponent along with
            # everything else that isn't a valid uri-host, since "@" may not
            # appear in one. RFC 9110 section 4.2.1 requires that an "http"
            # URI with an empty host be rejected as invalid, so an authority
            # is required here rather than merely allowed.
            if not self.proxy_netloc:
                raise ParsingError("Empty authority in absolute-form request-target")

            validate_uri_host(self.proxy_netloc, "request-target authority")

            headers["HOST"] = self.proxy_netloc

        # RFC 9112 section 3.2 requires a 400 (Bad Request) response to any
        # HTTP/1.1 request that lacks a Host header field, or that has a Host
        # header field with an invalid field value. Duplicate Host headers are
        # already rejected as part of SINGLETON_FIELDS above.
        host = headers.get("HOST")

        if host is None:
            if version == "1.1":
                raise ParsingError("HTTP/1.1 request does not contain a Host header")
        else:
            validate_uri_host(host, "Host header")

        self.url_scheme = self.adj.url_scheme
        connection = headers.get("CONNECTION", "")

        if version == "1.0":
            if connection.lower() != "keep-alive":
                self.connection_close = True

        if version == "1.1":
            # since the server buffers data from chunked transfers and clients
            # never need to deal with chunked requests, downstream clients
            # should not see the HTTP_TRANSFER_ENCODING header; we pop it
            # here
            te = headers.pop("TRANSFER_ENCODING", "")

            # NB: We can not just call bare strip() here because it will also
            # remove other non-printable characters that we explicitly do not
            # want removed so that if someone attempts to smuggle a request
            # with these characters we don't fall prey to it.
            #
            # For example \x85 is stripped by default, but it is not considered
            # valid whitespace to be stripped by RFC7230.
            encodings = [
                encoding.strip(" \t").lower() for encoding in te.split(",") if encoding
            ]

            for encoding in encodings:
                # Out of the transfer-codings listed in
                # https://tools.ietf.org/html/rfc7230#section-4 we only support
                # chunked at this time.

                # Note: the identity transfer-coding was removed in RFC7230:
                # https://tools.ietf.org/html/rfc7230#appendix-A.2 and is thus
                # not supported

                if encoding not in {"chunked"}:
                    raise TransferEncodingNotImplemented(
                        "Transfer-Encoding requested is not supported."
                    )

            if encodings and encodings[-1] == "chunked":
                if (
                    len([encoding for encoding in encodings if encoding == "chunked"])
                    != 1
                ):
                    raise TransferEncodingNotImplemented(
                        "Transfer-Encoding is invalid. Multiple chunked encodings requested."
                    )

                self.chunked = True
                buf = OverflowableBuffer(self.adj.inbuf_overflow)
                self.body_rcv = ChunkedReceiver(buf)

                # RFC9112 states that we need to close the connection if the
                # Transfer-Encoding is set, AND a Content-Length is provided.
                cl = headers.pop("CONTENT_LENGTH", None)
                if cl is not None:
                    self.connection_close = True

            elif encodings:  # pragma: nocover
                raise TransferEncodingNotImplemented(
                    "Transfer-Encoding requested is not supported."
                )

            expect = headers.get("EXPECT", "").lower()
            self.expect_continue = expect == "100-continue"

            if connection.lower() == "close":
                self.connection_close = True

        if not self.chunked:
            cl = headers.get("CONTENT_LENGTH", "0")

            if not ONLY_DIGIT_RE.match(cl.encode("latin-1")):
                raise ParsingError("Content-Length is invalid")

            cl = int(cl)
            self.content_length = cl

            if cl > 0:
                buf = OverflowableBuffer(self.adj.inbuf_overflow)
                self.body_rcv = FixedStreamReceiver(cl, buf)

    def get_body_stream(self):
        body_rcv = self.body_rcv

        if body_rcv is not None:
            return body_rcv.getfile()
        else:
            return BytesIO()

    def close(self):
        body_rcv = self.body_rcv

        if body_rcv is not None:
            body_rcv.getbuf().close()


def validate_uri_host(value, what):
    """
    Validate that ``value`` is a "uri-host [ ':' port ]" as required by RFC 7230
    section 5.4 for the Host header field, and by RFC 3986 section 3.2 for the
    authority of an absolute-form request-target.

    ``what`` names the thing being validated, for use in the error message.
    """

    if not HOST_RE.match(value.encode("latin-1")):
        raise ParsingError(f"Invalid {what}")


def validate_authority_form(uri):
    """
    Validate that ``uri`` is an "authority-form" request-target as defined by
    RFC 9112 section 3.2.3, that is a uri-host followed by a non-empty and
    in-range port number.
    """

    m = AUTHORITY_FORM_RE.match(uri)

    if m is None:
        raise ParsingError("Request-target is not in the authority-form")

    host, port = m.group("host", "port")

    if not host:
        raise ParsingError("Request-target does not contain a host")

    # The regular expression bounds the port to at most 5 digits, so int() is
    # safe to use on it here
    if not port or not 0 < int(port) <= 65535:
        raise ParsingError("Request-target contains an empty or invalid port")


def split_uri(uri):
    # urlsplit handles byte input by returning bytes on py3, so
    # scheme, netloc, path, query, and fragment are bytes

    scheme = netloc = path = query = fragment = b""

    # urlsplit below will treat this as a scheme-less netloc, thereby losing
    # the original intent of the request. Here we shamelessly stole 4 lines of
    # code from the CPython stdlib to parse out the fragment and query but
    # leave the path alone. See
    # https://github.com/python/cpython/blob/8c9e9b0cd5b24dfbf1424d1f253d02de80e8f5ef/Lib/urllib/parse.py#L465-L468
    # and https://github.com/Pylons/waitress/issues/260

    if uri[:2] == b"//":
        path = uri

        if b"#" in path:
            path, fragment = path.split(b"#", 1)

        if b"?" in path:
            path, query = path.split(b"?", 1)
    else:
        try:
            scheme, netloc, path, query, fragment = parse.urlsplit(uri)
        except UnicodeError:
            raise ParsingError("Bad URI")

    return (
        scheme.decode("latin-1"),
        netloc.decode("latin-1"),
        unquote_bytes_to_wsgi(path),
        query.decode("latin-1"),
        fragment.decode("latin-1"),
    )


def get_header_lines(header):
    """
    Splits the header into lines, putting multi-line headers together.
    """
    r = []
    lines = header.split(b"\r\n")

    for line in lines:
        if not line:
            continue

        if b"\r" in line or b"\n" in line:
            raise ParsingError(
                'Bare CR or LF found in header line "%s"' % str(line, "latin-1")
            )

        if line.startswith((b" ", b"\t")):
            if not r:
                # https://corte.si/posts/code/pathod/pythonservers/index.html
                raise ParsingError('Malformed header line "%s"' % str(line, "latin-1"))
            r[-1] += line
        else:
            r.append(line)

    return r


first_line_re = re.compile(
    rb"(?P<method>[!#$%&'*+\-.^_`|~0-9A-Za-z]+) "
    rb"(?P<uri>(?:[^ :?#]+://[^ ?#/]*(?:[0-9]{1,5})?)?[^ ]+)"
    rb"(?: HTTP/(?P<version>[0-9]\.[0-9]))?"
)


def crack_first_line(line):
    m = first_line_re.fullmatch(line)

    if m is None:
        return b"", b"", b""

    version = m["version"] or b""
    method = m["method"]
    uri = m["uri"]

    # the request methods that are currently defined are all uppercase:
    # https://www.iana.org/assignments/http-methods/http-methods.xhtml and
    # the request method is case sensitive according to
    # https://tools.ietf.org/html/rfc7231#section-4.1

    # By disallowing anything but uppercase methods we save poor
    # unsuspecting souls from sending lowercase HTTP methods to waitress
    # and having the request complete, while servers like nginx drop the
    # request onto the floor.

    if method != method.upper():
        raise ParsingError('Malformed HTTP method "%s"' % str(method, "latin-1"))

    return method, uri, version
