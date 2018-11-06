# -*- coding: utf-8 -*-
"""
    stegoproxy.stego
    ~~~~~~~~~~~~~~~~

    This module contains the logic for embedding messages in stego mediums
    and extracting them again.

    A stego object can be constructed using following equation::

           stego-medium = frame + message [+ key]

    :copyright: (c) 2018 by Peter Justin.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import base64
import io
import logging

import stegano
from stegoproxy.config import cfg
from stegoproxy.utils import to_bytes, to_native, to_unicode

log = logging.getLogger(__name__)


INPUT_IMAGES = ["img1.png"]


def stegano_hide_lsb(cover, message):
    # hide the message inside the cover
    image = stegano.lsb.hide(cover, message, auto_convert_rgb=True)
    # save the image in memory
    stego_image = io.BytesIO()
    image.save(stego_image, format="png")
    # return the in memory representation of the image
    return stego_image.getvalue()


def stegano_extract_lsb(medium):
    message = stegano.lsb.reveal(medium)
    return message


def null_encode(cover, message):
    # all messages get base64 encoded by default
    return message


def null_decode(medium):
    return medium


AVAILABLE_STEGOS = {
    "null": {"in": null_encode, "out": null_decode},
    "stegano_lsb": {"in": stegano_hide_lsb, "out": stegano_extract_lsb}
}


def embed(cover, message):
    """Embeds a message inside a stego medium.

    param cover: The cover object to embed the message in.
    param message: The message to be embedded.
    """
    return AVAILABLE_STEGOS[cfg.STEGO_ALGORITHM]["in"](cover, to_unicode(message))


def extract(medium):
    """Extracts a message from a stego medium.

    :param medium: The medium where hidden message is located in.
    """
    message = AVAILABLE_STEGOS[cfg.STEGO_ALGORITHM]["out"](medium)
    # all messages are base64 encoded
    # TODO: Fix this ugly hack
    return base64.b64decode(message)
