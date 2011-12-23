import sys
import types

try:
    from urllib import unquote
except ImportError: # pragma: no cover
    from urllib.parse import unquote

try:
    import urlparse
except ImportError: # pragma: no cover
    from urllib import parse as urlparse


try:
    from cStringIO import StringIO
except ImportError: # pragma: no cover
    from StringIO import StringIO

# True if we are running on Python 3.
PY3 = sys.version_info[0] == 3

if PY3: # pragma: no cover
    string_types = str,
    integer_types = int,
    class_types = type,
    text_type = str
    binary_type = bytes
    long = int
else:
    string_types = basestring,
    integer_types = (int, long)
    class_types = (type, types.ClassType)
    text_type = unicode
    binary_type = str
    long = long

if PY3: # pragma: no cover
    def toascii(s):
        if isinstance(s, text_type):
            s = s.encode('ascii')
        return str(s, 'ascii', 'strict')
else:
    def toascii(s):
        if isinstance(s, text_type):
            s = s.encode('ascii')
        return str(s)

