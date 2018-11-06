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
import os

import stegano
from stegoproxy.config import cfg
from stegoproxy.utils import to_bytes, to_native, to_unicode

log = logging.getLogger(__name__)


INPUT_IMAGES = ["img1.png"]


def stegano_hide_lsb(message):
    # TODO: randomize
    image_path = os.path.join(cfg.COVER_OBJECTS, INPUT_IMAGES[0])
    image_format = image_path.split(".", maxsplit=1)[1]

    message = to_unicode(base64.b64encode(message))
    image = stegano.lsb.hide(image_path, message, auto_convert_rgb=True)
    stego_image = io.BytesIO()
    image.save(stego_image, image_format)
    return stego_image.getvalue()


def stegano_extract_lsb(medium):
    message = stegano.lsb.reveal(medium)
    message = base64.b64decode(message)
    return message


def base64_encode(message):
    return base64.b64encode(message)


def base64_decode(medium):
    return base64.b64decode(medium.getvalue())


AVAILABLE_STEGOS = {
    "base64": {"in": base64_encode, "out": base64_decode},
    "stegano_lsb": {"in": stegano_hide_lsb, "out": stegano_extract_lsb}
}


def embed(message):
    """Embeds a message inside a stego medium.

    param message: The message to be embedded.
    """
    return AVAILABLE_STEGOS[cfg.STEGO_ALGORITHM]["in"](message)


def extract(medium):
    """Extracts a message from a stego medium.

    :param medium: The medium where hidden message is located in.
    """
    return AVAILABLE_STEGOS[cfg.STEGO_ALGORITHM]["out"](medium)
