from . import fromgeostyler
from . import togeostyler


def toGeostyler(style, options=None):
    return togeostyler.convert(style, options)  # TODO


def fromGeostyler(style, options=None):
    mb, warnings = fromgeostyler.convert(style, options)
    return mb
