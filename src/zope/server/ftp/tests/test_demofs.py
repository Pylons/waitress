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
"""Test the Demo Filesystem implementation.
"""
import demofs
from unittest import TestCase, TestSuite, main, makeSuite
from fstests import FileSystemTests
from StringIO import StringIO

class Test(FileSystemTests, TestCase):

    def setUp(self):
        root = demofs.Directory()
        root.grant('bob', demofs.write)
        fs = self.filesystem = demofs.DemoFileSystem(root, 'bob')
        fs.mkdir(self.dir_name)
        fs.writefile(self.file_name, StringIO(self.file_contents))
        fs.writefile(self.unwritable_filename, StringIO("save this"))
        fs.get(self.unwritable_filename).revoke('bob', demofs.write)

def test_suite():
    return TestSuite((
        makeSuite(Test),
        ))

if __name__=='__main__':
    main(defaultTest='test_suite')
