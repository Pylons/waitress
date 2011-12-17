##############################################################################
#
# Copyright (c) 2004 Zope Foundation and Contributors.
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
"""Server utility functions
"""

def find_double_newline(s):
    """Returns the position just after a double newline in the given string."""
    pos1 = s.find('\n\r\n')  # One kind of double newline
    if pos1 >= 0:
        pos1 += 3
    pos2 = s.find('\n\n')    # Another kind of double newline
    if pos2 >= 0:
        pos2 += 2

    if pos1 >= 0:
        if pos2 >= 0:
            return min(pos1, pos2)
        else:
            return pos1
    else:
        return pos2
