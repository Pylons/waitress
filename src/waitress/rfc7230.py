"""
This contains a bunch of RFC7230 definitions and regular expressions that are
needed to properly parse HTTP messages.
"""

import re

HEXDIG = "[0-9a-fA-F]"
DIGIT = "[0-9]"

WS = "[ \t]"
OWS = WS + "{0,}?"
RWS = WS + "{1,}?"
BWS = OWS

# RFC 7230 Section 3.2.6 "Field Value Components":
# tchar          = "!" / "#" / "$" / "%" / "&" / "'" / "*"
#                / "+" / "-" / "." / "^" / "_" / "`" / "|" / "~"
#                / DIGIT / ALPHA
# obs-text      = %x80-FF
TCHAR = r"[!#$%&'*+\-.^_`|~0-9A-Za-z]"
OBS_TEXT = r"\x80-\xff"

TOKEN = TCHAR + "{1,}"

# RFC 5234 Appendix B.1 "Core Rules":
# VCHAR         =  %x21-7E
#                  ; visible (printing) characters
VCHAR = r"\x21-\x7e"

# The '\\' between \x5b and \x5d is needed to escape \x5d (']')
QDTEXT = "[\t \x21\x23-\x5b\\\x5d-\x7e" + OBS_TEXT + "]"

QUOTED_PAIR = r"\\" + "([\t " + VCHAR + OBS_TEXT + "])"
QUOTED_STRING = '"(?:(?:' + QDTEXT + ")|(?:" + QUOTED_PAIR + '))*"'

# header-field   = field-name ":" OWS field-value OWS
# field-name     = token
# field-value    = *( field-content / obs-fold )
# field-content  = field-vchar [ 1*( SP / HTAB ) field-vchar ]
# field-vchar    = VCHAR / obs-text

# Errata from: https://www.rfc-editor.org/errata_search.php?rfc=7230&eid=4189
# changes field-content to:
#
# field-content  = field-vchar [ 1*( SP / HTAB / field-vchar )
#                  field-vchar ]

FIELD_VCHAR = "[" + VCHAR + OBS_TEXT + "]"
# Field content is more greedy than the ABNF, in that it will match the whole value
FIELD_CONTENT = FIELD_VCHAR + "+(?:[ \t]+" + FIELD_VCHAR + "+)*"
# Which allows the field value here to just see if there is even a value in the first place
FIELD_VALUE = "(?:" + FIELD_CONTENT + ")?"

# chunk-ext      = *( ";" chunk-ext-name [ "=" chunk-ext-val ] )
# chunk-ext-name = token
# chunk-ext-val  = token / quoted-string

CHUNK_EXT_NAME = TOKEN
CHUNK_EXT_VAL = "(?:" + TOKEN + ")|(?:" + QUOTED_STRING + ")"
CHUNK_EXT = (
    "(?:;(?P<extension>" + CHUNK_EXT_NAME + ")(?:=(?P<value>" + CHUNK_EXT_VAL + "))?)*"
)

# RFC 3986 Section 3.2.2 "Host", which is what RFC 7230 Section 5.4 uses to
# define the value of the Host header field, and what RFC 9112 Section 3.2.3
# uses for the authority-form of a request-target:
#
# host          = IP-literal / IPv4address / reg-name
# IP-literal    = "[" ( IPv6address / IPvFuture  ) "]"
# IPvFuture     = "v" 1*HEXDIG "." 1*( unreserved / sub-delims / ":" )
# reg-name      = *( unreserved / pct-encoded / sub-delims )
# unreserved    = ALPHA / DIGIT / "-" / "." / "_" / "~"
# sub-delims    = "!" / "$" / "&" / "'" / "(" / ")" / "*" / "+" / "," / ";" / "="
# pct-encoded   = "%" HEXDIG HEXDIG
#
# IPv4address is a strict subset of reg-name, so it doesn't need to be matched
# separately. The contents of an IP-literal are not validated any further than
# the set of characters that may appear inside of one.
UNRESERVED = r"[A-Za-z0-9\-._~]"
SUB_DELIMS = r"[!$&'()*+,;=]"
PCT_ENCODED = "%" + HEXDIG + HEXDIG
IPV6_LITERAL = r"\[[A-Fa-f0-9:.]+\]"
IPVFUTURE_LITERAL = (
    r"\[[vV]" + HEXDIG + r"+\.(?:" + UNRESERVED + "|" + SUB_DELIMS + "|:)+\\]"
)
IP_LITERAL = "(?:" + IPV6_LITERAL + "|" + IPVFUTURE_LITERAL + ")"
# NB: the alternatives here are disjoint (no character may start more than one
# of them), so this can't backtrack catastrophically
REG_NAME = "(?:" + UNRESERVED + "|" + PCT_ENCODED + "|" + SUB_DELIMS + ")*"
URI_HOST = "(?:" + IP_LITERAL + "|" + REG_NAME + ")"

# RFC 7230 Section 5.4: Host = uri-host [ ":" port ], where port = *DIGIT.
# Both the uri-host and the port may be empty as far as the grammar goes; the
# callers apply the stricter rules that their context requires.
HOST_RE = re.compile(("^" + URI_HOST + "(?::" + DIGIT + "*)?$").encode("latin-1"))

# RFC 9112 Section 3.2.3: authority-form = uri-host ":" port. It is used only
# for CONNECT, where the port is required to be present and valid.
AUTHORITY_FORM_RE = re.compile(
    ("^(?P<host>" + URI_HOST + "):(?P<port>" + DIGIT + "{0,5})$").encode("latin-1")
)

# Pre-compiled regular expressions for use elsewhere
ONLY_HEXDIG_RE = re.compile(("^" + HEXDIG + "+$").encode("latin-1"))
ONLY_DIGIT_RE = re.compile(("^" + DIGIT + "+$").encode("latin-1"))
HEADER_FIELD_RE = re.compile(
    (
        "^(?P<name>" + TOKEN + "):" + OWS + "(?P<value>" + FIELD_VALUE + ")" + OWS + "$"
    ).encode("latin-1")
)
QUOTED_PAIR_RE = re.compile(QUOTED_PAIR)
QUOTED_STRING_RE = re.compile(QUOTED_STRING)
CHUNK_EXT_RE = re.compile(("^" + CHUNK_EXT + "$").encode("latin-1"))
