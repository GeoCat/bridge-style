from .sld import processLayer
from xml.dom import minidom
from xml.etree import ElementTree

def toGeostyler(style):
    return style #TODO

def fromGeostyler(style):
    xml, warnings = processLayer(style)
    sld = ElementTree.tostring(xml, encoding='utf8', method='xml').decode()
    dom = minidom.parseString(sld)
    return dom.toprettyxml(indent="  ")