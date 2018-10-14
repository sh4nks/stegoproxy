# -*- coding: utf-8 -*-
"""
    stego_proxy.stegoserver
    ~~~~~~~~~~~~~~~~~~~~~~~

    This module contains the stego server listens for connections
    from the client.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, urlunparse, urlsplit, parse_qsl, ParseResult
from http.client import HTTPResponse, parse_headers
import ssl
import socket
import select
import logging
import datetime
import json
import re
from html.parser import HTMLParser
import logging
from http.client import HTTPResponse
from urllib.parse import ParseResult, urlparse, urlunparse

from stego_proxy.config import cfg
from stego_proxy.connection import Client, Server
from stego_proxy.exceptions import UnsupportedSchemeException
from stego_proxy.utils import to_bytes, to_unicode
from stego_proxy.handler import BaseProxyHandler
from stego_proxy.stego import StegoMedium

CRLF = b"\r\n"
log = logging.getLogger(__name__)


class ServerProxyHandler(BaseProxyHandler):
    def __init__(self, request, client_address, server):
        BaseProxyHandler.__init__(self, request, client_address, server)
        self.stego_medium = None

    def _connect_to_host(self):
        # Get hostname and port to connect to
        if self.is_connect:
            self.hostname, self.port = self.path.split(":")
        else:
            u = urlparse(self.path)
            # if u.scheme != "http":
            #    raise UnsupportedSchemeException(
            #        "Unknown scheme %s" % repr(u.scheme)
            #    )
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

    def _get_hostaddr_from_headers(self, headers):
        import email
        raw_headers = to_unicode(headers).split('\r\n')[1]
        headers = email.message_from_string(raw_headers)
        host, port = headers["host"].split(":")
        return host, port

    def do_COMMAND(self):
        # log.info(f"{self.command} {self.path}")
        try:
            # Connect to destination
            self._connect_to_host()
        except Exception as e:
            self.send_error(500, str(e))
            return

        # The request that got sent to the website: self
        # Browser <--> [Proxy <--> Website]
        content_length = int(self.headers.get("Content-Length", 0))
        request_body = self.rfile.read(content_length)

        self.stego_medium = StegoMedium(
            medium=request_body, algorithm="base64"
        ).extract()

        host, port = self._get_hostaddr_from_headers(self.stego_medium.message)

        log.info(f"Connecting to: {host}:{port}")
        # establish connection to the website
        self.server = Server(host, port)
        self.server.connect()

        log.debug("Sending message:\n" + to_unicode(self.stego_medium.message))
        # Send the original request to the website
        self.server.send(self.stego_medium.message)

        # Parse response
        h = HTTPResponse(self.server.conn)
        h.begin()
        log.debug("Got response:\n" + h.msg.as_string())

        # Get rid of hop-by-hop headers
        orig_response = h
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

        # Let's close off the remote end
        h.close()
        self.server.close()

        # Relay the message
        self.client.send(res)
