##############################################################################
#
# Copyright (c) 2003 Zope Foundation and Contributors.
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
"""Test the FTP publisher.
"""
import demofs
from unittest import TestCase, TestSuite, main, makeSuite
from fstests import FileSystemTests
from StringIO import StringIO
from zope.publisher.publish import mapply

class DemoFileSystem(demofs.DemoFileSystem):

    def rename(self, path, old, new):
        return demofs.DemoFileSystem.rename(
            self, "%s/%s" % (path, old), "%s/%s" % (path, new))

class Publication(object):

    def __init__(self, root):
        self.root = root

    def beforeTraversal(self, request):
        pass

    def getApplication(self, request):
        return self.root

    def afterTraversal(self, request, ob):
        pass

    def callObject(self, request, ob):
        command = getattr(ob, request.env['command'])
        if 'name' in request.env:
            request.env['path'] += "/" + request.env['name']
        return mapply(command, request = request.env)

    def afterCall(self, request, ob):
        pass

    def endRequest(self, request, ob):
        pass

    def handleException(self, object, request, info, retry_allowed=True):
        request.response._exc = info[:2]


class Request(object):

    def __init__(self, input, env):
        self.env = env
        self.response = Response()
        self.user = env['credentials']
        del env['credentials']

    def processInputs(self):
        pass

    def traverse(self, root):
        root.user = self.user
        return root

    def close(self):
        pass

class Response(object):

    _exc = _body = None

    def setResult(self, result):
        self._result = result

    def getResult(self):
        if self._exc:
            raise self._exc[0], self._exc[1]
        return self._result

class RequestFactory(object):

    def __init__(self, root):
        self.pub = Publication(root)

    def __call__(self, input, env):
        r = Request(input, env)
        r.publication = self.pub
        return r

class TestPublisherFileSystem(FileSystemTests, TestCase):

    def setUp(self):
        root = demofs.Directory()
        root.grant('bob', demofs.write)
        fs = DemoFileSystem(root, 'bob')
        fs.mkdir(self.dir_name)
        fs.writefile(self.file_name, StringIO(self.file_contents))
        fs.writefile(self.unwritable_filename, StringIO("save this"))
        fs.get(self.unwritable_filename).revoke('bob', demofs.write)

        # import only now to prevent the testrunner from importing it too early
        # Otherwise dualmodechannel.the_trigger is closed by the ZEO tests
        from zope.server.ftp.publisher import PublisherFileSystem
        self.filesystem = PublisherFileSystem('bob', RequestFactory(fs))

def test_suite():
    return TestSuite((
        makeSuite(TestPublisherFileSystem),
        ))

if __name__=='__main__':
    main(defaultTest='test_suite')
