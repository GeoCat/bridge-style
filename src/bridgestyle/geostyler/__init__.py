import json


def toGeostyler(style, options=None):
    return json.loads(style), [], []


def fromGeostyler(style, options=None):
    return json.dumps(style), [], []
