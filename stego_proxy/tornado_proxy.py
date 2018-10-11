#!/usr/bin/env python
#
# Simple asynchronous HTTP proxy with tunnelling (CONNECT).


import logging
import logging.config
import os
import sys
import socket
from urllib.parse import urlparse

import tornado.httpserver
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.httpclient
import tornado.httputil

from stego_proxy import config

__all__ = ["ProxyHandler", "run_proxy"]


logging.config.dictConfig(config.LOG_DEFAULT_CONF)
logger = logging.getLogger("stego_proxy")


def get_proxy(url):
    url_parsed = urlparse(url, scheme="http")
    proxy_key = "%s_proxy" % url_parsed.scheme
    return os.environ.get(proxy_key)


def parse_proxy(proxy):
    proxy_parsed = urlparse(proxy, scheme="http")
    return proxy_parsed.hostname, proxy_parsed.port


def fetch_request(url, callback, **kwargs):
    proxy = get_proxy(url)
    if proxy:
        logger.debug("Forward request via upstream proxy %s", proxy)
        tornado.httpclient.AsyncHTTPClient.configure(
            "tornado.curl_httpclient.CurlAsyncHTTPClient"
        )
        host, port = parse_proxy(proxy)
        kwargs["proxy_host"] = host
        kwargs["proxy_port"] = port

    req = tornado.httpclient.HTTPRequest(url, **kwargs)
    client = tornado.httpclient.AsyncHTTPClient()
    client.fetch(req, callback, raise_error=False)
    print(client)


class ProxyHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ["GET", "POST", "CONNECT"]

    def compute_etag(self):
        return None  # disable tornado Etag

    @tornado.web.asynchronous
    def get(self):
        logger.debug(
            "%s request to %s", self.request.method, self.request.uri
        )

        def handle_response(response):
            if response.error and not isinstance(
                response.error, tornado.httpclient.HTTPError
            ):
                self.set_status(500)
                self.write("Internal server error:\n" + str(response.error))
            else:
                self.set_status(response.code, response.reason)
                self._headers = (
                    tornado.httputil.HTTPHeaders()
                )  # clear tornado default header

                for header, v in response.headers.get_all():
                    if header not in (
                        "Content-Length",
                        "Transfer-Encoding",
                        "Content-Encoding",
                        "Connection",
                    ):
                        self.add_header(
                            header, v
                        )  # some header appear multiple times, eg 'Set-Cookie'

                if response.body:
                    self.set_header("Content-Length", len(response.body))
                    self.write(response.body)
            self.finish()

        body = self.request.body
        if not body:
            body = None
        try:
            if "Proxy-Connection" in self.request.headers:
                del self.request.headers["Proxy-Connection"]

            fetch_request(
                self.request.uri,
                handle_response,
                method=self.request.method,
                body=body,
                headers=self.request.headers,
                follow_redirects=False,
                allow_nonstandard_methods=True,
            )

            print(self.request)

        except tornado.httpclient.HTTPError as e:
            if hasattr(e, "response") and e.response:
                handle_response(e.response)
            else:
                self.set_status(500)
                self.write("Internal server error:\n" + str(e))
                self.finish()

    @tornado.web.asynchronous
    def post(self):
        return self.get()

    @tornado.web.asynchronous
    def connect(self):
        logger.debug("CONNECT to %s", self.request.uri)
        host, port = self.request.uri.split(":")
        client = self.request.connection.stream

        def read_from_client(data):
            upstream.write(data)

        def read_from_upstream(data):
            client.write(data)

        def client_close(data=None):
            if upstream.closed():
                return
            if data:
                upstream.write(data)
            upstream.close()

        def upstream_close(data=None):
            if client.closed():
                return
            if data:
                client.write(data)
            client.close()

        def start_tunnel():
            logger.debug("CONNECT tunnel established to %s", self.request.uri)
            client.read_until_close(client_close, read_from_client)
            upstream.read_until_close(upstream_close, read_from_upstream)
            client.write(b"HTTP/1.0 200 Connection established\r\n\r\n")

        def on_proxy_response(data=None):
            if data:
                first_line = data.splitlines()[0]
                http_v, status, text = first_line.split(None, 2)
                if int(status) == 200:
                    logger.debug("Connected to upstream proxy %s", proxy)
                    start_tunnel()
                    return

            self.set_status(500)
            self.finish()

        def start_proxy_tunnel():
            upstream.write("CONNECT %s HTTP/1.1\r\n" % self.request.uri)
            upstream.write("Host: %s\r\n" % self.request.uri)
            upstream.write("Proxy-Connection: Keep-Alive\r\n\r\n")
            upstream.read_until("\r\n\r\n", on_proxy_response)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        upstream = tornado.iostream.IOStream(s)

        proxy = get_proxy(self.request.uri)
        if proxy:
            proxy_host, proxy_port = parse_proxy(proxy)
            upstream.connect((proxy_host, proxy_port), start_proxy_tunnel)
        else:
            upstream.connect((host, int(port)), start_tunnel)


def run_proxy(port, start_ioloop=True):
    """
    Run proxy on the specified port. If start_ioloop is True (default),
    the tornado IOLoop will be started immediately.
    """
    app = tornado.web.Application([(r".*", ProxyHandler)])
    app.listen(port)
    ioloop = tornado.ioloop.IOLoop.instance()
    if start_ioloop:
        ioloop.start()


if __name__ == "__main__":
    port = 8888
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    print("Starting HTTP proxy on port %d" % port)
    run_proxy(port)
