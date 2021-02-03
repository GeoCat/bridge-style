import json
from . import togeostyler
from . import fromgeostyler


def toGeostyler(style):
    geostyler, _, _ = togeostyler.convert(json.loads(style))
    return geostyler


def fromGeostyler(style):
    arcgisjson, warnings = fromgeostyler.convert(style)
    return arcgisjson
