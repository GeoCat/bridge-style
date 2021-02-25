import json

from . import fromgeostyler
from . import togeostyler


def toGeostyler(style, options=None):
    geostyler, _, _ = togeostyler.convert(json.loads(style), options)
    return geostyler


def fromGeostyler(style, options=None):
    arcgisjson, warnings = fromgeostyler.convert(style, options)
    return arcgisjson
