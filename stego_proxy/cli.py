# -*- coding: utf-8 -*-

"""Console script for stego_proxy."""
import sys
import click

from .server import start_server


@click.group()
def main(args=None):
    """Console script for stego_proxy."""


@main.command()
def server():
    """A server"""
    click.secho("Starting proxy server...")
    start_server()


@main.command()
def client():
    """A client"""
    click.secho("Stego Proxy Consumer")


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
