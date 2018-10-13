# -*- coding: utf-8 -*-
"""
    stego_proxy.cli
    ~~~~~~~~~~~~~~~

    Console scripts for the stego proxy.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import sys
import click
import logging
import logging.config

from stego_proxy import config
from stego_proxy.server import run_server
from stego_proxy.stegoclient import ProxyHandler


logging.config.dictConfig(config.LOG_DEFAULT_CONF)
log = logging.getLogger("stego_proxy")
LOG_LEVELS = {
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


@click.group()
@click.version_option()
def main(args=None):
    """Console script for stego_proxy."""


@main.command()
@click.option(
    "--host", "-h", default="127.0.0.1:8888", show_default=True, help="Address to bind to\n"
)
@click.option("--remote", "-r", default="127.0.0.1:9999", show_default=True, help="The remote server")
@click.option(
    "--no-reloader", is_flag=True, default=True, help="Disable the reloader"
)
@click.option(
    "--no-threading", is_flag=True, default=True, help="Disable multithreading"
)
@click.option(
    "--log-level", default="INFO", show_default=True, help="DEBUG, INFO, WARNING or ERROR"
)
def client(host, remote, no_reloader, no_threading, log_level):
    """Runs the client side proxy."""
    log.setLevel(LOG_LEVELS.get(log_level, "INFO"))
    host, port = host.split(":")

    run_server(
        hostname=host,
        port=int(port),
        request_handler=ProxyHandler,
        use_reloader=no_reloader,
        threaded=no_threading,
    )


@main.command()
@click.option(
    "--host", "-h", default="127.0.0.1:8888", show_default=True, help="Address to bind to\n"
)
@click.option(
    "--no-reloader", is_flag=True, default=True, help="Disable the reloader"
)
@click.option(
    "--no-threading", is_flag=True, default=True, help="Disable multithreading"
)
@click.option(
    "--log-level", default="INFO", show_default=True, help="DEBUG, INFO, WARNING or ERROR"
)
def server(host, no_reloader, no_threading, log_level):
    """Runs the server side proxy."""
    log.setLevel(LOG_LEVELS.get(log_level, "INFO"))
    host, port = host.split(":")

    run_server(
        hostname=host,
        port=int(port),
        request_handler=ProxyHandler,
        use_reloader=no_reloader,
        threaded=no_threading,
    )



if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
