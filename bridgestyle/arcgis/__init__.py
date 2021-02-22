import json
from . import togeostyler
from . import fromgeostyler


def toGeostyler(style, options=None):
    geostyler, _, _ = togeostyler.convert(json.loads(style), options)
    return geostyler


def fromGeostyler(style, options=None):
    arcgisjson, warnings = fromgeostyler.convert(style, options)
    return arcgisjson
