# -*- coding: utf-8 -*-
"""
    stegoproxy.connection
    ~~~~~~~~~~~~~~~~~~~~~

    This module contains classes that are shared
    between the client and the server.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import logging
import socket
import ssl

log = logging.getLogger(__name__)


class Connection(object):
    """TCP server/client connection abstraction."""

    def __init__(self, what):
        self.buffer = b""
        self.closed = False
        self.what = what  # server or client

    def send(self, data):
        """Sends data down the socket."""
        return self.conn.send(data)

    def recv(self, bytes=8192):
        """Recieves data from the socket."""
        try:
            data = self.conn.recv(bytes)
            if len(data) == 0:
                log.debug("recvd 0 bytes from %s", self.what)
                return None
            log.debug("rcvd %d bytes from %s", len(data), self.what)
            return data
        except Exception as e:
            log.exception(
                "Exception while receiving from connection %s %r "
                "with reason %r",
                self.what,
                self.conn,
                e,
            )
            return None

    def close(self):
        """Closes the connection."""
        self.conn.close()
        self.closed = True

    def buffer_size(self):
        """Returns the current buffer size."""
        return len(self.buffer)

    def has_buffer(self):
        """Checks if the buffer is > 0."""
        return self.buffer_size() > 0

    def write(self, data):
        """Writes data to the buffer."""
        self.buffer += data

    def flush(self):
        """Flushes the buffer."""
        sent = self.send(self.buffer)
        self.buffer = self.buffer[sent:]
        log.debug("flushed %d bytes to %s", sent, self.what)


class Server(Connection):
    """Establish connection to destination server."""

    def __init__(self, conn=None, host=None, port=None):
        super(Server, self).__init__(b"server")
        if host and port:
            self.conn = socket.create_connection((host, port))
        else:
            self.conn = conn


class Client(Connection):
    """Accepted client connection."""

    def __init__(self, conn=None, host=None, port=None):
        super(Client, self).__init__(b"client")
        if host and port:
            self.conn = socket.create_connection((host, port))
        else:
            self.conn = conn
