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

try:
    from Queue import (
        Queue,
        Empty,
        )
except ImportError:
    from queue import (
        Queue,
        Empty,
        )

try:
    import thread
except ImportError:
    import _thread as thread
    

if PY3: # pragma: no cover
    import builtins
    exec_ = getattr(builtins, "exec")

    def reraise(tp, value, tb=None):
        if value is None:
            value = tp
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value


    del builtins

else: # pragma: no cover
    def exec_(code, globs=None, locs=None):
        """Execute code in a namespace."""
        if globs is None:
            frame = sys._getframe(1)
            globs = frame.f_globals
            if locs is None:
                locs = frame.f_locals
            del frame
        elif locs is None:
            locs = globs
        exec("""exec code in globs, locs""")


    exec_("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")


