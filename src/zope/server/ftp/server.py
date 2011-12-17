##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
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
"""FTP Server
"""
import asyncore
import posixpath
import socket
from datetime import date, timedelta
from getopt import getopt, GetoptError

from zope.security.interfaces import Unauthorized
from zope.interface import implements
from zope.server.buffers import OverflowableBuffer
from zope.server.interfaces import ITask
from zope.server.interfaces.ftp import IFileSystemAccess
from zope.server.interfaces.ftp import IFTPCommandHandler
from zope.server.linereceiver.lineserverchannel import LineServerChannel
from zope.server.serverbase import ServerBase
from zope.server.dualmodechannel import DualModeChannel, the_trigger

status_messages = {
    'OPEN_DATA_CONN'   : '150 Opening %s mode data connection for file list',
    'OPEN_CONN'        : '150 Opening %s connection for %s',
    'SUCCESS_200'      : '200 %s command successful.',
    'TYPE_SET_OK'      : '200 Type set to %s.',
    'STRU_OK'          : '200 STRU F Ok.',
    'MODE_OK'          : '200 MODE S Ok.',
    'FILE_DATE'        : '213 %4d%02d%02d%02d%02d%02d',
    'FILE_SIZE'        : '213 %d Bytes',
    'HELP_START'       : '214-The following commands are recognized',
    'HELP_END'         : '214 Help done.',
    'SERVER_TYPE'      : '215 %s Type: %s',
    'SERVER_READY'     : '220 %s FTP server (Zope Async/Thread V0.1) ready.',
    'GOODBYE'          : '221 Goodbye.',
    'SUCCESS_226'      : '226 %s command successful.',
    'TRANS_SUCCESS'    : '226 Transfer successful.',
    'PASV_MODE_MSG'    : '227 Entering Passive Mode (%s,%d,%d)',
    'LOGIN_SUCCESS'    : '230 Login Successful.',
    'SUCCESS_250'      : '250 %s command successful.',
    'SUCCESS_257'      : '257 %s command successful.',
    'ALREADY_CURRENT'  : '257 "%s" is the current directory.',
    'PASS_REQUIRED'    : '331 Password required',
    'RESTART_TRANSFER' : '350 Restarting at %d. Send STORE or '
                         'RETRIEVE to initiate transfer.',
    'READY_FOR_DEST'   : '350 File exists, ready for destination.',
    'NO_DATA_CONN'     : "425 Can't build data connection",
    'TRANSFER_ABORTED' : '426 Connection closed; transfer aborted.',
    'CMD_UNKNOWN'      : "500 '%s': command not understood.",
    'INTERNAL_ERROR'   : "500 Internal error: %s",
    'ERR_ARGS'         : '500 Bad command arguments',
    'MODE_UNKOWN'      : '502 Unimplemented MODE type',
    'WRONG_BYTE_SIZE'  : '504 Byte size must be 8',
    'STRU_UNKNOWN'     : '504 Unimplemented STRU type',
    'NOT_AUTH'         : "530 You are not authorized to perform the "
                         "'%s' command",
    'LOGIN_REQUIRED'   : '530 Please log in with USER and PASS',
    'LOGIN_MISMATCH'   : '530 The username and password do not match.',
    'ERR_NO_LIST'      : '550 Could not list directory or file: %s',
    'ERR_NO_DIR'       : '550 "%s": No such directory.',
    'ERR_NO_FILE'      : '550 "%s": No such file.',
    'ERR_NO_DIR_FILE'  : '550 "%s": No such file or directory.',
    'ERR_IS_NOT_FILE'  : '550 "%s": Is not a file',
    'ERR_CREATE_FILE'  : '550 Error creating file.',
    'ERR_CREATE_DIR'   : '550 Error creating directory: %s',
    'ERR_DELETE_FILE'  : '550 Error deleting file: %s',
    'ERR_DELETE_DIR'   : '550 Error removing directory: %s',
    'ERR_OPEN_READ'    : '553 Could not open file for reading: %s',
    'ERR_OPEN_WRITE'   : '553 Could not open file for writing: %s',
    'ERR_IO'           : '553 I/O Error: %s',
    'ERR_RENAME'       : '560 Could not rename "%s" to "%s": %s',
    'ERR_RNFR_SOURCE'  : '560 No source filename specify. Call RNFR first.',
    }

class FTPServerChannel(LineServerChannel):
    """The FTP Server Channel represents a connection to a particular
       client. We can therefore store information here."""

    implements(IFTPCommandHandler)


    # List of commands that are always available
    special_commands = (
        'cmd_quit', 'cmd_type', 'cmd_noop', 'cmd_user', 'cmd_pass')

    # These are the commands that are accessing the filesystem.
    # Since this could be also potentially a longer process, these commands
    # are also the ones that are executed in a different thread.
    thread_commands = (
        'cmd_appe', 'cmd_cdup', 'cmd_cwd', 'cmd_dele',
        'cmd_list', 'cmd_nlst', 'cmd_mdtm', 'cmd_mkd',
        'cmd_pass', 'cmd_retr', 'cmd_rmd', 'cmd_rnfr',
        'cmd_rnto', 'cmd_size', 'cmd_stor', 'cmd_stru')

    # Define the status messages
    status_messages = status_messages

    # Define the type of directory listing this server is returning
    system = ('UNIX', 'L8')

    # comply with (possibly troublesome) RFC959 requirements
    # This is necessary to correctly run an active data connection
    # through a firewall that triggers on the source port (expected
    # to be 'L-1', or 20 in the normal case).
    bind_local_minus_one = 0

    restart_position = 0

    type_map = {'a':'ASCII', 'i':'Binary', 'e':'EBCDIC', 'l':'Binary'}

    type_mode_map = {'a':'t', 'i':'b', 'e':'b', 'l':'b'}


    def __init__(self, server, conn, addr, adj=None):
        super(FTPServerChannel, self).__init__(server, conn, addr, adj)

        self.port_addr = None  # The client's PORT address
        self.passive_listener = None  # The PASV listener
        self.client_dc = None  # The data connection

        self.transfer_mode = 'a'  # Have to default to ASCII :-|
        self.passive_mode = 0
        self.cwd = '/'
        self._rnfr = None

        self.username = ''
        self.credentials = None

        self.reply('SERVER_READY', self.server.server_name)


    def _getFileSystem(self):
        """Open the filesystem using the current credentials."""
        return self.server.fs_access.open(self.credentials)


    def cmd_abor(self, args):
        'See IFTPCommandHandler'
        assert self.async_mode
        self.reply('TRANSFER_ABORTED')
        self.abortPassive()
        self.abortData()


    def cmd_appe (self, args):
        'See IFTPCommandHandler'
        return self.cmd_stor(args, 'a')


    def cmd_cdup(self, args):
        'See IFTPCommandHandler'
        path = self._generatePath('../')
        if self._getFileSystem().type(path):
            self.cwd = path
            self.reply('SUCCESS_250', 'CDUP')
        else:
            self.reply('ERR_NO_FILE', path)


    def cmd_cwd(self, args):
        'See IFTPCommandHandler'
        path = self._generatePath(args)
        if self._getFileSystem().type(path) == 'd':
            self.cwd = path
            self.reply('SUCCESS_250', 'CWD')
        else:
            self.reply('ERR_NO_DIR', path)


    def cmd_dele(self, args):
        'See IFTPCommandHandler'
        if not args:
            self.reply('ERR_ARGS')
            return
        path = self._generatePath(args)

        try:
            self._getFileSystem().remove(path)
        except OSError, err:
            self.reply('ERR_DELETE_FILE', str(err))
        else:
            self.reply('SUCCESS_250', 'DELE')


    def cmd_help(self, args):
        'See IFTPCommandHandler'
        self.reply('HELP_START', flush=0)
        self.write('Help goes here somewhen.\r\n')
        self.reply('HELP_END')


    def cmd_list(self, args, long=1):
        'See IFTPCommandHandler'
        opts = ()
        if args.strip().startswith('-'):
            try:
                opts, args = getopt(args.split(), 'Llad')
            except GetoptError:
                self.reply('ERR_ARGS')
                return
            if len(args) > 1:
                self.reply('ERR_ARGS')
                return
            args = args and args[0] or ''

        fs = self._getFileSystem()
        path = self._generatePath(args)
        if not fs.type(path):
            self.reply('ERR_NO_DIR_FILE', path)
            return
        args = args.split()
        try:
            s = self.getList(
                args, long,
                directory=bool([opt for opt in opts if opt[0]=='-d'])
                )
        except OSError, err:
            self.reply('ERR_NO_LIST', str(err))
            return
        ok_reply = ('OPEN_DATA_CONN', self.type_map[self.transfer_mode])
        cdc = RETRChannel(self, ok_reply)
        try:
            cdc.write(s)
            cdc.close_when_done()
        except OSError, err:
            self.reply('ERR_NO_LIST', str(err))
            cdc.reported = True
            cdc.close_when_done()

    def getList(self, args, long=0, directory=0):
        # we need to scan the command line for arguments to '/bin/ls'...
        fs = self._getFileSystem()
        path_args = []
        for arg in args:
            if arg[0] != '-':
                path_args.append (arg)
            else:
                # ignore arguments
                pass
        if len(path_args) < 1:
            path = '.'
        else:
            path = path_args[0]

        path = self._generatePath(path)

        if fs.type(path) == 'd' and not directory:
            if long:
                file_list = map(ls, fs.ls(path))
            else:
                file_list = fs.names(path)
        else:
            if long:
                file_list = [ls(fs.lsinfo(path))]
            else:
                file_list = [posixpath.split(path)[1]]

        return '\r\n'.join(file_list) + '\r\n'


    def cmd_mdtm(self, args):
        'See IFTPCommandHandler'
        fs = self._getFileSystem()
        # We simply do not understand this non-standard extension to MDTM
        if len(args.split()) > 1:
            self.reply('ERR_ARGS')
            return
        path = self._generatePath(args)
        
        if fs.type(path) != 'f':
            self.reply('ERR_IS_NOT_FILE', path)
        else:
            mtime = fs.mtime(path)
            if mtime is not None:
                mtime = (mtime.year, mtime.month, mtime.day,
                         mtime.hour, mtime. minute, mtime.second)
            else:
                mtime = 0, 0, 0, 0, 0, 0

            self.reply('FILE_DATE', mtime)


    def cmd_mkd(self, args):
        'See IFTPCommandHandler'
        if not args:
            self.reply('ERR_ARGS')
            return
        path = self._generatePath(args)
        try:
            self._getFileSystem().mkdir(path)
        except OSError, err:
            self.reply('ERR_CREATE_DIR', str(err))
        else:
            self.reply('SUCCESS_257', 'MKD')


    def cmd_mode(self, args):
        'See IFTPCommandHandler'
        if len(args) == 1 and args in 'sS':
            self.reply('MODE_OK')
        else:
            self.reply('MODE_UNKNOWN')


    def cmd_nlst(self, args):
        'See IFTPCommandHandler'
        self.cmd_list(args, 0)


    def cmd_noop(self, args):
        'See IFTPCommandHandler'
        self.reply('SUCCESS_200', 'NOOP')


    def cmd_pass(self, args):
        'See IFTPCommandHandler'
        self.authenticated = 0
        password = args
        credentials = (self.username, password)
        try:
            self.server.fs_access.authenticate(credentials)
        except Unauthorized:
            self.reply('LOGIN_MISMATCH')
            self.close_when_done()
        else:
            self.credentials = credentials
            self.authenticated = 1
            self.reply('LOGIN_SUCCESS')


    def cmd_pasv(self, args):
        'See IFTPCommandHandler'
        assert self.async_mode
        # Kill any existing passive listener first.
        self.abortPassive()
        local_addr = self.getsockname()[0]
        self.passive_listener = PassiveListener(self, local_addr)
        port = self.passive_listener.port
        self.reply('PASV_MODE_MSG', (','.join(local_addr.split('.')),
                                     port/256,
                                     port%256 ) )


    def cmd_port(self, args):
        'See IFTPCommandHandler'
        info = args.split(',')
        ip = '.'.join(info[:4])
        port = int(info[4])*256 + int(info[5])
        # how many data connections at a time?
        # I'm assuming one for now...
        # TODO: we should (optionally) verify that the
        # ip number belongs to the client.  [wu-ftpd does this?]
        self.port_addr = (ip, port)
        self.reply('SUCCESS_200', 'PORT')


    def cmd_pwd(self, args):
        'See IFTPCommandHandler'
        self.reply('ALREADY_CURRENT', self.cwd)


    def cmd_quit(self, args):
        'See IFTPCommandHandler'
        self.reply('GOODBYE')
        self.close_when_done()


    def cmd_retr(self, args):
        'See IFTPCommandHandler'
        fs = self._getFileSystem()
        if not args:
            self.reply('CMD_UNKNOWN', 'RETR')
        path = self._generatePath(args)

        if not (fs.type(path) == 'f'):
            self.reply('ERR_IS_NOT_FILE', path)
            return

        start = 0
        if self.restart_position:
            start = self.restart_position
            self.restart_position = 0

        ok_reply = 'OPEN_CONN', (self.type_map[self.transfer_mode], path)
        cdc = RETRChannel(self, ok_reply)
        outstream = ApplicationOutputStream(cdc)

        try:
            fs.readfile(path, outstream, start)
            cdc.close_when_done()
        except OSError, err:
            self.reply('ERR_OPEN_READ', str(err))
            cdc.reported = True
            cdc.close_when_done()
        except IOError, err:
            self.reply('ERR_IO', str(err))
            cdc.reported = True
            cdc.close_when_done()


    def cmd_rest(self, args):
        'See IFTPCommandHandler'
        try:
            pos = int(args)
        except ValueError:
            self.reply('ERR_ARGS')
            return
        self.restart_position = pos
        self.reply('RESTART_TRANSFER', pos)


    def cmd_rmd(self, args):
        'See IFTPCommandHandler'
        if not args:
            self.reply('ERR_ARGS')
            return
        path = self._generatePath(args)
        try:
            self._getFileSystem().rmdir(path)
        except OSError, err:
            self.reply('ERR_DELETE_DIR', str(err))
        else:
            self.reply('SUCCESS_250', 'RMD')


    def cmd_rnfr(self, args):
        'See IFTPCommandHandler'
        path = self._generatePath(args)
        if self._getFileSystem().type(path):
            self._rnfr = path
            self.reply('READY_FOR_DEST')
        else:
            self.reply('ERR_NO_FILE', path)


    def cmd_rnto(self, args):
        'See IFTPCommandHandler'
        path = self._generatePath(args)
        if self._rnfr is None:
            self.reply('ERR_RENAME')
        try:
            self._getFileSystem().rename(self._rnfr, path)
        except OSError, err:
            self.reply('ERR_RENAME', (self._rnfr, path, str(err)))
        else:
            self.reply('SUCCESS_250', 'RNTO')
        self._rnfr = None


    def cmd_size(self, args):
        'See IFTPCommandHandler'
        path = self._generatePath(args)
        fs = self._getFileSystem()
        if fs.type(path) != 'f':
            self.reply('ERR_NO_FILE', path)
        else:
            self.reply('FILE_SIZE', fs.size(path))


    def cmd_stor(self, args, write_mode='w'):
        'See IFTPCommandHandler'
        if not args:
            self.reply('ERR_ARGS')
            return
        path = self._generatePath(args)

        start = 0
        if self.restart_position:
            self.start = self.restart_position
        mode = write_mode + self.type_mode_map[self.transfer_mode]

        if not self._getFileSystem().writable(path):
            self.reply('ERR_OPEN_WRITE', "Can't write file")
            return

        cdc = STORChannel(self, (path, mode, start))
        self.syncConnectData(cdc)
        self.reply('OPEN_CONN', (self.type_map[self.transfer_mode], path))


    def finishSTOR(self, buffer, (path, mode, start)):
        """Called by STORChannel when the client has sent all data."""
        assert not self.async_mode
        try:
            infile = buffer.getfile()
            infile.seek(0)
            self._getFileSystem().writefile(path, infile, start,
                                            append=(mode[0]=='a'))
        except OSError, err:
            self.reply('ERR_OPEN_WRITE', str(err))
        except IOError, err:
            self.reply('ERR_IO', str(err))
        except:
            self.exception()
        else:
            self.reply('TRANS_SUCCESS')


    def cmd_stru(self, args):
        'See IFTPCommandHandler'
        if len(args) == 1 and args in 'fF':
            self.reply('STRU_OK')
        else:
            self.reply('STRU_UNKNOWN')


    def cmd_syst(self, args):
        'See IFTPCommandHandler'
        self.reply('SERVER_TYPE', self.system)


    def cmd_type(self, args):
        'See IFTPCommandHandler'
        # ascii, ebcdic, image, local <byte size>
        args = args.split()
        t = args[0].lower()
        # no support for EBCDIC
        # if t not in ['a','e','i','l']:
        if t not in ['a','i','l']:
            self.reply('ERR_ARGS')
        elif t == 'l' and (len(args) > 2 and args[2] != '8'):
            self.reply('WRONG_BYTE_SIZE')
        else:
            self.transfer_mode = t
            self.reply('TYPE_SET_OK', self.type_map[t])


    def cmd_user(self, args):
        'See IFTPCommandHandler'
        self.authenticated = 0
        if len(args) > 1:
            self.username = args
            self.reply('PASS_REQUIRED')
        else:
            self.reply('ERR_ARGS')

    ############################################################

    def _generatePath(self, args):
        """Convert relative paths to absolute paths."""
        # We use posixpath even on non-Posix platforms because we don't want
        # slashes converted to backslashes.
        path = posixpath.join(self.cwd, args)
        return posixpath.normpath(path)

    def syncConnectData(self, cdc):
        """Calls asyncConnectData in the asynchronous thread."""
        the_trigger.pull_trigger(lambda: self.asyncConnectData(cdc))

    def asyncConnectData(self, cdc):
        """Starts connecting the data channel.

        This is a little complicated because the data connection might
        be established already (in passive mode) or might be
        established in the near future (in port or passive mode.)  If
        the connection has already been established,
        self.passive_listener already has a socket and is waiting for
        a call to connectData().  If the connection has not been
        established in passive mode, the passive listener will
        remember the data channel and send it when it's ready.  In port
        mode, this method tells the data connection to connect.
        """
        self.abortData()
        self.client_dc = cdc
        if self.passive_listener is not None:
            # Connect via PASV
            self.passive_listener.connectData(cdc)
        if self.port_addr:
            # Connect via PORT
            a = self.port_addr
            self.port_addr = None
            cdc.connectPort(a)

    def connectedPassive(self):
        """Accepted a passive connection."""
        self.passive_listener = None

    def abortPassive(self):
        """Close the passive listener."""
        if self.passive_listener is not None:
            self.passive_listener.abort()
            self.passive_listener = None

    def abortData(self):
        """Close the data connection."""
        if self.client_dc is not None:
            self.client_dc.abort()
            self.client_dc = None

    def closedData(self):
        self.client_dc = None

    def close(self):
        # Make sure the passive listener and active client DC get closed.
        self.abortPassive()
        self.abortData()
        LineServerChannel.close(self)



def ls(ls_info):
    """Formats a directory entry similarly to the 'ls' command.
    """

    info = {
        'owner_name': 'na',
        'owner_readable': True,
        'owner_writable': True,
        'group_name': "na",
        'group_readable': True,
        'group_writable': True,
        'other_readable': False,
        'other_writable': False,
        'nlinks': 1,
        'size': 0,
        }

    if ls_info['type'] == 'd':
        info['owner_executable'] = True
        info['group_executable'] = True
        info['other_executable'] = True
    else:
        info['owner_executable'] = False
        info['group_executable'] = False
        info['other_executable'] = False

    info.update(ls_info)

    mtime = info.get('mtime')
    if mtime is not None:
        if date.today() - mtime.date() > timedelta(days=180):
            mtime = mtime.strftime('%b %d  %Y')
        else:
            mtime = mtime.strftime('%b %d %H:%M')
    else:
        mtime = "Jan 02  0000"

    return "%s%s%s%s%s%s%s%s%s%s %3d %-8s %-8s %8d %s %s" % (
        info['type'] == 'd' and 'd' or '-',
        info['owner_readable'] and 'r' or '-',
        info['owner_writable'] and 'w' or '-',
        info['owner_executable'] and 'x' or '-',
        info['group_readable'] and 'r' or '-',
        info['group_writable'] and 'w' or '-',
        info['group_executable'] and 'x' or '-',
        info['other_readable'] and 'r' or '-',
        info['other_writable'] and 'w' or '-',
        info['other_executable'] and 'x' or '-',
        info['nlinks'],
        info['owner_name'],
        info['group_name'],
        info['size'],
        mtime,
        info['name'],
        )


class PassiveListener(asyncore.dispatcher):
    """This socket accepts a data connection, used when the server has
       been placed in passive mode.  Although the RFC implies that we
       ought to be able to use the same listener over and over again,
       this presents a problem: how do we shut it off, so that we are
       accepting connections only when we expect them?  [we can't]

       wuftpd, and probably all the other servers, solve this by
       allowing only one connection to hit this listener.  They then
       close it.  Any subsequent data-connection command will then try
       for the default port on the client side [which is of course
       never there].  So the 'always-send-PORT/PASV' behavior seems
       required.

       Another note: wuftpd will also be listening on the channel as
       soon as the PASV command is sent.  It does not wait for a data
       command first.
       """

    def __init__ (self, control_channel, local_addr):
        asyncore.dispatcher.__init__ (self)
        self.control_channel = control_channel
        self.accepted = None  # The accepted socket address
        self.client_dc = None  # The data connection to accept the socket
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.closed = False
        # bind to an address on the interface where the
        # control connection is connected.
        self.bind((local_addr, 0))
        self.port = self.getsockname()[1]
        self.listen(1)

    def log (self, *ignore):
        pass

    def abort(self):
        """Abort the passive listener."""
        if not self.closed:
            self.closed = True
            self.close()
        if self.accepted is not None:
            self.accepted.close()

    def handle_accept (self):
        """Accept a connection from the client.

        For some reason, sometimes accept() returns None instead of a
        socket.  This code ignores that case.
        """
        v = self.accept()
        if v is None:
            return
        self.accepted, addr = v
        if self.accepted is None:
            return
        self.accepted.setblocking(0)
        self.closed = True
        self.close()
        if self.client_dc is not None:
            self.connectData(self.client_dc)

    def connectData(self, cdc):
        """Sends the connection to the data channel.

        If the connection has not yet been made, sends the connection
        when it becomes available.
        """
        if self.accepted is not None:
            cdc.set_socket(self.accepted)
            # Note that this method will be called twice, once by the
            # control channel, and once by handle_accept, and the two
            # calls may come in either order.  If handle_accept calls
            # first, we don't want to call set_socket() on the data
            # connection twice, so set self.accepted = None to keep a
            # record that the data connection already has the socket.
            self.accepted = None
            self.control_channel.connectedPassive()
        else:
            self.client_dc = cdc


class FTPDataChannel(DualModeChannel):
    """Base class for FTP data connections.

    Note that data channels are always in async mode.
    """
    
    def __init__ (self, control_channel):
        self.control_channel = control_channel
        self.reported = False
        self.closed = False
        DualModeChannel.__init__(self, None, None, control_channel.adj)

    def connectPort(self, client_addr):
        """Connect to a port on the client"""
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        #if bind_local_minus_one:
        #    self.bind(('', self.control_channel.server.port - 1))
        try:
            self.connect(client_addr)
        except socket.error:
            self.report('NO_DATA_CONN')

    def abort(self):
        """Abort the data connection without reporting."""
        self.reported = True
        if not self.closed:
            self.closed = True
            self.close()

    def report(self, *reply_args):
        """Reports the result of the data transfer."""
        self.reported = True
        if self.control_channel is not None:
            self.control_channel.reply(*reply_args)

    def reportDefault(self):
        """Provide a default report on close."""
        pass

    def close(self):
        """Notifies the control channel when the data connection closes."""
        c = self.control_channel
        try:
            if c is not None and c.connected and not self.reported:
                self.reportDefault()
        finally:
            self.control_channel = None
            DualModeChannel.close(self)
            if c is not None:
                c.closedData()


class STORChannel(FTPDataChannel):
    """Channel for uploading one file from client to server"""

    complete_transfer = 0
    _fileno = None  # provide a default for asyncore.dispatcher._fileno

    def __init__ (self, control_channel, finish_args):
        self.finish_args = finish_args
        self.inbuf = OverflowableBuffer(control_channel.adj.inbuf_overflow)
        FTPDataChannel.__init__(self, control_channel)
        # Note that this channel starts in async mode.

    def writable (self):
        return 0

    def handle_connect (self):
        pass

    def received (self, data):
        if data:
            self.inbuf.append(data)

    def handle_close (self):
        """Client closed, indicating EOF."""
        c = self.control_channel
        task = FinishSTORTask(c, self.inbuf, self.finish_args)
        self.complete_transfer = 1
        self.close()
        c.queue_task(task)

    def reportDefault(self):
        if not self.complete_transfer:
            self.report('TRANSFER_ABORTED')
        # else the transfer completed and FinishSTORTask will
        # provide a complete reply through finishSTOR().


class FinishSTORTask(object):
    """Calls control_channel.finishSTOR() in an application thread.

    This task executes after the client has finished uploading.
    """

    implements(ITask)

    def __init__(self, control_channel, inbuf, finish_args):
        self.control_channel = control_channel
        self.inbuf = inbuf
        self.finish_args = finish_args

    def service(self):
        """Called to execute the task.
        """
        close_on_finish = 0
        c = self.control_channel
        try:
            try:
                c.finishSTOR(self.inbuf, self.finish_args)
            except socket.error:
                close_on_finish = 1
                if c.adj.log_socket_errors:
                    raise
        finally:
            if close_on_finish:
                c.close_when_done()

    def cancel(self):
        'See ITask'
        self.control_channel.close_when_done()

    def defer(self):
        'See ITask'
        pass


class RETRChannel(FTPDataChannel):
    """Channel for downloading one file from server to client

    Also used for directory listings.
    """

    opened = 0
    _fileno = None  # provide a default for asyncore.dispatcher._fileno

    def __init__ (self, control_channel, ok_reply_args):
        self.ok_reply_args = ok_reply_args
        FTPDataChannel.__init__(self, control_channel)

    def _open(self):
        """Signal the client to open the connection."""
        self.opened = 1
        self.control_channel.reply(*self.ok_reply_args)
        self.control_channel.asyncConnectData(self)

    def write(self, data):
        if self.control_channel is None:
            raise IOError('Client FTP connection closed')
        if not self.opened:
            self._open()
        return FTPDataChannel.write(self, data)

    def readable(self):
        return not self.connected

    def handle_read(self):
        # This may be called upon making the connection.
        try:
            self.recv(1)
        except socket.error:
            # The connection failed.
            self.report('NO_DATA_CONN')
            self.close()

    def handle_connect(self):
        pass

    def handle_comm_error(self):
        self.report('TRANSFER_ABORTED')
        self.close()

    def reportDefault(self):
        if not len(self.outbuf):
            # All data transferred
            if not self.opened:
                # Zero-length file
                self._open()
            self.report('TRANS_SUCCESS')
        else:
            # Not all data transferred
            self.report('TRANSFER_ABORTED')


class ApplicationOutputStream(object):
    """Provide stream output to RETRChannel.

    Maps close() to close_when_done().
    """

    def __init__(self, retr_channel):
        self.write = retr_channel.write
        self.flush = retr_channel.flush
        self.close = retr_channel.close_when_done


class FTPServer(ServerBase):
    """Generic FTP Server"""

    channel_class = FTPServerChannel
    SERVER_IDENT = 'zope.server.ftp'


    def __init__(self, ip, port, fs_access, *args, **kw):

        assert IFileSystemAccess.providedBy(fs_access)
        self.fs_access = fs_access

        super(FTPServer, self).__init__(ip, port, *args, **kw)
