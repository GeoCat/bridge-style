import json

from . import fromgeostyler
from . import togeostyler


def toGeostyler(style, options=None):
    return togeostyler.convert(json.loads(style), options)


def fromGeostyler(style, options=None):
    return fromgeostyler.convert(style, options)

