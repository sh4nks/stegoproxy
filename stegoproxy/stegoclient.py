# -*- coding: utf-8 -*-
"""
    stegoproxy.stegoclient
    ~~~~~~~~~~~~~~~~~~~~~~

    This module contains the client that establishes the connection
    to the stegoserver.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import io
import logging
from email.message import Message

from stegoproxy import stego
from stegoproxy.config import cfg
from stegoproxy.connection import Client, Server
from stegoproxy.exceptions import MessageToLong
from stegoproxy.handler import BaseProxyHandler, StegoHTTPResponse
from stegoproxy.utils import to_bytes, to_native, to_unicode

log = logging.getLogger(__name__)


class ClientProxyHandler(BaseProxyHandler):
    def __init__(self, request, client_address, server):
        BaseProxyHandler.__init__(self, request, client_address, server)

    def _connect_to_host(self):
        self.hostname = cfg.REMOTE_ADDR[0]
        self.port = cfg.REMOTE_ADDR[1]
        self.remote_path = f"http://{self.hostname}:{self.port}/"
        # establish connection to the stegoserver
        log.info(f"Connecting to stegoserver on {self.hostname}:{self.port}")
        self.server = Server(host=self.hostname, port=int(self.port))
        self.client = Client(self.connection)  # reusing the connection here

    def do_CONNECT(self):
        self.is_connect = True
        try:
            # Connect to destination first
            super()._connect_to_host()

            # If successful, let's do this!
            self.send_response(200, "Connection Established")
            self.end_headers()
        except Exception as e:
            self.send_error(500, str(e))
            return

        log.info(f"{self.command} {self.path}")

        self._process_connect()

    def do_COMMAND(self):
        try:
            # Connect to destination
            self._connect_to_host()
        except Exception as e:
            self.send_error(500, str(e))
            return

        # Build request for destination
        # [Browser] <--> StegoClient <--> StegoServer <--> [Website]
        stego_req = self._build_stego_request(
            self.command,
            self.path,
            self.request_version,
            self.headers,
            self.rfile.read(int(self.headers.get("Content-Length", 0))),
        )

        # Build request for StegoServer
        # Browser <--> [StegoClient <--> StegoServer] <--> Website
        log.debug("Embedding request to destination in stego-request")
        header = Message()
        header.add_header("Host", f"{cfg.REMOTE_ADDR[0]}:{cfg.REMOTE_ADDR[1]}")
        header.add_header("Connection", "keep-alive")

        cover = self._get_cover_object()
        max_size = self._calc_max_size(cover)

        if len(stego_req) > max_size:
            log.error("Message doesn't fit inside cover object.")
            raise MessageToLong("Message doesn't fit inside cover object.")

        stego_medium = stego.embed(cover=cover, message=stego_req)
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
            # each chunk got seperately extracted
            stego_message = h.read()
        else:
            stego_message = stego.extract(medium=io.BytesIO(h.read()))

        # Close connection to the StegoServer
        h.close()
        self.server.close()

        # Relay the message to the browser
        log.debug("Relaying extracted response to browser")
        self.client.send(stego_message)
