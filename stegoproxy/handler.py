# -*- coding: utf-8 -*-
"""
    stegoproxy.handler
    ~~~~~~~~~~~~~~~~~~

    This module contains a basic HTTP Proxy Handler.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import base64
import datetime
import email
import io
import json
import logging
import os
import random
import re
import select
from html.parser import HTMLParser
from http.client import _UNKNOWN, HTTPMessage, HTTPResponse, IncompleteRead
from http.server import BaseHTTPRequestHandler
from urllib.parse import ParseResult, parse_qsl, urlparse, urlsplit, urlunparse

from PIL import Image

from stegoproxy import stego
from stegoproxy.config import cfg
from stegoproxy.connection import Client, Server
from stegoproxy.exceptions import UnsupportedSchemeException
from stegoproxy.utils import to_bytes, to_unicode

log = logging.getLogger(__name__)
CRLF = b"\r\n"
HTTP_VERSIONS = {10: "HTTP/1.0", 11: "HTTP/1.1"}


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
                value.append(stego.extract(io.BytesIO(chunk)))
                self.chunk_left = 0
            return b"".join(value)
        except IncompleteRead:
            raise IncompleteRead(b"".join(value))


class BaseProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, request, client_address, server):
        self.is_connect = False
        self.start_time = self._now()
        self.last_activity = self.start_time
        self._headers_buffer = []
        BaseHTTPRequestHandler.__init__(self, request, client_address, server)

    def _now(self):
        return datetime.datetime.utcnow()

    def _inactive_for(self):
        return (self._now() - self.last_activity).seconds

    def _is_inactive(self):
        return self._inactive_for() > 30

    def _connect_to_host(self):
        # Get hostname and port to connect to
        if self.is_connect:
            self.hostname, self.port = self.path.split(":")
        else:
            u = urlparse(self.path)
            if u.scheme != "http":
                raise UnsupportedSchemeException(
                    "Unknown scheme %s" % repr(u.scheme)
                )
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

        self.server = Server(host=self.hostname, port=int(self.port))
        self.client = Client(self.connection)  # reusing the connection here

    def _get_waitable_lists(self):
        rlist, wlist, xlist = [self.client.conn], [], []
        log.debug("*** watching client for read ready")

        if self.client.has_buffer():
            log.debug(
                "pending client buffer found, watching client for write ready"
            )
            wlist.append(self.client.conn)

        if self.server and not self.server.closed:
            log.debug(
                "connection to server exists, watching server for read ready"
            )
            rlist.append(self.server.conn)

        if self.server and not self.server.closed and self.server.has_buffer():
            log.debug(
                "connection to server exists and pending server "
                "buffer found, watching server for write ready"
            )
            wlist.append(self.server.conn)

        return rlist, wlist, xlist

    def _process_request(self, data):
        # once we have connection to the server we don't parse the
        # http request packets any further, instead just pipe incoming
        # data from client to server
        if self.server and not self.server.closed:
            log.debug("processing request")
            self.server.write(data)
            return

    def _process_response(self, data):
        # write data for client
        log.debug("processing response")
        self.client.write(data)

    def _process_wlist(self, w):
        if self.client.conn in w:
            log.debug("client is ready for writes, flushing client buffer")
            self.client.flush()

        if self.server and not self.server.closed and self.server.conn in w:
            log.debug("server is ready for writes, flushing server buffer")
            self.server.flush()

    def _process_rlist(self, r):
        if self.client.conn in r:
            log.debug("client is ready for reads, reading")
            data = self.client.recv()

            if not data:
                log.debug("client closed connection, breaking")
                return True

            try:
                self._process_request(data)
            except Exception as e:
                log.exception(e)
                self.client.write(
                    CRLF.join(
                        [
                            b"HTTP/1.1 502 Bad Gateway",
                            b"Proxy-agent: stegoproxy.py v0.1",
                            b"Content-Length: 11",
                            b"Connection: close",
                            CRLF,
                        ]
                    )
                    + b"Bad Gateway"
                )
                self.client.flush()
                return True

        if self.server and not self.server.closed and self.server.conn in r:
            log.debug("server is ready for reads, reading")
            data = self.server.recv()
            self.last_activity = self._now()

            if not data:
                log.debug("server closed connection")
                self.server.close()
            else:
                self._process_response(data)

        return False

    def _process_connect(self):
        while True:
            rlist, wlist, xlist = self._get_waitable_lists()
            ready_to_read, ready_to_write, in_error = select.select(
                rlist, wlist, xlist, 10
            )

            self._process_wlist(ready_to_write)
            if self._process_rlist(ready_to_read) or in_error:
                break

    def _write_end_of_chunks(self):
        self.client.send(b"0\r\n\r\n")

    def _write_chunks(self, chunk):
        # no need to convert to "to_bytes" - chunk is already of type bytes
        self.client.send(b"%X\r\n%s\r\n" % (len(chunk), chunk))

    def _split_into_chunks(self, seq, chunk_size):
        """Splits a sequence into evenly sized chunks."""
        for i in range(0, len(seq), chunk_size):
            yield seq[i : i + chunk_size]

    def _calc_max_size(self, cover):
        w, h = cover.size
        # each pixel consists of RGB  thus we need * 3
        # / 8 because ONE character is represented by 8 bits
        return int(w * h * 3 / 8) - 1024

    def _encode(self, s):
        return base64.b64encode(s)

    def _decode(self, s):
        return base64.b64decode(s)

    def _build_response_header(self, version, status, reason, headers):
        """Builds a response header.

        :param version: The HTTP Version. This can either an integer where
                        10 defines HTTP/1.0 and 11 defines HTTP/1.1 or a
                        string like "HTTP/1.1".
        :param status: The HTTP Status Code like "200".
        :param reason: The HTTP Status Code Reason like "OK" for a status code
                        200.
        :param headers: Either a string consisting of all headers or a
                        HTTPMessage object.
        """
        if isinstance(headers, (HTTPMessage, email.message.Message)):
            headers = headers.as_bytes()
        if isinstance(version, int):
            version = HTTP_VERSIONS[version]

        header = (
            # HTTP/1.1 200 OK
            to_bytes("%s %s %s" % (version, status, reason))
            + CRLF
            # Server, Date, Content-Type,...
            + headers
        )

        return header

    def _build_request_header(self, command, path, version, headers):
        """Builds a request header.

        :param command: The HTTP Command like "GET"
        :param path: The path to request like "/"
        :param version: The HTTP Version. This can either an integer where
                        10 defines HTTP/1.0 and 11 defines HTTP/1.1 or a
                        string like "HTTP/1.1".
        :param headers: Either a string consisting of all headers or a
                        HTTPMessage object.
        """
        if isinstance(headers, (HTTPMessage, email.message.Message)):
            headers = headers.as_bytes()
        if isinstance(version, int):
            version = HTTP_VERSIONS[version]

        header = (
            # GET / HTTP/1.1
            to_bytes("%s %s %s" % (command, path, version))
            + CRLF
            # Host, User-Agent, ...
            + headers
        )

        return header

    def _build_request(self, command, path, request_version, headers, body):
        return (
            # Headers
            self._build_request_header(command, path, request_version, headers)
            # Add Request Body
            + body
        )

    def _build_response(self, request_version, status, reason, headers, body):
        return (
            # Headers
            self._build_response_header(
                request_version, status, reason, headers
            )
            # Body
            + body
        )

    def _build_stego_request(
        self, command, path, request_version, headers, body
    ):
        return self._encode(
            self._build_request(command, path, request_version, headers, body)
        )

    def _build_stego_response(
        self, request_version, status, reason, headers, body
    ):
        return self._encode(
            self._build_response(request_version, status, reason, headers, body)
        )

    def _get_cover_object(self):
        # i = cfg.COVER_OBJECTS[random.randint(0, len(cfg.COVER_OBJECTS) - 1)]
        i = cfg.COVER_OBJECTS[0]
        i_path = os.path.join(cfg.COVER_PATH, i)
        im = Image.open(i_path)
        return im

    def _get_hostaddr_from_headers(self, headers):
        # first line ([0]) is request line
        raw_headers = to_unicode(headers).split("\r\n")[1]
        headers = email.message_from_string(raw_headers)
        addr = headers["host"].split(":")
        return (addr[0], 80) if len(addr) <= 1 else (addr[0], addr[1])

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
        log.info(f"{self.command} {self.path}")
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

        # Build request which will be sent to the client
        # [Browser <--> Proxy] <--> Website
        client_request = (
            # Add "GET / HTTP/1.1..." to the request"
            b" ".join(
                [
                    to_bytes(self.command),
                    to_bytes(self.path),
                    to_bytes(self.request_version),
                ]
            )
            + CRLF
            # Add Headers to the request (Host:..., User-Agent:...)
            + self.headers.as_bytes()
            + CRLF
            + request_body
        )

        # Send it down the pipe!
        self.server.send(to_bytes(client_request))

        # Parse response
        h = HTTPResponse(self.server.conn)
        h.begin()

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
                    to_bytes(h.status),
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

        self.print_info(self, request_body, orig_response, response_body)

    def log_message(self, format, *args):
        log.debug(
            "%s - - [%s] %s"
            % (
                self.address_string(),
                self.log_date_time_string(),
                format % args,
            )
        )

    def filter_headers(self, headers):
        # http://tools.ietf.org/html/rfc2616#section-13.5.1
        hop_by_hop = (
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        )
        for k in hop_by_hop:
            del headers[k]

        return headers

    def print_info(self, req, req_body, res, res_body):
        def _parse_qsl(s):
            return "\n".join(
                "%-20s %s" % (k, v)
                for k, v in parse_qsl(s, keep_blank_values=True)
            )

        HTTP_VERSIONS = {10: "HTTP/1.0", 11: "HTTP/1.1"}

        req_header_text = "%s %s %s\n%s" % (
            req.command,
            req.path,
            req.request_version,
            req.headers,
        )
        res_header_text = "%s %d %s\n%s" % (
            HTTP_VERSIONS.get(res.version, ""),
            res.status,
            res.reason,
            res.headers,
        )

        log.debug("==== REQUEST HEADER ====\n%s" % req_header_text)

        u = urlsplit(req.path)
        if u.query:
            query_text = _parse_qsl(u.query)
            log.debug("==== QUERY PARAMETERS ====\n%s" % query_text)

        cookie = req.headers.get("Cookie", "")
        if cookie:
            cookie = _parse_qsl(re.sub(r";\s*", "&", cookie))
            log.debug("==== COOKIE ====\n%s" % cookie)

        auth = req.headers.get("Authorization", "")
        if auth.lower().startswith("basic"):
            token = auth.split()[1].decode("base64")
            log.debug("==== BASIC AUTH ====\n%s" % token)

        if req_body is not None:
            req_body_text = None
            content_type = req.headers.get("Content-Type", "")

            if content_type.startswith("application/x-www-form-urlencoded"):
                req_body_text = parse_qsl(req_body)
            elif content_type.startswith("application/json"):
                try:
                    json_obj = json.loads(req_body)
                    json_str = json.dumps(json_obj, indent=2)
                    if json_str.count("\n") < 50:
                        req_body_text = json_str
                    else:
                        lines = json_str.splitlines()
                        req_body_text = "%s\n(%d lines)" % (
                            "\n".join(lines[:50]),
                            len(lines),
                        )
                except ValueError:
                    req_body_text = req_body
            elif len(req_body) < 1024:
                req_body_text = req_body

            if req_body_text:
                log.debug("==== REQUEST BODY ====\n%s" % req_body_text)

        log.debug("==== RESPONSE HEADER ====\n%s" % res_header_text)

        cookies = res.headers["Set-Cookie"]
        if cookies:
            cookies = "\n".join(cookies)
            log.debug("==== SET-COOKIE ====\n%s" % cookies)

        if res_body is not None:
            res_body_text = None
            content_type = res.headers.get("Content-Type", "")

            if content_type.startswith("application/json"):
                try:
                    json_obj = json.loads(res_body)
                    json_str = json.dumps(json_obj, indent=2)
                    if json_str.count("\n") < 50:
                        res_body_text = json_str
                    else:
                        lines = json_str.splitlines()
                        res_body_text = "%s\n(%d lines)" % (
                            "\n".join(lines[:50]),
                            len(lines),
                        )
                except ValueError:
                    res_body_text = res_body
            elif content_type.startswith("text/html"):
                m = re.search(
                    b"<title[^>]*>\s*([^<]+?)\s*</title>", res_body, re.I
                )
                if m:
                    h = HTMLParser()
                    log.debug(
                        "==== HTML TITLE ====\n%s"
                        % h.unescape(m.group(1).decode("utf-8"))
                    )
            elif content_type.startswith("text/") and len(res_body) < 1024:
                res_body_text = res_body

            if res_body_text:
                log.debug("==== RESPONSE BODY ====\n%s" % res_body_text)

    def __getattr__(self, item):
        if item.startswith("do_"):
            return self.do_COMMAND
