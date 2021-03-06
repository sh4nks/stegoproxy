# -*- coding: utf-8 -*-
"""
    stegoproxy.cli
    ~~~~~~~~~~~~~~

    Console scripts for the stego proxy.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: GPLv3, see LICENSE for more details.
"""
import logging
import logging.config
import os
import sys

import click

from stegoproxy.config import cfg
from stegoproxy.demoapp import app
from stegoproxy.httpserver import run_server
from stegoproxy.stegoclient import ClientProxyHandler
from stegoproxy.stegoserver import ServerProxyHandler

logging.config.dictConfig(cfg.LOGGING_CONFIG)
log = logging.getLogger("stegoproxy")
LOG_LEVELS = {
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


@click.group()
@click.version_option()
def main(args=None):
    """Console script for stegoproxy."""


@main.command(context_settings=dict(max_content_width=120))
@click.option(
    "--host",
    "-h",
    default="127.0.0.1:8888",
    show_default=True,
    help="Address to bind to\n",
)
@click.option(
    "--remote",
    "-r",
    default="127.0.0.1:9999",
    show_default=True,
    help="The remote server",
)
@click.option(
    "--algorithm",
    "-a",
    default="null",
    show_default=True,
    help="The stego algorithm. Use 'stegano_lsb', 'stegano_exif' or 'null'",
)
@click.option(
    "--no-reloader", is_flag=True, default=True, help="Disable the reloader"
)
@click.option(
    "--no-threading", is_flag=True, default=True, help="Disable multithreading"
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    help="DEBUG, INFO, WARNING or ERROR",
)
def client(host, remote, algorithm, no_reloader, no_threading, log_level):
    """Runs the client side proxy."""
    log.setLevel(LOG_LEVELS.get(log_level, "INFO"))
    host, port = host.split(":")
    remote_ip, remote_port = remote.split(":")

    cfg.REMOTE_ADDR = (remote_ip, int(remote_port))
    cfg.ALGORITHM = algorithm.lower()
    cfg.STEGO_ALGORITHM = cfg.AVAILABLE_STEGOS[cfg.ALGORITHM]

    run_server(
        hostname=host,
        port=int(port),
        request_handler=ClientProxyHandler,
        use_reloader=no_reloader,
        threaded=no_threading,
        what="client",
        algorithm=cfg.ALGORITHM
    )


@main.command(context_settings=dict(max_content_width=120))
@click.option(
    "--host",
    "-h",
    default="127.0.0.1:9999",
    show_default=True,
    help="Address to bind to\n",
)
@click.option(
    "--algorithm",
    "-a",
    type=click.Choice(cfg.AVAILABLE_STEGOS.keys()),
    default="null",
    show_default=True,
    help="The stego algorithm",
)
@click.option(
    "--no-reloader", is_flag=True, default=True, help="Disable the reloader"
)
@click.option(
    "--no-threading", is_flag=True, default=True, help="Disable multithreading"
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    help="DEBUG, INFO, WARNING or ERROR",
)
def server(host, algorithm, no_reloader, no_threading, log_level):
    """Runs the server side proxy."""
    log.setLevel(LOG_LEVELS.get(log_level, "INFO"))
    host, port = host.split(":")

    cfg.REMOTE_ADDR = (host, int(port))
    cfg.ALGORITHM = algorithm.lower()
    cfg.STEGO_ALGORITHM = cfg.AVAILABLE_STEGOS[cfg.ALGORITHM]

    run_server(
        hostname=host,
        port=int(port),
        request_handler=ServerProxyHandler,
        use_reloader=no_reloader,
        threaded=no_threading,
        what="server",
        algorithm=cfg.ALGORITHM
    )


@main.command(context_settings=dict(max_content_width=120))
@click.option(
    "--host",
    "-h",
    default="127.0.0.1:5000",
    show_default=True,
    help="Address to bind to\n",
)
@click.option(
    "--use-https", is_flag=True, default=False, help="Use HTTPS instead of HTTP"
)
def demoapp(host, use_https):
    """Runs a simple demo web server."""
    host, port = host.split(":")
    run_config = dict(host=host, port=int(port), debug=True)

    if use_https:
        run_config["ssl_context"] = (
            os.path.join(cfg.BASE_DIR, "stego.local.cert.pem"),
            os.path.join(cfg.BASE_DIR, "stego.local.key.pem"),
        )

    app.run(**run_config)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
