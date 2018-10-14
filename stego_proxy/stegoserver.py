# -*- coding: utf-8 -*-
"""
    stego_proxy.stegoserver
    ~~~~~~~~~~~~~~~~~~~~~~~

    This module contains the stego server listens for connections
    from the client.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import logging
from http.client import HTTPResponse
from urllib.parse import ParseResult, urlparse, urlunparse
from email.message import Message

from stego_proxy.config import cfg
from stego_proxy.connection import Client, Server
from stego_proxy.handler import BaseProxyHandler
from stego_proxy.stego import StegoMedium
from stego_proxy.utils import to_bytes, to_unicode

CRLF = b"\r\n"
log = logging.getLogger(__name__)


class ServerProxyHandler(BaseProxyHandler):
    def __init__(self, request, client_address, server):
        BaseProxyHandler.__init__(self, request, client_address, server)

    def _connect_to_host(self):
        # Get hostname and port to connect to
        if self.is_connect:
            self.hostname, self.port = self.path.split(":")
        else:
            u = urlparse(self.path)
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
        self.client = Client(self.connection)  # reusing the connection here

    def do_COMMAND(self):
        try:
            # Connect to destination
            self._connect_to_host()
        except Exception as e:
            self.send_error(500, str(e))
            return

        # The request that contains the request to the website is located
        # inside the POST request body from the stegoclient
        req_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        stego_server = StegoMedium(medium=req_body).extract()

        # Get Host and Port from the original request
        host, port = self._get_hostaddr_from_headers(stego_server.message)

        # establish connection to the website
        log.info(f"Connecting to: {host}:{port}")
        self.server = Server(host, port)
        self.server.connect()

        # Just relay the original request to the website
        log.debug("Sending message:\n" + to_unicode(stego_server.message))
        self.server.send(stego_server.message)

        # Parse response from website
        h = HTTPResponse(self.server.conn)
        h.begin()
        log.debug("Got response:\n" + h.msg.as_string())

        # Get rid of hop-by-hop headers
        self.filter_headers(h.msg)

        # Build response from website
        resp_from_dest = self._build_response(
                    to_bytes(self.request_version),
                    to_bytes(h.status),
                    to_bytes(h.reason),
                    h.msg.as_bytes(),
                    h.read()
        )

        # Encapsulate response inside response to stego client
        stego_client = StegoMedium(message=resp_from_dest).embed()

        header = Message()
        header.add_header("Host", f"{cfg.REMOTE_ADDR[0]}:{cfg.REMOTE_ADDR[1]}")
        header.add_header("Connection", "keep-alive")
        header.add_header("Content-Length", str(len(stego_client.medium)))

        resp_to_client = self._build_response(
            to_bytes(cfg.HTTP_VERSION),
            to_bytes(h.status),
            to_bytes(h.reason),
            header.as_bytes()[:-1],
            stego_client.medium
        )

        # Let's close off the remote end
        h.close()
        self.server.close()

        # Relay the message
        self.client.send(resp_to_client)
