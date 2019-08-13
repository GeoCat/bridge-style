from .mapboxgl import processLayer

def toGeostyler(style):
	return style #TODO

def fromGeostyler(style):
	mb, warnings = processLayer(style)
    return json.dumps(mb)