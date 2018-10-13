# -*- coding: utf-8 -*-
import base64


def base64_decoder(data):
    return base64.b64decode(data)


def decode(data):
    """decoder API"""
    return base64_decoder(data)
