# -*- coding: utf-8 -*-
"""
    stegoproxy.stegoclient
    ~~~~~~~~~~~~~~~~~~~~~~

    This module contains the client that establishes the connection
    to the stegoserver.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import logging
from email.message import Message
from http.client import (_MAXLINE, _UNKNOWN, HTTPResponse, IncompleteRead,
                         LineTooLong)

from stegoproxy import stego
from stegoproxy.config import cfg
from stegoproxy.connection import Client, Server
from stegoproxy.handler import BaseProxyHandler

log = logging.getLogger(__name__)


class StegoHTTPResponse(HTTPResponse):

    def _readall_chunked(self):
        assert self.chunked != _UNKNOWN
        value = []
        try:
            while True:
                chunk_left = self._get_chunk_left()
                if chunk_left is None:
                    break
                chunk = self._safe_read(chunk_left)
                value.append(stego.extract(chunk))
                self.chunk_left = 0
            return b''.join(value)
        except IncompleteRead:
            raise IncompleteRead(b''.join(value))


class ClientProxyHandler(BaseProxyHandler):
    def __init__(self, request, client_address, server):
        BaseProxyHandler.__init__(self, request, client_address, server)

    def _connect_to_host(self):
        self.hostname = cfg.REMOTE_ADDR[0]
        self.port = cfg.REMOTE_ADDR[1]
        self.remote_path = f"http://{self.hostname}:{self.port}/"
        # establish connection to the stegoserver
        log.info(f"Connecting to stegoserver on {self.hostname}:{self.port}")
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
            self.command,
            self.path,
            self.request_version,
            self.headers,
            self.rfile.read(int(self.headers.get("Content-Length", 0))),
        )

        # Build request for StegoServer
        # Browser <--> [StegoClient <--> StegoServer] <--> Website
        log.debug("Embedding request to destination in covert medium")
        stego_medium = stego.embed(message=req_to_dest)

        header = Message()
        header.add_header("Host", f"{cfg.REMOTE_ADDR[0]}:{cfg.REMOTE_ADDR[1]}")
        header.add_header("Connection", "keep-alive")
        header.add_header("Content-Length", str(len(stego_medium)))

        req_to_server = self._build_request(
            cfg.STEGO_HTTP_COMMAND,
            cfg.STEGO_HTTP_PATH,
            cfg.STEGO_HTTP_VERSION,
            header,
            stego_medium,
        )

        # Send the request to the stego server
        log.debug("Sending stego-request to stegoserver...")
        self.server.send(req_to_server)

        # Parse the response from the stego server
        # which contains the response from the browser
        h = StegoHTTPResponse(self.server.conn)
        h.begin()

        # Get rid of hop-by-hop headers
        self.filter_headers(h.msg)

        # Extract exact Response StegoServer's Stego-Response
        log.debug("Extracting stego-response from stegoserver")
        if h.chunked:
            stego_message = h.read()
        else:
            stego_message = stego.extract(h.read())

        # Close connection to the StegoServer
        h.close()
        self.server.close()

        # Relay the message to the browser
        log.debug("Relaying response to browser")
        self.client.send(stego_message)
