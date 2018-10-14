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
        self.stego_medium = None

    def _connect_to_host(self):
        self.hostname = cfg.REMOTE_ADDR[0]
        self.port = cfg.REMOTE_ADDR[1]
        self.remote_path = f"http://{self.hostname}:{self.port}/"
        # establish connection to the stegoserver
        log.debug(f"Connecting to {self.hostname}:{self.port}")
        self.server = Server(self.hostname, int(self.port))
        self.server.connect()
        self.client = Client(self.connection)  # reusing the connection here

    def _build_request(self, cmd, path, version, headers, body):
        request = (
            # Add "GET / HTTP/1.1..." to the request"
            b" ".join([to_bytes(cmd), to_bytes(path), to_bytes(version)])
            + CRLF
            # Add Headers to the request (Host:..., User-Agent:...)
            + headers.as_bytes()[:-1]
            + CRLF
            + body
        )
        return request

    def do_CONNECT(self):
        self.is_connect = True
        try:
            # Connect to destination first
            self._connect_to_host()

            # If successful, let's do this!
            self.send_response(200, "Connection Established")
            self.end_headers()
        except Exception as e:
            self.send_error(500, str(e))
            return

        log.info(f"{self.command} {self.path}")

        self._process_connect()

    def do_COMMAND(self):
        # log.info(f"{self.command} {self.path}")
        try:
            # Connect to destination
            self._connect_to_host()
        except Exception as e:
            # raise e
            self.send_error(500, str(e))
            return

        # Build request for destination
        # [Browser] <--> StegoClient <--> StegoServer <--> [Website]
        content_length = int(self.headers.get("Content-Length", 0))
        request_body = self.rfile.read(content_length)
        req_to_dest = self._build_request(
            self.command,
            self.path,
            self.request_version,
            self.headers,
            request_body,
        )

        # Build request for StegoServer
        # Browser <--> [StegoClient <--> StegoServer] <--> Website
        self.stego_medium = StegoMedium(message=req_to_dest, algorithm="base64").embed()

        msg = Message()
        msg.add_header("Host", "127.0.0.1:9999")
        msg.add_header("Connection", "keep-alive")
        msg.add_header("Content-Length", str(len(self.stego_medium.medium)))

        req_to_server = self._build_request(
            "POST", "/", "HTTP/1.1", msg, self.stego_medium.medium
        )
        log.info(req_to_server)
        # Send it down the pipe!
        self.server.send(req_to_server)

        # Parse response
        h = HTTPResponse(self.server.conn)
        h.begin()

        # TODO: 1. Extract Stego Message from StegoServer Response
        #          and relay the message to the Browser
        #       2. Create new HTTP Message from extracted StegoMessage

        # Get rid of hop-by-hop headers
        self.filter_headers(h.msg)
        # Time to relay the message across
        # read response body
        response_body = h.read()
        res = (
            # HTTP/1.1  OK
            b" ".join(
                [
                    to_bytes(self.request_version),
                    to_bytes(str(h.status)),
                    to_bytes(h.reason),
                ]
            )
            # Content-Type, Content-Length, Server...
            + CRLF
            + h.msg.as_bytes()
            + CRLF
            + response_body
        )

        # Close connection to the StegoServer
        h.close()
        self.server.close()

        # Relay the message to the browser
        self.client.send(res)
