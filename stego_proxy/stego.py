# -*- coding: utf-8 -*-
"""
    stego_proxy.stego
    ~~~~~~~~~~~~~~~~~

    This module contains the logic for embedding messages in stego mediums
    and extracting them again.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""
import base64
import logging
from stego_proxy.exceptions import UnsupportedStegoAlgorithm
from stego_proxy.utils import to_bytes


log = logging.getLogger(__name__)


class StegoAlgorithm(object):

    def __init__(self, algorithm):
        if algorithm not in self._default_stego:
            raise UnsupportedStegoAlgorithm(
                f"Stego algorithm {algorithm} not supported."
            )
        self.name = algorithm  # name of the algorithm
        self.algorithm = self._default_stego[algorithm]

    def embed(self, message):
        """Embeds a message inside a stego medium.

        :param message: The message to be embedded.
        """
        return self.algorithm["in"](message)

    def extract(self, medium):
        """Extracts a message from a stego medium.

        :param medium: The medium where hidden message is located in.
        """
        return self.algorithm["out"](medium)


class StegoMedium(StegoAlgorithm):
    """Represents the stego medium. As a general rule, a stego object can
       be constructed using following equation::

           stego-medium = frame + message [+ key]
    """
    _default_stego = {
        "plain": {"in": lambda x: x[::-1], "out": lambda x: x[::-1]},
        "base64": {"in": base64.b64encode, "out": base64.b64decode},
    }

    def __init__(self, message=None, medium=None, frame=None, algorithm=None):
        """Constructs a stego medium.

        :param message: The message to hide or extract.
        :param medium: The stego medium that contains the hidden message.
        :param frame: The cover object where the message will be embedded in.
        :param algorithm: The algorithm to use for the embedding process.
        """
        algo = algorithm if algorithm is not None else "plain"
        super(StegoMedium, self).__init__(algo)

        self.message = message
        self.frame = frame
        self.medium = medium

    def embed(self):
        """Embeds a message inside a frame."""
        if self.medium:
            return self

        self.medium = self.algorithm["in"](self.message)
        return self

    def extract(self):
        """Extracts a message from a stego medium."""
        if self.message:
            return self

        self.message = self.algorithm["out"](self.medium)
        return self

    def __repr__(self):
        return f"<StegoMessage: {self.message} > {self.medium}>"
