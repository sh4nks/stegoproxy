# -*- coding: utf-8 -*-
from flask import Flask


stegoclient = Flask(__name__)


@stegoclient.route('/', defaults={'path': ''})
@stegoclient.route('/<path:path>')
def relay(path):
    pass


def main():
    stegoclient.run(port=5002)


if __name__ == '__main__':
    main()
