import os
import platform

# Fix for issue reported in https://github.com/Pylons/waitress/issues/138,
# Python on Windows may not define IPPROTO_IPV6 in socket.
import socket
import sys
import warnings
from http import client as httplib
from io import StringIO as NativeIO
from urllib import parse as urlparse
from urllib.parse import unquote_to_bytes

import _thread as thread

# True if we are running on Windows
WIN = platform.system() == "Windows"

string_types = (str,)
integer_types = (int,)
class_types = (type,)
text_type = str
binary_type = bytes
long = int


def unquote_bytes_to_wsgi(bytestring):
    return unquote_to_bytes(bytestring).decode("latin-1")


def text_(s, encoding="latin-1", errors="strict"):
    """ If ``s`` is an instance of ``binary_type``, return
    ``s.decode(encoding, errors)``, otherwise return ``s``"""

    if isinstance(s, binary_type):
        return s.decode(encoding, errors)

    return s  # pragma: no cover


def tostr(s):
    return str(s, "latin-1", "strict")


def tobytes(s):
    return bytes(s, "latin-1")


MAXINT = sys.maxsize
HAS_IPV6 = socket.has_ipv6

if hasattr(socket, "IPPROTO_IPV6") and hasattr(socket, "IPV6_V6ONLY"):
    IPPROTO_IPV6 = socket.IPPROTO_IPV6
    IPV6_V6ONLY = socket.IPV6_V6ONLY
else:  # pragma: no cover
    if WIN:
        IPPROTO_IPV6 = 41
        IPV6_V6ONLY = 27
    else:
        warnings.warn(
            "OS does not support required IPv6 socket flags. This is requirement "
            "for Waitress. Please open an issue at https://github.com/Pylons/waitress. "
            "IPv6 support has been disabled.",
            RuntimeWarning,
        )
        HAS_IPV6 = False
