#!/usr/bin/env python
# -*- coding: utf-8 -*-

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, urlunparse, ParseResult
from socketserver import ThreadingMixIn
from http.client import HTTPResponse, HTTPSConnection, HTTPConnection
from tempfile import gettempdir
import sys
import os
import ssl
import socket
import io
import select
import logging
import datetime
from OpenSSL.crypto import (
    X509Extension,
    X509,
    dump_privatekey,
    dump_certificate,
    load_certificate,
    load_privatekey,
    PKey,
    TYPE_RSA,
    X509Req,
)
from OpenSSL.SSL import FILETYPE_PEM

CRLF, COLON, SP = b"\r\n", b":", b" "
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - pid:%(process)d - %(message)s",
)
from stego_proxy.utils import to_bytes


__all__ = [
    "CertificateAuthority",
    "ProxyHandler",
    "RequestInterceptorPlugin",
    "ResponseInterceptorPlugin",
    "MitmProxy",
    "AsyncMitmProxy",
    "InvalidInterceptorPluginException",
]

global tunnel_addr


class CertificateAuthority(object):
    def __init__(self, ca_file="ca.pem", cache_dir=gettempdir()):
        self.ca_file = ca_file
        self.cache_dir = cache_dir
        self._serial = self._get_serial()
        if not os.path.exists(ca_file):
            self._generate_ca()
        else:
            self._read_ca(ca_file)

    def _get_serial(self):
        s = 1
        for c in filter(
            lambda x: x.startswith(".pymp_"), os.listdir(self.cache_dir)
        ):
            c = load_certificate(
                FILETYPE_PEM, open(os.path.sep.join([self.cache_dir, c])).read()
            )
            sc = c.get_serial_number()
            if sc > s:
                s = sc
            del c
        return s

    def _generate_ca(self):
        # Generate key
        self.key = PKey()
        self.key.generate_key(TYPE_RSA, 2048)

        # Generate certificate
        self.cert = X509()
        self.cert.set_version(3)
        self.cert.set_serial_number(1)
        self.cert.get_subject().CN = "ca.mitm.com"
        self.cert.gmtime_adj_notBefore(0)
        self.cert.gmtime_adj_notAfter(315360000)
        self.cert.set_issuer(self.cert.get_subject())
        self.cert.set_pubkey(self.key)
        self.cert.add_extensions(
            [
                X509Extension("basicConstraints", True, "CA:TRUE, pathlen:0"),
                X509Extension("keyUsage", True, "keyCertSign, cRLSign"),
                X509Extension(
                    "subjectKeyIdentifier", False, "hash", subject=self.cert
                ),
            ]
        )
        self.cert.sign(self.key, "sha1")

        with open(self.ca_file, "wb+") as f:
            f.write(dump_privatekey(FILETYPE_PEM, self.key))
            f.write(dump_certificate(FILETYPE_PEM, self.cert))

    def _read_ca(self, file):
        self.cert = load_certificate(FILETYPE_PEM, open(file).read())
        self.key = load_privatekey(FILETYPE_PEM, open(file).read())

    def __getitem__(self, cn):

        cnp = os.path.sep.join([self.cache_dir, ".pymp_%s.pem" % cn])
        if not os.path.exists(cnp):
            # create certificate
            key = PKey()
            key.generate_key(TYPE_RSA, 2048)

            # Generate CSR
            req = X509Req()
            req.get_subject().CN = cn
            req.set_pubkey(key)
            req.sign(key, "sha1")

            # Sign CSR
            cert = X509()
            cert.set_subject(req.get_subject())
            cert.set_serial_number(self.serial)
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(31536000)
            cert.set_issuer(self.cert.get_subject())
            cert.set_pubkey(req.get_pubkey())
            cert.sign(self.key, "sha1")

            with open(cnp, "wb+") as f:
                f.write(dump_privatekey(FILETYPE_PEM, key))
                f.write(dump_certificate(FILETYPE_PEM, cert))

        return cnp

    @property
    def serial(self):
        self._serial += 1
        return self._serial


class UnsupportedSchemeException(Exception):
    pass


class Connection(object):
    """TCP server/client connection abstraction."""

    def __init__(self, what):
        self.buffer = b""
        self.closed = False
        self.what = what  # server or client

    def send(self, data):
        """Sends data down the socket."""
        return self.conn.send(data)

    def recv(self, bytes=8192):
        """Recieves data from the socket."""
        try:
            data = self.conn.recv(bytes)
            if len(data) == 0:
                logger.debug("recvd 0 bytes from %s", self.what)
                return None
            logger.debug("rcvd %d bytes from %s", len(data), self.what)
            return data
        except Exception as e:
            logger.exception(
                "Exception while receiving from connection %s %r "
                "with reason %r",
                self.what,
                self.conn,
                e,
            )
            return None

    def close(self):
        """Closes the connection."""
        self.conn.close()
        self.closed = True

    def buffer_size(self):
        """Returns the current buffer size."""
        return len(self.buffer)

    def has_buffer(self):
        """Checks if the buffer is > 0."""
        return self.buffer_size() > 0

    def queue(self, data):
        """Writes data to the buffer."""
        self.buffer += data

    def flush(self):
        """Flushes the buffer."""
        sent = self.send(self.buffer)
        self.buffer = self.buffer[sent:]
        logger.debug("flushed %d bytes to %s", sent, self.what)


class Server(Connection):
    """Establish connection to destination server."""

    def __init__(self, host, port):
        super(Server, self).__init__(b"server")
        self.addr = (host, int(port))
        self.tunnel = Tunnel()

    def connect(self, intercept=False):
        self.conn = socket.create_connection((self.addr[0], self.addr[1]))
        if intercept:
            self.conn = ssl.wrap_socket(self.conn)

    def recv(self, bytes=8192):
        """Recieves data from the socket."""
        try:
            data = self.tunnel.recv(bytes)
            if len(data) == 0:
                logger.debug("recvd 0 bytes from %s", self.tunnel.what)
                return None
            logger.debug("rcvd %d bytes from %s", len(data), self.tunnel.what)
            return data
        except Exception as e:
            logger.exception(
                "Exception while receiving from connection %s %r "
                "with reason %r",
                self.what,
                self.conn,
                e,
            )
            return None


class Client(Connection):
    """Accepted client connection."""

    def __init__(self, conn):
        super(Client, self).__init__(b"client")
        self.conn = conn


class Tunnel(Connection):
    """Establish connection between two proxy servers."""

    def __init__(self):
        super(Tunnel, self).__init__(b"tunnel")
        self.conn = socket.create_connection(tunnel_addr, timeout=10)


# Browser -- Host1 --- Host2 -- Website
#
#


class ProxyHandler(BaseHTTPRequestHandler):
    # r = compile(r"http://[^/]+(/?.*)(?i)")

    def __init__(self, request, client_address, server):
        self.is_connect = False
        self.do_intercept = False
        self.start_time = self._now()
        self.last_activity = self.start_time
        self._headers_buffer = []
        BaseHTTPRequestHandler.__init__(self, request, client_address, server)

    def _connect_to_host(self):
        # Get hostname and port to connect to
        if self.is_connect:
            self.hostname, self.port = self.path.split(":")
        else:
            u = urlparse(self.path)
            if u.scheme != "http":
                raise UnsupportedSchemeException(
                    "Unknown scheme %s" % repr(u.scheme)
                )
            self.hostname = u.hostname
            self.port = u.port or 80
            self.path = urlunparse(
                ParseResult(
                    scheme="",
                    netloc="",
                    params=u.params,
                    path=u.path or "/",
                    query=u.query,
                    fragment=u.fragment,
                )
            )

        self.server = Server(self.hostname, int(self.port))
        self.server.connect()
        self.client = Client(self.connection)  # reusing the connection here

    def _transition_to_ssl(self):
        if self.do_intercept:
            self.request = ssl.wrap_socket(
                self.request,
                server_side=True,
                certfile=self.server.ca[self.path.split(":")[0]],
            )

    def _get_waitable_lists(self):
        rlist, wlist, xlist = [self.client.conn], [], []
        logger.debug("*** watching client for read ready")

        if self.client.has_buffer():
            logger.debug(
                "pending client buffer found, watching client for write ready"
            )
            wlist.append(self.client.conn)

        if self.server and not self.server.closed:
            logger.debug(
                "connection to server exists, watching server for read ready"
            )
            rlist.append(self.server.conn)

        if self.server and not self.server.closed and self.server.has_buffer():
            logger.debug(
                "connection to server exists and pending server "
                "buffer found, watching server for write ready"
            )
            wlist.append(self.server.conn)

        return rlist, wlist, xlist

    def _now(self):
        return datetime.datetime.utcnow()

    def _inactive_for(self):
        return (self._now() - self.last_activity).seconds

    def _is_inactive(self):
        return self._inactive_for() > 30

    def _process_request(self, data):
        # once we have connection to the server we don't parse the
        # http request packets any further, instead just pipe incoming
        # data from client to server
        if self.server and not self.server.closed:
            logger.debug("processing request")
            self.server.queue(data)
            return

    def _process_response(self, data):
        # queue data for client
        logger.debug("processing response")
        self.client.queue(data)

    def _process_wlist(self, w):
        if self.client.conn in w:
            logger.debug("client is ready for writes, flushing client buffer")
            self.client.flush()

        if self.server and not self.server.closed and self.server.conn in w:
            logger.debug("server is ready for writes, flushing server buffer")
            self.server.flush()

    def _process_rlist(self, r):
        if self.client.conn in r:
            logger.debug("client is ready for reads, reading")
            data = self.client.recv()

            if not data:
                logger.debug("client closed connection, breaking")
                return True

            try:
                self._process_request(data)
            except Exception as e:
                logger.exception(e)
                self.client.queue(
                    CRLF.join(
                        [
                            b"HTTP/1.1 502 Bad Gateway",
                            b"Proxy-agent: stego_proxy.py v0.1",
                            b"Content-Length: 11",
                            b"Connection: close",
                            CRLF,
                        ]
                    )
                    + b"Bad Gateway"
                )
                self.client.flush()
                return True

        if self.server and not self.server.closed and self.server.conn in r:
            logger.debug("server is ready for reads, reading")
            data = self.server.recv()
            self.last_activity = self._now()

            if not data:
                logger.debug("server closed connection")
                self.server.close()
            else:
                self._process_response(data)

        return False

    def _process_connect(self):
        while True:
            rlist, wlist, xlist = self._get_waitable_lists()
            ready_to_read, ready_to_write, in_error = select.select(
                rlist, wlist, xlist, 10
            )

            self._process_wlist(ready_to_write)
            if self._process_rlist(ready_to_read) or in_error:
                break

    def do_CONNECT(self):
        self.is_connect = True

        try:
            # Connect to destination first
            self._connect_to_host()

            # If successful, let's do this!
            self.send_response(200, "Connection Established")
            self.end_headers()
            self._transition_to_ssl()
        except Exception as e:
            self.send_error(500, str(e))
            return

        if self.do_intercept:
            # Reload!
            self.setup()
            self.ssl_host = "https://%s" % self.path
            self.handle_one_request()
        else:
            self._process_connect()

    def do_COMMAND(self):
        # Is this an SSL tunnel?
        if not self.is_connect:
            try:
                # Connect to destination
                self._connect_to_host()
            except Exception as e:
                self.send_error(500, str(e))
                return
            # Extract path

        # Build request
        req = "%s %s %s\r\n" % (self.command, self.path, self.request_version)

        # Add headers to the request
        req += "%s\r\n" % self.headers

        # Append message body if present to the request
        if "Content-Length" in self.headers:
            req += self.rfile.read(int(self.headers["Content-Length"]))

        # Send it down the pipe!
        self.server.send(to_bytes(req))
        self.server.tunnel.send(to_bytes(req))

        # Parse response
        h = HTTPResponse(self.server.conn)
        h.begin()

        # Get rid of the pesky header
        del h.msg["Transfer-Encoding"]

        # Time to relay the message across
        res = to_bytes(
            "%s %s %s\r\n" % (self.request_version, h.status, h.reason)
        )
        res += to_bytes("%s\r\n" % h.msg)
        res += h.read()

        # Let's close off the remote end
        h.close()
        self.server.close()

        # Relay the message
        self.client.send(res)

    def mitm_request(self, data):
        return data

    def mitm_response(self, data):
        return data

    def __getattr__(self, item):
        if item.startswith("do_"):
            return self.do_COMMAND


class InterceptorPlugin(object):
    def __init__(self, server, msg):
        self.server = server
        self.message = msg


class RequestInterceptorPlugin(InterceptorPlugin):
    def do_request(self, data):
        return data


class ResponseInterceptorPlugin(InterceptorPlugin):
    def do_response(self, data):
        return data


class DebugInterceptor(RequestInterceptorPlugin, ResponseInterceptorPlugin):
    def do_request(self, data):
        # print(">> %s" % repr(data[:200]))
        return data

    def do_response(self, data):
        # print("<< %s" % repr(data[:200]))
        return data


class InvalidInterceptorPluginException(Exception):
    pass


class MitmProxyServer(HTTPServer, ThreadingMixIn):
    def __init__(
        self,
        server_address=("", 8888),
        tunnel_address=("", 8890),
        RequestHandlerClass=ProxyHandler,
        bind_and_activate=True,
        ca_file="ca.pem",
    ):
        HTTPServer.__init__(
            self, server_address, RequestHandlerClass, bind_and_activate
        )
        self.ca = CertificateAuthority(ca_file)
        self._res_plugins = []
        self._req_plugins = []

    def register_interceptor(self, interceptor_class):
        if not issubclass(interceptor_class, InterceptorPlugin):
            raise InvalidInterceptorPluginException(
                "Expected type InterceptorPlugin got %s instead"
                % type(interceptor_class)
            )
        if issubclass(interceptor_class, RequestInterceptorPlugin):
            self._req_plugins.append(interceptor_class)
        if issubclass(interceptor_class, ResponseInterceptorPlugin):
            self._res_plugins.append(interceptor_class)


def main():
    import argparse
    from stego_proxy.proxyserver import run_server
    parser = argparse.ArgumentParser(
        description="proxy.py v%s" % "0.1",
        epilog=(
            "Having difficulty using proxy.py? Report at: /issues/new"
        ),
    )

    parser.add_argument(
        "--host", default="127.0.0.1:8888", help="Default: 127.0.0.1:8888"
    )
    parser.add_argument(
        "--tunnel", default="127.0.0.1:8890", help="Default: 127.0.0.1:8890"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - pid:%(process)d - %(message)s",
    )

    addr = args.host.split(":")
    hostname = addr[0]
    port = int(addr[1])

    tunnel = args.tunnel.split(":")
    global tunnel_addr
    tunnel_addr = (tunnel[0], tunnel[1])

    run_server(hostname, port, ProxyHandler)


if __name__ == "__main__":
    main()
