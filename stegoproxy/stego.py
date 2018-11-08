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
from zlib import compress, decompress

from PIL import Image

import piexif
import stegano
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


def stegano_hide_exif(cover, message, img_format="JPEG"):
    """Hide a message (string) in an image."""
    text = compress(to_bytes(message))

    if img_format is None:
        img_format = cover.format

    if "exif" in cover.info:
        exif_dict = piexif.load(cover.info["exif"])
    else:
        exif_dict = {}
        exif_dict["0th"] = {}
    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = text
    exif_bytes = piexif.dump(exif_dict)

    # save the image in memory
    stego_image = io.BytesIO()
    cover.save(stego_image, format=img_format, exif=exif_bytes)
    cover.close()
    return stego_image.getvalue()


def stegano_extract_exif(medium):
    """Find a message in an image."""
    img = Image.open(medium)
    try:
        if img.format in ["JPEG", "TIFF"]:
            if "exif" in img.info:
                exif_dict = piexif.load(img.info.get("exif", b""))
                description_key = piexif.ImageIFD.ImageDescription
                encoded_message = exif_dict["0th"][description_key]
            else:
                encoded_message = b""
        else:
            raise ValueError("Given file is neither JPEG nor TIFF.")
    finally:
        img.close()

    return decompress(encoded_message)


def null_encode(cover, message):
    # all messages get base64 encoded by default
    return to_bytes(message)


def null_decode(medium):
    # medium is a BytesIO object
    return medium.getvalue()


def embed(cover, message):
    """Embeds a message inside a stego medium.

    param cover: The cover object to embed the message in.
    param message: The message to be embedded.
    """
    from stegoproxy.config import cfg
    return cfg.STEGO_ALGORITHM["in"](cover, to_unicode(message))


def extract(medium):
    """Extracts a message from a stego medium.

    :param medium: The medium where hidden message is located in.
    """
    from stegoproxy.config import cfg
    return base64.b64decode(cfg.STEGO_ALGORITHM["out"](medium))
