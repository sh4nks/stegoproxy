# -*- coding: utf-8 -*-
"""
    stegoproxy.stegoserver
    ~~~~~~~~~~~~~~~~~~~~~~

    This module contains the stego server listens for connections
    from the client.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import logging
from email.message import Message
from http.client import HTTPResponse
from urllib.error import HTTPError
from urllib.parse import ParseResult, urlparse, urlunparse
from urllib.request import Request, urlopen

from stegoproxy.config import cfg
from stegoproxy.connection import Client, Server
from stegoproxy.handler import BaseProxyHandler
from stegoproxy.stego import StegoMedium

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

    def do_GET(self, body=True):
        req = None
        resp = None

        url = "http://{}{}".format(cfg.REVERSE_HOSTNAME, self.path)
        req = Request(url=url)

        self.filter_headers(self.headers)

        try:
            resp = urlopen(req)
        except HTTPError as e:
            if e.getcode():
                resp = e
            else:
                log.error(f"Error proxying: {str(e)}")
                self.send_error(599, "error proxying: {}".format(str(e)))
                return

        resp_to_client = self._build_response(
            resp.version,
            resp.status,
            resp.reason,
            resp.info(),
            resp.read(),
        )

        self.wfile.write(resp_to_client)
        resp.close()

    def do_POST(self):
        try:
            # Connect to destination
            self._connect_to_host()
        except Exception as e:
            self.send_error(500, str(e))
            return

        # The request that contains the request to the website is located
        # inside the POST request body from the stegoclient
        log.debug("Got stego-request from stegoclient")
        req_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        stego_server = StegoMedium(medium=req_body).extract()

        # Get Host and Port from the original request
        host, port = self._get_hostaddr_from_headers(stego_server.message)

        # establish connection to the website
        log.info(f"Connecting to {host}:{port}")
        self.server = Server(host, port)
        self.server.connect()

        # Just relay the original request to the website
        log.debug("Relaying extracted request to website")
        self.server.send(stego_server.message)

        # Parse response from website
        h = HTTPResponse(self.server.conn)
        h.begin()

        # Get rid of hop-by-hop headers
        self.filter_headers(h.msg)

        # Build response from website
        log.debug("Building response from website")
        resp_from_dest = self._build_response(
            self.request_version,
            h.status,
            h.reason,
            h.msg,
            h.read(),
        )

        # Encapsulate response inside response to stego client
        log.debug("Embedding response from website in covert medium")
        stego_client = StegoMedium(message=resp_from_dest).embed()

        header = Message()
        header.add_header("Host", f"{cfg.REMOTE_ADDR[0]}:{cfg.REMOTE_ADDR[1]}")
        header.add_header("Connection", "keep-alive")
        header.add_header("Content-Length", str(len(stego_client.medium)))

        resp_to_client = self._build_response(
            cfg.STEGO_HTTP_VERSION,
            h.status,
            h.reason,
            header,
            stego_client.medium,
        )

        # Let's close off the remote end
        h.close()
        self.server.close()

        # Relay the message
        log.debug("Relaying stego-response to stegoclient")
        self.client.send(resp_to_client)

    def __getattr__(self, item):
        if item.startswith("do_POST"):
            return self.do_POST
        elif item.startswith("do_GET"):
            return self.do_GET
        else:
            return self.do_COMMAND
