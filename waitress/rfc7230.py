"""
This contains a bunch of RFC7230 definitions and regular expressions that are
needed to properly parse HTTP messages.
"""

import re

from .compat import tobytes

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

# header-field   = field-name ":" OWS field-value OWS
# field-name     = token
# field-value    = *( field-content / obs-fold )
# field-content  = field-vchar [ 1*( SP / HTAB ) field-vchar ]
# field-vchar    = VCHAR / obs-text

FIELD_VCHAR = "[" + VCHAR + OBS_TEXT + "]"
FIELD_CONTENT = FIELD_VCHAR + "(" + RWS + FIELD_VCHAR + "){0,}"
FIELD_VALUE = "(" + FIELD_CONTENT + "){0,}"

HEADER_FIELD = re.compile(
    tobytes(
        "^(?P<name>" + TOKEN + "):" + OWS + "(?P<value>" + FIELD_VALUE + ")" + OWS + "$"
    )
)
