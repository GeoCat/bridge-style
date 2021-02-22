from . import togeostyler
from . import fromgeostyler


def toGeostyler(style, options=None):
    return togeostyler.convert(style, options)  # TODO


def fromGeostyler(style, options=None):
    sld, warnings = fromgeostyler.convert(style, options)
    return sld
