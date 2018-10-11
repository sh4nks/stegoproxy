# -*- coding: utf-8 -*-
from flask import Flask


stegoserver = Flask(__name__)


@stegoserver.route('/', defaults={'path': ''})
@stegoserver.route('/<path:path>')
def catch_all(path):
    print(path)
    return


def main():
    stegoserver.run(port=5001)


if __name__ == '__main__':
    main()

