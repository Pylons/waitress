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
"""Find max number of sockets allowed.
"""
# Medusa max_sockets module.

import socket
import select

# several factors here we might want to test:
# 1) max we can create
# 2) max we can bind
# 3) max we can listen on
# 4) max we can connect

def max_server_sockets():
    # TODO: This should be a configuration value as it takes a long time to
    # compute on Mac OSX
    return 100
    sl = []
    while 1:
        try:
            s = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
            s.bind (('',0))
            s.listen(5)
            sl.append (s)
        except:
            break
    num = len(sl)
    for s in sl:
        s.close()
    del sl
    return num

def max_client_sockets():
    # TODO: This should be a configuration value as it takes a long time to
    # compute on Mac OSX
    return 100
    # make a server socket
    server = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
    server.bind (('', 9999))
    server.listen (5)
    sl = []
    while 1:
        try:
            s = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
            s.connect (('', 9999))
            conn, addr = server.accept()
            sl.append ((s,conn))
        except:
            break
    num = len(sl)
    for s,c in sl:
        s.close()
        c.close()
    del sl
    return num

def max_select_sockets():
    # TODO: This should be a configuration value as it takes a long time to
    # compute on Mac OSX
    return 100
    sl = []
    while 1:
        try:
            num = len(sl)
            for i in range(1 + len(sl) // 20):
                # Increase exponentially.
                s = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
                s.bind (('',0))
                s.listen(5)
                sl.append (s)
            select.select(sl,[],[],0)
        except:
            break
    for s in sl:
        s.close()
    del sl
    return num
