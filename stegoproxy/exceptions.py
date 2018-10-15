# -*- coding: utf-8 -*-
"""
    stegoproxy.connection
    ~~~~~~~~~~~~~~~~~~~~~

    This module contains the exceptions that are used by
    the stego proxy.

    :copyright: (c) 2018 by Peter Justin, see AUTHORS for more details.
    :license: All Rights Reserved, see LICENSE for more details.
"""


class UnsupportedSchemeException(Exception):
    pass


class UnsupportedStegoAlgorithm(Exception):
    pass
