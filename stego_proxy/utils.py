# -*- coding: utf-8 -*-
"""
    stego_proxy.utils
    ~~~~~~~~~~~~~~~~~

    This module contains some utilities that are used
    throughout the project.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import sys


def to_bytes(x, charset=sys.getdefaultencoding(), errors="strict"):
    if x is None:
        return None
    if isinstance(x, (bytes, bytearray, memoryview, int)):  # noqa
        return bytes(x)
    if isinstance(x, str):
        return x.encode(charset, errors)
    raise TypeError("Expected bytes")


def to_native(x, charset=sys.getdefaultencoding(), errors="strict"):
    if x is None or isinstance(x, str):
        return x
    return x.decode(charset, errors)


def to_unicode(
    x,
    charset=sys.getdefaultencoding(),
    errors="strict",
    allow_none_charset=False,
):
    if x is None:
        return None
    if not isinstance(x, bytes):
        return str(x)
    if charset is None and allow_none_charset:
        return x
    return x.decode(charset, errors)


def append_text(text_to_append, file_path):
    """Appends some text in a picture."""
    with open(file_path, "ab") as fp:
        fp.write(text_to_append.encode("utf-8"))


def extract_text(file_path):
    """Extracts a text from a picture."""
    # doesn't check the size of the file - be careful when opening large files!
    with open(file_path, "rb") as fp:
        s = fp.read()
        position = s.rfind(b"\xff\xd9") + 2
        return s[position:]
