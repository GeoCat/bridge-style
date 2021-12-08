from . import fromgeostyler
from . import togeostyler


def toGeostyler(style, options=None):
    return togeostyler.convert(style, options)  # TODO


def fromGeostyler(style, options=None):
    return fromgeostyler.convert(style, options)
