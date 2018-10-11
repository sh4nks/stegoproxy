import os
import socket

from http.server import HTTPServer
from socketserver import ThreadingMixIn, ForkingMixIn


LISTEN_QUEUE = 128


def _log(s):
    print(s)


def select_address_family(host, port):
    """Return ``AF_INET4``, ``AF_INET6``, or ``AF_UNIX`` depending on
    the host and port."""
    if ":" in host and hasattr(socket, "AF_INET6"):
        return socket.AF_INET6
    return socket.AF_INET


def get_sockaddr(host, port, family):
    """Return a fully qualified socket address that can be passed to
    :func:`socket.bind`."""
    try:
        res = socket.getaddrinfo(
            host, port, family, socket.SOCK_STREAM, socket.SOL_TCP
        )
    except socket.gaierror:
        return host, port
    return res[0][4]


class BaseHTTPServer(HTTPServer, object):
    """Simple single-threaded, single-process HTTP server."""
    multithread = False
    multiprocess = False
    request_queue_size = LISTEN_QUEUE

    def __init__(self, host, port, handler, passthrough_errors=False):
        self.address_family = select_address_family(host, port)
        server_address = get_sockaddr(host, int(port), self.address_family)

        HTTPServer.__init__(self, server_address, handler)

        self.passthrough_errors = passthrough_errors
        self.shutdown_signal = False
        self.host = host
        self.port = self.socket.getsockname()[1]

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


class ThreadedHTTPServer(ThreadingMixIn, BaseHTTPServer):
    """A WSGI server that does threading."""

    multithread = True
    daemon_threads = True


class ForkingHTTPServer(ForkingMixIn, BaseHTTPServer):
    """A WSGI server that does forking."""

    multiprocess = True

    def __init__(
        self, host, port, processes=40, handler=None, passthrough_errors=False
    ):
        if not hasattr(os, "fork"):
            raise ValueError("Your platform does not support forking.")
        BaseHTTPServer.__init__(self, host, port, handler, passthrough_errors)
        self.max_children = processes


def make_server(
    host=None,
    port=None,
    threaded=False,
    processes=1,
    request_handler=None,
    passthrough_errors=False,
):
    """Create a new server instance that is either threaded, or forks
    or just processes one request after another.
    """
    if threaded and processes > 1:
        raise ValueError(
            "cannot have a multithreaded and " "multi process server."
        )
    elif threaded:
        return ThreadedHTTPServer(
            host, port, request_handler, passthrough_errors
        )
    elif processes > 1:
        return ForkingHTTPServer(
            host, port, processes, request_handler, passthrough_errors
        )
    else:
        return BaseHTTPServer(host, port, request_handler, passthrough_errors)


def is_running_from_reloader():
    """Checks if the application is running from within the
    reloader subprocess.
    """
    return os.environ.get("STEGOPROXY_RUN_MAIN") == "true"


def run_server(
    hostname,
    port,
    request_handler,
    use_reloader=False,
    reloader_interval=1,
    reloader_type="auto",
    threaded=False,
    processes=1,
    passthrough_errors=False,
):
    """Starts a HTTP Server. Optional features include a reloader,
    multithreading and fork support.

    :param hostname: The host to bind to, for example ``'localhost'``.

    :param port: The port for the server.  eg: ``8080``
    :param request_handler: The request handler to use.
    :param use_reloader: should the server automatically restart the python
                         process if modules were changed?
    :param reloader_interval: the interval for the reloader in seconds.
    :param reloader_type: the type of reloader to use.  The default is
                          auto detection.  Valid values are ``'stat'`` and
                          ``'watchdog'``(requires watchdog).
    :param threaded: should the process handle each request in a separate
                     thread?
    :param processes: if greater than 1 then handle each request in a new
                      process up to this maximum number of concurrent
                      processes.
    :param passthrough_errors: set this to `True` to disable the error
                               catching. This means that the server will die on
                               errors but it can be useful to hook debuggers
                               in (pdb etc.)
    """
    if not isinstance(port, int):
        raise TypeError("port must be an integer")

    def log_startup(sock):
        display_hostname = hostname not in ("", "*") and hostname or "localhost"  # noqa
        quit_msg = "(Press CTRL+C to quit)"
        if sock.family is socket.AF_UNIX:
            _log(" * Running on %s %s" % (display_hostname, quit_msg))
        else:
            if ":" in display_hostname:
                display_hostname = "[%s]" % display_hostname
            port = sock.getsockname()[1]
            _log(
                " * Running on http://%s:%d/ %s"
                % (display_hostname, port, quit_msg)
            )

    def inner():
        srv = make_server(
            hostname,
            port,
            threaded,
            processes,
            request_handler,
            passthrough_errors,
        )
        log_startup(srv.socket)
        srv.serve_forever()

    if use_reloader:
        # If we're not running already in the subprocess that is the
        # reloader we want to open up a socket early to make sure the
        # port is actually available.
        if os.environ.get("STEGOPROXY_RUN_MAIN") != "true":
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

            s.close()

        # Do not use relative imports, otherwise "python -m werkzeug.serving"
        # breaks.
        from stego_proxy.reloader import run_with_reloader

        run_with_reloader(
            inner, interval=reloader_interval, reloader_type=reloader_type
        )
    else:
        inner()


if __name__ == "__main__":
    from stego_proxy.proxy import ProxyRequestHandler

    run_server(
        hostname="127.0.0.1",
        port=8888,
        request_handler=ProxyRequestHandler,
        use_reloader=True,
    )
