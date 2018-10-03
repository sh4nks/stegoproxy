import sys


def to_bytes(x, charset=sys.getdefaultencoding(), errors="strict"):
    if x is None:
        return None
    if isinstance(x, (bytes, bytearray, memoryview)):  # noqa
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
