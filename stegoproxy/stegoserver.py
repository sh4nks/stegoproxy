# -*- coding: utf-8 -*-
"""
    stegoproxy.stegoserver
    ~~~~~~~~~~~~~~~~~~~~~~

    This module contains the stego server listens for connections
    from the client.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import io
import logging
import time
from email.message import Message
from http.client import HTTPResponse
from urllib.error import HTTPError
from urllib.parse import ParseResult, urlparse, urlunparse
from urllib.request import Request, urlopen

from PIL import Image

from stegoproxy import stego
from stegoproxy.config import cfg
from stegoproxy.connection import Client, Server
from stegoproxy.handler import BaseProxyHandler, StegoHTTPResponse
from stegoproxy.utils import to_bytes, to_native, to_unicode

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
        # io stream that represents the stego medium (i.e. image)
        req_body = io.BytesIO(
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
        )
        stego_message = stego.extract(medium=req_body)

        # Get Host and Port from the original request
        host, port = self._get_hostaddr_from_headers(stego_message)

        # establish connection to the website
        log.info(f"Connecting to {host}:{port}")
        self.server = Server(host=host, port=port)

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
        stego_resp = self._build_stego_response(
            self.request_version, h.status, h.reason, h.msg, h.read()
        )

        # Build header to stegoclient
        header = Message()
        header.add_header("Host", f"{cfg.REMOTE_ADDR[0]}:{cfg.REMOTE_ADDR[1]}")
        header.add_header("Connection", "keep-alive")
        cover = self._get_cover_object()
        max_size = self._calc_max_size(cover)

        if (
            len(stego_resp) > max_size
            or len(stego_resp) > cfg.MAX_CONTENT_LENGTH
        ):
            if cfg.MAX_CONTENT_LENGTH > max_size:
                cfg.MAX_CONTENT_LENGTH = max_size

            log.debug(
                f"Can't fit response ({len(stego_resp)} bytes) into stego-response - "
                f"splitting into chunks of {cfg.MAX_CONTENT_LENGTH} bytes."
            )

            header.add_header("Transfer-Encoding", "chunked")
            resp_to_client = self._build_response_header(
                cfg.STEGO_HTTP_VERSION, h.status, h.reason, header
            )

            # Send headers to client
            log.debug("Sending chunked stego-response header to stegoclient")
            self.client.send(resp_to_client)

            start = time.time()
            chunk_count = 0
            for chunk in self._split_into_chunks(
                stego_resp, cfg.MAX_CONTENT_LENGTH
            ):
                # Send chunks
                log.debug(f"Sending chunk with size: {len(chunk)} bytes")
                self._write_chunks(
                    stego.embed(cover=cover.copy(), message=chunk)
                )
                chunk_count += 1

            end = time.time()
            # send "end of chunks" trailer
            self._write_end_of_chunks()
            log.debug(f"{chunk_count} chunks sent in {end - start:.2f}s.")
        else:
            # Encapsulate response inside response to stego client
            log.debug("Embedding response from website in stego-response")

            start = time.time()
            stego_medium = stego.embed(cover=cover.copy(), message=stego_resp)
            end = time.time()
            log.debug(f"Took {end - start:.2f}s to embed response in stego-response")

            header.add_header("Content-Length", str(len(stego_medium)))

            resp_to_client = self._build_response(
                cfg.STEGO_HTTP_VERSION, h.status, h.reason, header, stego_medium
            )

            # Relay the message
            log.debug("Relaying stego-response to stegoclient")
            self.client.send(resp_to_client)

        cover.close()
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
