# -*- coding: utf-8 -*-
"""
    stego_proxy.stegoclient
    ~~~~~~~~~~~~~~~~~~~~~~~

    This module contains the client that establishes the connection
    to the stegoserver.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import logging
from http.client import HTTPResponse
from urllib.parse import ParseResult, urlparse, urlunparse
from email.message import Message

from stego_proxy.config import cfg
from stego_proxy.connection import Client, Server
from stego_proxy.exceptions import UnsupportedSchemeException
from stego_proxy.utils import to_bytes
from stego_proxy.handler import BaseProxyHandler
from stego_proxy.stego import StegoMedium


log = logging.getLogger(__name__)
CRLF = b"\r\n"


class ClientProxyHandler(BaseProxyHandler):
    def __init__(self, request, client_address, server):
        BaseProxyHandler.__init__(self, request, client_address, server)

    def _connect_to_host(self):
        self.hostname = cfg.REMOTE_ADDR[0]
        self.port = cfg.REMOTE_ADDR[1]
        self.remote_path = f"http://{self.hostname}:{self.port}/"
        # establish connection to the stegoserver
        log.debug(f"Connecting to {self.hostname}:{self.port}")
        self.server = Server(self.hostname, int(self.port))
        self.server.connect()
        self.client = Client(self.connection)  # reusing the connection here

    def do_COMMAND(self):
        try:
            # Connect to destination
            self._connect_to_host()
        except Exception as e:
            self.send_error(500, str(e))
            return

        # Build request for destination
        # [Browser] <--> StegoClient <--> StegoServer <--> [Website]
        req_to_dest = self._build_request(
            to_bytes(self.command),
            to_bytes(self.path),
            to_bytes(self.request_version),
            self.headers.as_bytes()[:-1],  # ends with 2 \n\n - remove 1
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
        )

        # Build request for StegoServer
        # Browser <--> [StegoClient <--> StegoServer] <--> Website
        stego_server = StegoMedium(message=req_to_dest).embed()

        header = Message()
        header.add_header("Host", f"{cfg.REMOTE_ADDR[0]}:{cfg.REMOTE_ADDR[1]}")
        header.add_header("Connection", "keep-alive")
        header.add_header("Content-Length", str(len(stego_server.medium)))

        req_to_server = self._build_request(
            to_bytes(cfg.HTTP_COMMAND),
            to_bytes(cfg.HTTP_PATH),
            to_bytes(cfg.HTTP_VERSION),
            header.as_bytes()[:-1],
            stego_server.medium
        )
        log.info(req_to_server)

        # Send the request to the stego server
        self.server.send(req_to_server)

        # Parse the response from the stego server
        # which contains the response from the browser
        h = HTTPResponse(self.server.conn)
        h.begin()

        # Get rid of hop-by-hop headers
        self.filter_headers(h.msg)

        # TODO: 1. Extract Stego Message from StegoServer Response
        #          and relay the message to the Browser
        #       2. Create new HTTP Message from extracted StegoMessage

        #stego_client = StegoMedium(medium=h.read()).extract()

        # Build response for browser
        resp_to_browser = self._build_response(
            to_bytes(self.request_version),
            to_bytes(h.status),
            to_bytes(h.reason),
            h.msg.as_bytes(),
            h.read()
        )

        # Close connection to the StegoServer
        h.close()
        self.server.close()

        # Relay the message to the browser
        self.client.send(resp_to_browser)
