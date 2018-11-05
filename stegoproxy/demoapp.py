# -*- coding: utf-8 -*-
"""
    stegoproxy.demoapp
    ~~~~~~~~~~~~~~~~~~

    This module contains a simple demo Flask app and
    is mostly used for testing the functionality of the
    proxy.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import os

from flask import Flask, Response, send_from_directory, stream_with_context

app = Flask(__name__)

tpl = """\
<html>
<head>
<link rel="shortcut icon" href="data:image/x-icon;," type="image/x-icon">
<title>STEGO PROXY HTTPS</title>
</head>
<body>{body}</body>
</html>
"""


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


@app.route("/randomfile/<int:size>")
@app.route("/randomfile")
def random_file(size=None):
    # base64 /dev/urandom | head -c 1000000000 > 1000file.txt
    sizes = [2, 10, 100, 1000]
    filename = "2file.txt"
    if size in sizes:
        filename = "%sfile.txt"

    return send_from_directory(
        os.path.dirname(app.root_path), filename, as_attachment=False
    )
