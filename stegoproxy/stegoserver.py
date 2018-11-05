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

from stegoproxy import stego
from stegoproxy.config import cfg
from stegoproxy.connection import Client, Server
from stegoproxy.handler import BaseProxyHandler
from stegoproxy.utils import to_bytes, to_native, to_unicode

log = logging.getLogger(__name__)


class ServerProxyHandler(BaseProxyHandler):
    def __init__(self, request, client_address, server):
        BaseProxyHandler.__init__(self, request, client_address, server)

    def _write_end_of_chunks(self):
        self.client.send(b"0\r\n\r\n")

    def _write_chunks(self, chunk):
        # no need to convert to "to_bytes" - chunk is already of type bytes
        s = b"%X\r\n%s\r\n" % (len(chunk), chunk)
        log.debug(f"Sending chunk with size: {len(chunk)}")
        self.client.send(s)

    def to_chunks(self, seq, chunk_size):
        """Splits a sequence into evenly sized chunks."""
        for i in range(0, len(seq), chunk_size):
            yield seq[i: i + chunk_size]

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
            resp.version, resp.status, resp.reason, resp.info(), resp.read()
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
        stego_message = stego.extract(medium=req_body)

        # Get Host and Port from the original request
        host, port = self._get_hostaddr_from_headers(stego_message)

        # establish connection to the website
        log.info(f"Connecting to {host}:{port}")
        self.server = Server(host, port)
        self.server.connect()

        # Just relay the original request to the website
        log.debug("Relaying extracted request to website")
        self.server.send(stego_message)

        # Parse response from website
        h = HTTPResponse(self.server.conn)
        h.begin()

        # Get rid of hop-by-hop headers
        self.filter_headers(h.msg)

        # Build response from website
        log.debug("Building response from website")
        resp_from_dest = self._build_response(
            self.request_version, h.status, h.reason, h.msg, h.read()
        )

        # Build header to stegoclient
        header = Message()
        header.add_header("Host", f"{cfg.REMOTE_ADDR[0]}:{cfg.REMOTE_ADDR[1]}")
        header.add_header("Connection", "keep-alive")

        chunk_count = 0
        if len(resp_from_dest) > cfg.MAX_CONTENT_LENGTH:
            log.debug(
                "Can't fit response into stego medium - using chunks of "
                f"{cfg.MAX_CONTENT_LENGTH} bytes."
            )

            header.add_header("Transfer-Encoding", "chunked")
            resp_to_client = self._build_response_header(
                cfg.STEGO_HTTP_VERSION, h.status, h.reason, header
            )

            # Send headers to client
            log.debug("Sending chunked header to stegoclient")
            self.client.send(resp_to_client)

            for chunk in self.to_chunks(resp_from_dest, cfg.MAX_CONTENT_LENGTH):
                # Send chunks
                self._write_chunks(stego.embed(message=chunk))
                chunk_count += 1

            # send "end of chunks" trailer
            self._write_end_of_chunks()
            log.debug(f"{chunk_count} chunks sent.")
        else:
            # Encapsulate response inside response to stego client
            log.debug("Embedding response from website in covert medium")

            stego_medium = stego.embed(message=resp_from_dest)
            header.add_header("Content-Length", str(len(stego_medium)))

            resp_to_client = self._build_response(
                cfg.STEGO_HTTP_VERSION, h.status, h.reason, header, stego_medium
            )

            # Relay the message
            log.debug("Relaying stego-response to stegoclient")
            self.client.send(resp_to_client)

        # Let's close off the remote end
        h.close()
        self.server.close()

    def __getattr__(self, item):
        if item.startswith("do_POST"):
            return self.do_POST
        elif item.startswith("do_GET"):
            return self.do_GET
        else:
            return self.do_COMMAND
