# -*- coding: utf-8 -*-
import base64


def base64_encoder(data):
    return base64.b64encode(data)


def encode(data):
    """encoder API"""
    return base64_encoder(data)
