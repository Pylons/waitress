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

import os
import os.path
import socket
import threading
import time

from waitress import trigger
from waitress.adjustments import Adjustments
from waitress.channel import HTTPChannel
from waitress.compat import IPPROTO_IPV6, IPV6_V6ONLY
from waitress.task import ThreadedTaskDispatcher, in_task_thread
from waitress.utilities import cleanup_unix_socket, logger

from . import wasyncore
from .proxy_headers import proxy_headers_middleware


def create_server(
    application,
    map=None,
    _start=True,  # test shim
    _sock=None,  # test shim
    _dispatcher=None,  # test shim
    **kw,  # adjustments
):
    """
    if __name__ == '__main__':
        server = create_server(app)
        server.run()
    """
    if application is None:
        raise ValueError(
            'The "app" passed to ``create_server`` was ``None``.  You forgot '
            "to return a WSGI app within your application."
        )
    adj = Adjustments(**kw)

    if map is None:  # pragma: nocover
        map = {}

    dispatcher = _dispatcher
    if dispatcher is None:
        dispatcher = ThreadedTaskDispatcher()

    # Everything below here may fail: a socket may not be bindable, a Unix
    # socket path may not be writable, etc. Whatever we managed to create
    # before that happened needs to be cleaned up again, otherwise we leave
    # behind open sockets and running threads that the caller has no way of
    # getting a reference to. See
    # https://github.com/Pylons/waitress/issues/480
    servers = []

    try:
        if adj.unix_socket and hasattr(socket, "AF_UNIX"):
            sockinfo = (socket.AF_UNIX, socket.SOCK_STREAM, None, None)
            servers.append(
                UnixWSGIServer(
                    application,
                    map,
                    _start,
                    _sock,
                    dispatcher=dispatcher,
                    adj=adj,
                    sockinfo=sockinfo,
                )
            )
        else:
            if not adj.sockets:
                for sockinfo in adj.listen:
                    # When TcpWSGIServer is called, it registers itself in the
                    # map. This side-effect is all we need it for, so we don't
                    # return it to the user, we only hold on to it so that we
                    # are able to clean it up if a later server fails to start.
                    servers.append(
                        TcpWSGIServer(
                            application,
                            map,
                            _start,
                            _sock,
                            dispatcher=dispatcher,
                            adj=adj,
                            sockinfo=sockinfo,
                        )
                    )

            for sock in adj.sockets:
                sockinfo = (sock.family, sock.type, sock.proto, sock.getsockname())
                if sock.family == socket.AF_INET or sock.family == socket.AF_INET6:
                    servers.append(
                        TcpWSGIServer(
                            application,
                            map,
                            _start,
                            sock,
                            dispatcher=dispatcher,
                            adj=adj,
                            bind_socket=False,
                            sockinfo=sockinfo,
                        )
                    )
                elif hasattr(socket, "AF_UNIX") and sock.family == socket.AF_UNIX:
                    servers.append(
                        UnixWSGIServer(
                            application,
                            map,
                            _start,
                            sock,
                            dispatcher=dispatcher,
                            adj=adj,
                            bind_socket=False,
                            sockinfo=sockinfo,
                        )
                    )

        if not servers:
            raise ValueError(
                "There are no sockets to listen on, both 'listen' and 'sockets' "
                "are empty."
            )

        effective_listen = [(s.effective_host, s.effective_port) for s in servers]

        if _dispatcher is None:
            # Only start the worker threads once we know every socket is
            # usable, so that a failure above never leaves threads behind.
            dispatcher.set_thread_count(adj.threads)
    except BaseException:
        for server in servers:
            server.close()
        dispatcher.shutdown(timeout=adj.shutdown_timeout)
        raise

    # We are running a single server, so we can just return it, this saves us
    # from having to create one more object
    if len(servers) == 1:
        # In this case we have no need to use a MultiSocketServer. Hand the
        # task dispatcher over to the server we return, it is the only handle
        # the caller has on it and closing it needs to stop the threads.
        servers[0].own_task_dispatcher = True

        return servers[0]

    log_info = servers[0].log_info
    # Return a class that has a utility function to print out the sockets it's
    # listening on, and has a .run() function. All of the TcpWSGIServers
    # registered themselves in the map above.
    return MultiSocketServer(
        map, adj, effective_listen, dispatcher, log_info, servers=servers
    )


def _drain(servers, map, adj, asyncore=wasyncore):
    """
    Stop accepting new connections and then run the main loop until every
    connection that is still open has been dealt with.

    The task threads hand their output back to the main loop, and rely on the
    trigger to wake it up when they do. That means we can't stop the loop or
    tear the trigger down the moment we are asked to shut down: doing so drops
    the responses of everything that was in flight on the floor. Instead we
    keep polling until the channels have written out what they had left and
    closed themselves, giving up after ``adj.shutdown_timeout`` seconds.
    """

    # Close the listening sockets first. This releases the port right away and
    # makes sure no new connections show up while we are draining the ones we
    # already have. Everything else, in particular the trigger, is left alone.
    for server in servers:
        server.stop_accepting()

    if adj.shutdown_timeout <= 0:
        return

    deadline = time.time() + adj.shutdown_timeout

    try:
        while True:
            channels = {}

            for server in servers:
                channels.update(server.active_channels)

            if not channels:
                break

            now = time.time()

            if now >= deadline:
                logger.warning(
                    "Graceful shutdown timed out with %d connection(s) still "
                    "open, closing them now",
                    len(channels),
                )

                break

            for channel in channels.values():
                # Stop taking on any new work, we only want to finish what we
                # already have.
                channel.draining = True

                # A channel that is not waiting on a request to be serviced has
                # nothing left to do for us, so let it flush whatever output it
                # still has queued up and then close. Channels that do have
                # requests outstanding are left running until their task thread
                # is done with them, at which point they end up here too.
                with channel.requests_lock:
                    if not channel.requests:
                        channel.close_when_flushed = True

            asyncore.loop(
                timeout=min(adj.asyncore_loop_timeout, deadline - now),
                map=map,
                use_poll=adj.asyncore_use_poll,
                count=1,
            )
    except (SystemExit, KeyboardInterrupt):
        # Interrupted a second time, the user is not interested in waiting for
        # a clean shutdown anymore.
        logger.warning("Graceful shutdown interrupted, closing connections now")


class _ServerRunner:
    """
    Running the main loop, and stopping it again, shared by both flavours of
    server. Subclasses provide ``_map``, ``adj``, ``pull_trigger()`` and
    ``graceful_shutdown()``.
    """

    asyncore = wasyncore  # test shim

    # Set by stop() to ask the main loop to return. Only ever written from
    # outside the thread running the loop, hence the flag rather than a lock.
    _stopping = False

    # The thread start() is running the main loop in, if there is one.
    _thread = None

    def run(self):
        """
        Run the main loop until the server is asked to stop, then shut it down
        gracefully. This blocks until the shutdown has completed.

        The server stops when :meth:`stop` is called, when the process is
        interrupted, or when a ``SystemExit`` is raised in this thread.
        """

        try:
            while self._map and not self._stopping:
                self.asyncore.loop(
                    timeout=self.adj.asyncore_loop_timeout,
                    map=self._map,
                    use_poll=self.adj.asyncore_use_poll,
                    count=1,
                )
        except (SystemExit, KeyboardInterrupt):
            pass

        self.graceful_shutdown()

    def start(self):
        """
        Run the main loop in a background thread and return straight away.

        The server is listening by the time this returns, so
        ``effective_host``/``effective_port`` can be used to find out which
        address it ended up on when asking for port ``0``.

        The thread is a daemon thread, so it won't keep the process alive by
        itself. Call :meth:`stop` to shut the server down again.
        """

        if self._thread is not None:
            raise RuntimeError("This server has already been started")

        self._thread = threading.Thread(
            target=self.run, name="waitress-main", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=None):
        """
        Ask the server to shut down gracefully, see :meth:`graceful_shutdown`.

        Unlike the other shutdown methods this one may be called from any
        thread, including from within the WSGI application itself: it only
        signals the main loop, which then does the work.

        If the server was started with :meth:`start`, this waits up to
        ``timeout`` seconds (forever by default) for it to finish. Returns
        ``True`` if the server has completely stopped by the time it returns,
        and ``False`` if it is still busy finishing up.

        It never waits when called from a thread the shutdown itself has to
        wait for, such as from the WSGI application: doing so would deadlock.
        In that case it returns ``False`` and the server stops as soon as the
        request that called it has been answered.
        """

        self._stopping = True
        # Wake the main loop up so that it notices, rather than having to wait
        # for its select() to time out.
        self.pull_trigger()

        thread, self._thread = self._thread, None

        if thread is None or thread is threading.current_thread() or in_task_thread():
            # Either nobody is running the loop for us, or we are being called
            # from a thread the shutdown is going to wait on, which will get
            # around to it once it is back in control.
            return False

        thread.join(timeout)

        return not thread.is_alive()


# This class is only ever used if we have multiple listen sockets. It allows
# the serve() API to call .run() which starts the wasyncore loop, and catches
# SystemExit/KeyboardInterrupt so that it can attempt to cleanly shut down.
class MultiSocketServer(_ServerRunner):
    def __init__(
        self,
        map=None,
        adj=None,
        effective_listen=None,
        dispatcher=None,
        log_info=None,
        servers=None,
    ):
        self.adj = adj
        self.map = map
        self.effective_listen = effective_listen
        self.task_dispatcher = dispatcher
        self.log_info = log_info

        if servers is None:
            # Not passed the listening sockets we are in charge of, so pick
            # them back out of the socket map.
            servers = [s for s in map.values() if isinstance(s, BaseWSGIServer)]

        self.servers = servers

    @property
    def _map(self):
        # The socket map is called `map` here for backwards compatibility, but
        # _ServerRunner shares its name with wasyncore.dispatcher's.
        return self.map

    def print_listen(self, format_str):  # pragma: nocover
        for l in self.effective_listen:
            l = list(l)

            if ":" in l[0]:
                l[0] = f"[{l[0]}]"

            self.log_info(format_str.format(*l))

    def pull_trigger(self):
        for server in self.servers:
            server.pull_trigger()

    def graceful_shutdown(self):
        """
        Stop accepting new connections, let the requests that are already being
        serviced finish, and then shut the server down. See ``_drain``.
        """
        _drain(self.servers, self.map, self.adj, self.asyncore)
        self.close()

    def close(self):
        self.task_dispatcher.shutdown(timeout=self.adj.shutdown_timeout)
        wasyncore.close_all(self.map)


class BaseWSGIServer(_ServerRunner, wasyncore.dispatcher):
    channel_class = HTTPChannel
    next_channel_cleanup = 0
    socketmod = socket  # test shim
    in_connection_overflow = False
    trigger = None
    # Whether closing this server should also shut down the task dispatcher.
    # This is only true when nobody else holds a reference to the dispatcher,
    # in which case we would otherwise leave its threads running forever.
    own_task_dispatcher = False

    def __init__(
        self,
        application,
        map=None,
        _start=True,  # test shim
        _sock=None,  # test shim
        dispatcher=None,  # dispatcher
        adj=None,  # adjustments
        sockinfo=None,  # opaque object
        bind_socket=True,
        **kw,
    ):
        if adj is None:
            adj = Adjustments(**kw)

        if adj.trusted_proxy or adj.clear_untrusted_proxy_headers:
            # wrap the application to deal with proxy headers
            # we wrap it here because webtest subclasses the TcpWSGIServer
            # directly and thus doesn't run any code that's in create_server
            application = proxy_headers_middleware(
                application,
                trusted_proxy=adj.trusted_proxy,
                trusted_proxy_count=adj.trusted_proxy_count,
                trusted_proxy_headers=adj.trusted_proxy_headers,
                clear_untrusted=adj.clear_untrusted_proxy_headers,
                log_untrusted=adj.log_untrusted_proxy_headers,
                logger=self.logger,
            )

        if map is None:
            # use a nonglobal socket map by default to hopefully prevent
            # conflicts with apps and libs that use the wasyncore global socket
            # map ala https://github.com/Pylons/waitress/issues/63
            map = {}
        if sockinfo is None:
            sockinfo = adj.listen[0]

        self.sockinfo = sockinfo
        self.family = sockinfo[0]
        self.socktype = sockinfo[1]
        self.application = application
        self.adj = adj
        self.server_name = adj.server_name
        self.active_channels = {}

        # Initialise the wasyncore dispatcher before acquiring anything else so
        # that self.close() is always safe to call from the error handling
        # below, even if we never got as far as creating a socket.
        self.asyncore.dispatcher.__init__(self, _sock, map=map)

        if dispatcher is None:
            # Nobody else knows about this dispatcher, so we are the ones that
            # have to shut it down again when we get closed.
            dispatcher = ThreadedTaskDispatcher()
            self.own_task_dispatcher = True

        self.task_dispatcher = dispatcher

        try:
            self.trigger = trigger.trigger(map)

            if _sock is None:
                self.create_socket(self.family, self.socktype)
                if self.family == socket.AF_INET6:  # pragma: nocover
                    self.socket.setsockopt(IPPROTO_IPV6, IPV6_V6ONLY, 1)

            self.set_reuse_addr()

            if bind_socket:
                self.bind_server_socket()

            self.effective_host, self.effective_port = self.getsockname()

            if self.own_task_dispatcher:
                # Wait until we know that we have a working socket before
                # starting any threads, otherwise a failure above would leave
                # them running with no way to reach them.
                self.task_dispatcher.set_thread_count(self.adj.threads)

            if _start:
                self.accept_connections()
        except BaseException:
            # Don't leak the trigger, the socket, our entry in the socket map,
            # or the task dispatcher's threads if we can't finish starting up.
            # See https://github.com/Pylons/waitress/issues/480
            self.close()
            raise

    def bind_server_socket(self):
        raise NotImplementedError  # pragma: no cover

    def getsockname(self):
        raise NotImplementedError  # pragma: no cover

    def accept_connections(self):
        self.accepting = True
        self.socket.listen(self.adj.backlog)  # Get around asyncore NT limit

    def add_task(self, task):
        self.task_dispatcher.add_task(task)

    def readable(self):
        now = time.time()
        if now >= self.next_channel_cleanup:
            self.next_channel_cleanup = now + self.adj.cleanup_interval
            self.maintenance(now)

        if self.accepting:
            if (
                not self.in_connection_overflow
                and len(self._map) >= self.adj.connection_limit
            ):
                self.in_connection_overflow = True
                self.logger.warning(
                    "total open connections reached the connection limit, "
                    "no longer accepting new connections"
                )
            elif (
                self.in_connection_overflow
                and len(self._map) < self.adj.connection_limit
            ):
                self.in_connection_overflow = False
                self.logger.info(
                    "total open connections dropped below the connection limit, "
                    "listening again"
                )
            return not self.in_connection_overflow
        return False

    def writable(self):
        return False

    def handle_read(self):
        pass

    def handle_connect(self):
        pass

    def handle_accept(self):
        try:
            v = self.accept()
            if v is None:
                return
            conn, addr = v
            self.set_socket_options(conn)
        except OSError:
            # Linux: On rare occasions we get a bogus socket back from
            # accept.  socketmodule.c:makesockaddr complains that the
            # address family is unknown.  We don't want the whole server
            # to shut down because of this.
            # macOS: On occasions when the remote has already closed the socket
            # before we got around to accepting it, when we try to set the
            # socket options it will fail. So instead just we log the error and
            # continue
            if self.adj.log_socket_errors:
                self.logger.warning("server accept() threw an exception", exc_info=True)
            return
        addr = self.fix_addr(addr)
        self.channel_class(self, conn, addr, self.adj, map=self._map)

    def graceful_shutdown(self):
        """
        Stop accepting new connections, let the requests that are already being
        serviced finish, and then shut the server down. See ``_drain``.
        """
        _drain([self], self._map, self.adj, self.asyncore)
        self.close()

    def stop_accepting(self):
        """
        Close the listening socket, but leave everything else running.

        No new connections are accepted after this, while the channels that are
        already open, the trigger the task threads use to wake up the main loop,
        and the task dispatcher all keep working.
        """
        wasyncore.dispatcher.close(self)

    def pull_trigger(self):
        self.trigger.pull_trigger()

    def set_socket_options(self, conn):
        pass

    def fix_addr(self, addr):
        return addr

    def maintenance(self, now):
        """
        Closes channels that have not had any activity in a while.

        The timeout is configured through adj.channel_timeout (seconds).
        """
        cutoff = now - self.adj.channel_timeout
        for channel in self.active_channels.values():
            if (not channel.requests) and channel.last_activity < cutoff:
                channel.will_close = True

    def print_listen(self, format_str):  # pragma: no cover
        self.log_info(format_str.format(self.effective_host, self.effective_port))

    def close(self):
        # Stop the worker threads first, they may still be holding on to a
        # channel and they need the trigger to hand their output back to us.
        if self.own_task_dispatcher:
            self.task_dispatcher.shutdown(timeout=self.adj.shutdown_timeout)

        # Anything still connected at this point is not going to get an answer
        # from us, drop it. Note that we deliberately don't use close_all() on
        # the whole map here: it would call back into this method.
        for channel in list(self.active_channels.values()):
            channel.handle_close()

        # self.trigger is None only when we are being closed by an __init__
        # that failed before it got that far.
        if self.trigger is not None:
            self.trigger.close()

        return wasyncore.dispatcher.close(self)


class TcpWSGIServer(BaseWSGIServer):
    def bind_server_socket(self):
        _, _, _, sockaddr = self.sockinfo
        self.bind(sockaddr)

    def getsockname(self):
        # Return the IP address, port as numeric
        return self.socketmod.getnameinfo(
            self.socket.getsockname(),
            self.socketmod.NI_NUMERICHOST | self.socketmod.NI_NUMERICSERV,
        )

    def set_socket_options(self, conn):
        for level, optname, value in self.adj.socket_options:
            conn.setsockopt(level, optname, value)


if hasattr(socket, "AF_UNIX"):

    class UnixWSGIServer(BaseWSGIServer):
        def __init__(
            self,
            application,
            map=None,
            _start=True,  # test shim
            _sock=None,  # test shim
            dispatcher=None,  # dispatcher
            adj=None,  # adjustments
            sockinfo=None,  # opaque object
            **kw,
        ):
            if sockinfo is None:
                sockinfo = (socket.AF_UNIX, socket.SOCK_STREAM, None, None)

            super().__init__(
                application,
                map=map,
                _start=_start,
                _sock=_sock,
                dispatcher=dispatcher,
                adj=adj,
                sockinfo=sockinfo,
                **kw,
            )

        def bind_server_socket(self):
            cleanup_unix_socket(self.adj.unix_socket)
            self.bind(self.adj.unix_socket)
            if os.path.exists(self.adj.unix_socket):
                os.chmod(self.adj.unix_socket, self.adj.unix_socket_perms)

        def getsockname(self):
            return ("unix", self.socket.getsockname())

        def fix_addr(self, addr):
            return ("localhost", None)


# Compatibility alias.
WSGIServer = TcpWSGIServer
