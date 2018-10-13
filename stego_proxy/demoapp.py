# -*- coding: utf-8 -*-
"""
    stego_proxy.demoapp
    ~~~~~~~~~~~~~~~~~~~

    This module contains a simple demo Flask app and
    is mostly used for testing the functionality of the
    proxy.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import sys
from flask import Flask, Response, request, stream_with_context


app = Flask(__name__)

tpl = """<html><head><link rel="shortcut icon" href="data:image/x-icon;," type="image/x-icon"> <title>STEGO PROXY HTTPS</title></head><body>{body}</body></html>"""


@app.route("/")
def hello_world():
    return tpl.format(body="yeet this stego thingy is lit af")


@app.route("/content")
def content():
    return tpl.format(
        body="<img src='https://flaskbb.net/static/imgs/index.png' />"
    )


@app.route("/streaming")
def streaming():
    def generate():
        for i in range(100000):
            yield "Hello %s" % i

    return Response(stream_with_context(generate()))


if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
        app.run(
            port=port,
            ssl_context=("../stego.local.cert.pem", "../stego.local.key.pem"),
            debug=True,
        )
    app.run(port=port, debug=True)
