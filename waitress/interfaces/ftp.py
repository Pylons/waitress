##############################################################################
# Copyright (c) 2002 Zope Foundation and Contributors.
# All Rights Reserved.
# 
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
##############################################################################
"""FTP server specific interfaces.
"""
from zope.interface import Interface

class IFTPCommandHandler(Interface):
    """This interface defines all the FTP commands that are supported by the
       server.

       Every command takes the command line as first arguments, since it is
       responsible
    """

    def cmd_abor(args):
        """Abort operation. No read access required.
        """

    def cmd_appe(args):
        """Append to a file. Write access required.
        """

    def cmd_cdup(args):
        """Change to parent of current working directory.
        """

    def cmd_cwd(args):
        """Change working directory.
        """

    def cmd_dele(args):
        """Delete a file. Write access required.
        """

    def cmd_help(args):
        """Give help information. No read access required.
        """

    def cmd_list(args):
        """Give list files in a directory or displays the info of one file.
        """

    def cmd_mdtm(args):
        """Show last modification time of file.

           Example output: 213 19960301204320

           Geez, there seems to be a second syntax for this fiel, where one
           can also set the modification time using:
           MDTM datestring pathname

        """

    def cmd_mkd(args):
        """Make a directory. Write access required.
        """

    def cmd_mode(args):
        """Set file transfer mode.  No read access required. Obselete.
        """

    def cmd_nlst(args):
        """Give name list of files in directory.
        """

    def cmd_noop(args):
        """Do nothing. No read access required.
        """

    def cmd_pass(args):
        """Specify password.
        """

    def cmd_pasv(args):
        """Prepare for server-to-server transfer. No read access required.
        """

    def cmd_port(args):
        """Specify data connection port. No read access required.
        """

    def cmd_pwd(args):
        """Print the current working directory.
        """

    def cmd_quit(args):
        """Terminate session. No read access required.
        """

    def cmd_rest(args):
        """Restart incomplete transfer.
        """

    def cmd_retr(args):
        """Retrieve a file.
        """

    def cmd_rmd(args):
        """Remove a directory. Write access required.
        """

    def cmd_rnfr(args):
        """Specify rename-from file name. Write access required.
        """

    def cmd_rnto(args):
        """Specify rename-to file name. Write access required.
        """

    def cmd_size(args):
        """Return size of file.
        """

    def cmd_stat(args):
        """Return status of server. No read access required.
        """

    def cmd_stor(args):
        """Store a file. Write access required.
        """

    def cmd_stru(args):
        """Set file transfer structure. Obselete."""

    def cmd_syst(args):
        """Show operating system type of server system.

           No read access required.

           Replying to this command is of questionable utility,
           because this server does not behave in a predictable way
           w.r.t. the output of the LIST command.  We emulate Unix ls
           output, but on win32 the pathname can contain drive
           information at the front Currently, the combination of
           ensuring that os.sep == '/' and removing the leading slash
           when necessary seems to work.  [cd'ing to another drive
           also works]

           This is how wuftpd responds, and is probably the most
           expected.  The main purpose of this reply is so that the
           client knows to expect Unix ls-style LIST output.

           one disadvantage to this is that some client programs
           assume they can pass args to /bin/ls.  a few typical
           responses:

           215 UNIX Type: L8 (wuftpd)
           215 Windows_NT version 3.51
           215 VMS MultiNet V3.3
           500 'SYST': command not understood. (SVR4)
        """

    def cmd_type(args):
        """Specify data transfer type. No read access required.
        """

    def cmd_user(args):
        """Specify user name. No read access required.
        """



# this is the command list from the wuftpd man page
# '!' requires write access
#
not_implemented_commands = {
    'acct': 'specify account (ignored)',
    'allo': 'allocate storage (vacuously)',
    'site': 'non-standard commands (see next section)',
    'stou': 'store a file with a unique name',                            #!
    'xcup': 'change to parent of current working directory (deprecated)',
    'xcwd': 'change working directory (deprecated)',
    'xmkd': 'make a directory (deprecated)',                              #!
    'xpwd': 'print the current working directory (deprecated)',
    'xrmd': 'remove a directory (deprecated)',                            #!
}


class IFileSystemAccess(Interface):
    """Provides authenticated access to a filesystem."""

    def authenticate(credentials):
        """Verifies filesystem access based on the presented credentials.

        Should raise zope.security.interfaces.Unauthorized if the user can
        not be authenticated.

        This method checks only general access and is not used for each
        call to open().  Rather, open() should do its own verification.

        Credentials are passed as (username, password) tuples.
        """

    def open(credentials):
        """Returns an IFileSystem.

        Should raise zope.security.interfaces.Unauthorized if the user
        can not be authenticated.

        Credentials are passed as (username, password) tuples.
        """


class IFileSystem(Interface):
    """An abstract filesystem.

       Opening files for reading, and listing directories, should
       return a producer.

       All paths are POSIX paths, even when run on Windows,
       which mainly means that FS implementations always expect forward
       slashes, and filenames are case-sensitive.

       `IFileSystem`, in generel, could be created many times per
       request. Thus it is not advisable to store state in them. However, if
       you have a special kind of `IFileSystemAccess` object that somhow
       manages an `IFileSystem` for each set of credentials, then it would be
       possible to store some state on this obejct. 
    """

    def type(path):
        """Return the file type at `path`.

        The return valie is 'd', for a directory, 'f', for a file, and
        None if there is no file at `path`.

        This method doesn't raise exceptions.
        """

    def names(path, filter=None):
        """Return a sequence of the names in a directory.

        If `filter` is not None, include only those names for which
        `filter` returns a true value.
        """

    def ls(path, filter=None):
        """Return a sequence of information objects.

        Returm item info objects (see the ls_info operation) for the files
        in a directory.

        If `filter` is not None, include only those names for which
        `filter` returns a true value.
        """

    def readfile(path, outstream, start=0, end=None):
        """Outputs the file at `path` to a stream.

        Data are copied starting from `start`.  If `end` is not None,
        data are copied up to `end`.

        """

    def lsinfo(path):
        """Return information for a unix-style ls listing for `path`.

        Information is returned as a dictionary containing the following keys:

        type

           The path type, either 'd' or 'f'.

        owner_name

           Defaults to "na".  Must not include spaces.

        owner_readable

           Defaults to True.

        owner_writable

           Defaults to True.

        owner_executable

           Defaults to True for directories and False otherwise.

        group_name

           Defaults to "na".  Must not include spaces.

        group_readable

           Defaults to True.

        group_writable

           Defaults to True.

        group_executable

           Defaults to True for directories and False otherwise.

        other_readable

           Defaults to False.

        other_writable

           Defaults to False.

        other_executable

           Defaults to True for directories and false otherwise.

        mtime

           Optional time, as a datetime.datetime object.

        nlinks

           The number of links. Defaults to 1.

        size

           The file size.  Defaults to 0.

        name

           The file name.
        """

    def mtime(path):
        """Return the modification time for the file at `path`.

        This method returns the modification time. It is assumed that the path
        exists. You can use the `type(path)` method to determine whether
        `path` points to a valid file.

        If the modification time is unknown, then return `None`.
        """

    def size(path):
        """Return the size of the file at path.

        This method returns the modification time. It is assumed that the path
        exists. You can use the `type(path)` method to determine whether
        `path` points to a valid file.
        """

    def mkdir(path):
        """Create a directory.

        If it is not possible or allowed to create the directory, an `OSError`
        should be raised describing the reason of failure. 
        """

    def remove(path):
        """Remove a file.  Same as unlink.

        If it is not possible or allowed to remove the file, an `OSError`
        should be raised describing the reason of failure. 
        """

    def rmdir(path):
        """Remove a directory.

        If it is not possible or allowed to remove the directory, an `OSError`
        should be raised describing the reason of failure. 
        """

    def rename(old, new):
        """Rename a file or directory."""

    def writefile(path, instream, start=None, end=None, append=False):
        """Write data to a file.

        Both `start` and `end` must be either None or a non-negative
        integer.

        If `append` is true, `start` and `end` are ignored.

        If `start` or `end` is not None, they specify the part of the
        file that is to be written.

        If `end` is None, the file is truncated after the data are
        written.  If `end` is not None, any parts of the file after
        `end` are left unchanged.

        Note that if `end` is not `None`, and there is not enough data
        in the `instream` it will fill the file up to `end`, then the missing
        data are undefined.

        If both `start` is `None` and `end` is `None`, then the file contents
        are overwritten.

        If `start` is specified and the file doesn't exist or is shorter
        than `start`, the data in the file before `start` file will be
        undefined.

        If you do not want to handle incorrect starting and ending indices,
        you can also raise an `IOError`, which will be properly handled by the
        server.
        """

    def writable(path):
        """Return boolean indicating whether a file at path is writable.

        Note that a true value should be returned if the file doesn't
        exist but its directory is writable.

        """
