# -*- coding: utf-8 -*-
"""
    stegoproxy.demoapp
    ~~~~~~~~~~~~~~~~~~

    This module contains a simple demo Flask app and
    is mostly used for testing the functionality of the
    proxy.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: GPLv3, see LICENSE for more details.
"""
import os
from time import sleep

from flask import (Flask, Response, render_template_string,
                   send_from_directory, stream_with_context)

__base_dir = os.path.dirname(os.path.dirname(__file__))
static_folder = os.path.join(__base_dir, "coverobjects")


app = Flask(__name__, static_folder=static_folder)


tpl = """\
<html lang="en">
<head>
<meta charset="UTF-8">
<link rel="shortcut icon" href="data:image/x-icon;," type="image/x-icon">
<title>Stego Proxy Testing Facilities</title>
</head>
<body>
{% if content %}
<img src={{url_for('static', filename='handsome.png')}} />
<img src={{url_for('static', filename='handsome.jpeg')}} />
{% else %}
{{body|safe}}</body>
{% endif %}
</html>
"""


@app.route("/")
def hello_world():
    body = (
        "Hello, I am Stegosaurus, a wild algorithmic animal that "
        "tries to stay hidden in the shadows of the world wide web."
    )
    return render_template_string(tpl, body=body)


@app.route("/externcontent")
def externcontent():
    body = "<img src='https://flaskbb.net/static/imgs/index.png' />"
    return render_template_string(tpl, body=body)


@app.route("/content")
def content():
    return render_template_string(tpl, content=True)


@app.route("/streaming")
def streaming():
    def generate():
        for i in range(100000):
            yield "Hello %s" % i

    return Response(stream_with_context(generate()))


@app.route("/randomfile")
def random_file():
    # base64 /dev/urandom | head -c 1000000000 > 1000file.txt
    filename = "10file.txt"
    return send_from_directory(
        os.path.dirname(app.root_path), filename, as_attachment=False
    )
