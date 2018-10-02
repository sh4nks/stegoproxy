import os
import socket

from http.server import HTTPServer
from socketserver import ThreadingMixIn, ForkingMixIn

from stego_proxy._compat import WIN


LISTEN_QUEUE = 128
can_open_by_fd = not WIN and hasattr(socket, "fromfd")
can_fork = hasattr(os, "fork")


def _log(*args):
    print(*args)


def select_address_family(host, port):
    """Return ``AF_INET4``, ``AF_INET6``, or ``AF_UNIX`` depending on
    the host and port."""
    if host.startswith("unix://"):
        return socket.AF_UNIX
    elif ":" in host and hasattr(socket, "AF_INET6"):
        return socket.AF_INET6
    return socket.AF_INET


def get_sockaddr(host, port, family):
    """Return a fully qualified socket address that can be passed to
    :func:`socket.bind`."""
    if family == socket.AF_UNIX:
        return host.split("://", 1)[1]
    try:
        res = socket.getaddrinfo(
            host, port, family, socket.SOCK_STREAM, socket.SOL_TCP
        )
    except socket.gaierror:
        return host, port
    return res[0][4]


class BaseWSGIServer(HTTPServer, object):
    """Simple single-threaded, single-process WSGI server."""

    multithread = False
    multiprocess = False
    request_queue_size = LISTEN_QUEUE

    def __init__(self, host, port, handler, passthrough_errors=False, fd=None):
        self.address_family = select_address_family(host, port)

        if fd is not None:
            real_sock = socket.fromfd(
                fd, self.address_family, socket.SOCK_STREAM
            )
            port = 0

        server_address = get_sockaddr(host, int(port), self.address_family)

        # remove socket file if it already exists
        if self.address_family == socket.AF_UNIX and os.path.exists(
            server_address
        ):
            os.unlink(server_address)

        HTTPServer.__init__(self, server_address, handler)

        self.passthrough_errors = passthrough_errors
        self.shutdown_signal = False
        self.host = host
        self.port = self.socket.getsockname()[1]

        # Patch in the original socket.
        if fd is not None:
            self.socket.close()
            self.socket = real_sock
            self.server_address = self.socket.getsockname()

    def log(self, type, message, *args):
        _log(type, message, *args)

    def serve_forever(self):
        self.shutdown_signal = False
        try:
            HTTPServer.serve_forever(self)
        except KeyboardInterrupt:
            pass
        finally:
            self.server_close()

    def handle_error(self, request, client_address):
        if self.passthrough_errors:
            raise
        return HTTPServer.handle_error(self, request, client_address)

    def get_request(self):
        con, info = self.socket.accept()
        return con, info


class ThreadedWSGIServer(ThreadingMixIn, BaseWSGIServer):

    """A WSGI server that does threading."""

    multithread = True
    daemon_threads = True


class ForkingWSGIServer(ForkingMixIn, BaseWSGIServer):

    """A WSGI server that does forking."""

    multiprocess = True

    def __init__(
        self,
        host,
        port,
        app,
        processes=40,
        handler=None,
        passthrough_errors=False,
        ssl_context=None,
        fd=None,
    ):
        if not can_fork:
            raise ValueError("Your platform does not support forking.")
        BaseWSGIServer.__init__(
            self, host, port, app, handler, passthrough_errors, ssl_context, fd
        )
        self.max_children = processes


def make_server(
    host=None,
    port=None,
    threaded=False,
    processes=1,
    request_handler=None,
    passthrough_errors=False,
    fd=None,
):
    """Create a new server instance that is either threaded, or forks
    or just processes one request after another.
    """
    if threaded and processes > 1:
        raise ValueError(
            "cannot have a multithreaded and " "multi process server."
        )
    elif threaded:
        return ThreadedWSGIServer(
            host, port, request_handler, passthrough_errors, fd=fd
        )
    elif processes > 1:
        return ForkingWSGIServer(
            host, port, processes, request_handler, passthrough_errors, fd=fd
        )
    else:
        return BaseWSGIServer(
            host, port, request_handler, passthrough_errors, fd=fd
        )


def is_running_from_reloader():
    """Checks if the application is running from within the Werkzeug
    reloader subprocess.
    .. versionadded:: 0.10
    """
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def run_simple(
    hostname,
    port,
    request_handler,
    use_reloader=False,
    use_evalex=True,
    extra_files=None,
    reloader_interval=1,
    reloader_type="auto",
    threaded=False,
    processes=1,
    passthrough_errors=False,
):
    """Start a WSGI application. Optional features include a reloader,
    multithreading and fork support.

    :param hostname: The host to bind to, for example ``'localhost'``.
        If the value is a path that starts with ``unix://`` it will bind
        to a Unix socket instead of a TCP socket..
    :param port: The port for the server.  eg: ``8080``
    :param use_reloader: should the server automatically restart the python
                         process if modules were changed?
    :param use_evalex: should the exception evaluation feature be enabled?
    :param extra_files: a list of files the reloader should watch
                        additionally to the modules.  For example configuration
                        files.
    :param reloader_interval: the interval for the reloader in seconds.
    :param reloader_type: the type of reloader to use.  The default is
                          auto detection.  Valid values are ``'stat'`` and
                          ``'watchdog'``. See :ref:`reloader` for more
                          information.
    :param threaded: should the process handle each request in a separate
                     thread?
    :param processes: if greater than 1 then handle each request in a new process
                      up to this maximum number of concurrent processes.
    :param request_handler: optional parameter that can be used to replace
                            the default one.  You can use this to replace it
                            with a different
                            :class:`~BaseHTTPServer.BaseHTTPRequestHandler`
                            subclass.
    :param passthrough_errors: set this to `True` to disable the error catching.
                               This means that the server will die on errors but
                               it can be useful to hook debuggers in (pdb etc.)
    """
    if not isinstance(port, int):
        raise TypeError("port must be an integer")

    def log_startup(sock):
        display_hostname = hostname not in ("", "*") and hostname or "localhost"
        quit_msg = "(Press CTRL+C to quit)"
        if sock.family is socket.AF_UNIX:
            _log("info", " * Running on %s %s", display_hostname, quit_msg)
        else:
            if ":" in display_hostname:
                display_hostname = "[%s]" % display_hostname
            port = sock.getsockname()[1]
            _log(
                "info",
                " * Running on http://%s:%d/ %s",
                display_hostname,
                port,
                quit_msg,
            )

    def inner():
        try:
            fd = int(os.environ["WERKZEUG_SERVER_FD"])
        except (LookupError, ValueError):
            fd = None
        srv = make_server(
            hostname,
            port,
            threaded,
            processes,
            request_handler,
            passthrough_errors,
            fd=fd,
        )
        if fd is None:
            log_startup(srv.socket)
        srv.serve_forever()

    if use_reloader:
        # If we're not running already in the subprocess that is the
        # reloader we want to open up a socket early to make sure the
        # port is actually available.
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            if port == 0 and not can_open_by_fd:
                raise ValueError(
                    "Cannot bind to a random port with enabled "
                    "reloader if the Python interpreter does "
                    "not support socket opening by fd."
                )

            # Create and destroy a socket so that any exceptions are
            # raised before we spawn a separate Python interpreter and
            # lose this ability.
            address_family = select_address_family(hostname, port)
            server_address = get_sockaddr(hostname, port, address_family)
            s = socket.socket(address_family, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(server_address)
            if hasattr(s, "set_inheritable"):
                s.set_inheritable(True)

            # If we can open the socket by file descriptor, then we can just
            # reuse this one and our socket will survive the restarts.
            if can_open_by_fd:
                os.environ["WERKZEUG_SERVER_FD"] = str(s.fileno())
                s.listen(LISTEN_QUEUE)
                log_startup(s)
            else:
                s.close()
                if address_family is socket.AF_UNIX:
                    _log("info", "Unlinking %s" % server_address)
                    os.unlink(server_address)

        # Do not use relative imports, otherwise "python -m werkzeug.serving"
        # breaks.
        from stego_proxy.reloader import run_with_reloader

        run_with_reloader(inner, extra_files, reloader_interval, reloader_type)
    else:
        inner()


def run_with_reloader(*args, **kwargs):
    # People keep using undocumented APIs.  Do not use this function
    # please, we do not guarantee that it continues working.
    from stego_proxy.reloader import run_with_reloader

    return run_with_reloader(*args, **kwargs)


if __name__ == "__main__":
    # test()
    from stego_proxy.proxy import ProxyRequestHandler

    run_simple(hostname="127.0.0.1", port=8888, request_handler=ProxyRequestHandler,
               use_reloader=True)
