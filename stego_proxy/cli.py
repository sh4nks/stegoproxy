# -*- coding: utf-8 -*-

"""Console script for stego_proxy."""
import sys
import click

from stego_proxy.proxyserver import run_server
from stego_proxy.proxy import ProxyRequestHandler


@click.group()
def main(args=None):
    """Console script for stego_proxy."""


@main.command()
@click.option(
    "--host", "-h", default="127.0.0.1", help="Address to bind the server to."
)
@click.option(
    "--port", "-p", default=8888, type=int, help="The port to listen no."
)
@click.option(
    "--no-reloader", is_flag=True, default=True, help="Disable the reloader."
)
@click.option(
    "--no-threading",
    is_flag=True,
    default=True,
    help="Disable multithreading.",
)
def client(host, port, no_reloader, no_threading):
    """Runs the client side proxy."""
    run_server(
        hostname=host,
        port=port,
        request_handler=ProxyRequestHandler,
        use_reloader=no_reloader,
        threaded=no_threading
    )


@main.command()
def server():
    """Runs the server side proxy."""
    click.secho("Stego Proxy Consumer")


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
