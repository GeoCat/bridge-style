import os
import json

_usedIcons = {}
_warnings = []

def convert(arcgis):
    global _usedIcons
    _usedIcons = {}
    global _warnings
    _warnings = []
    geostyler = processLayer(arcgis["layerDefinitions"][0])
    return geostyler, _usedIcons, _warnings

def processLayer(layer):
    #layer is a dictionary with the ArcGIS Pro Json style 
    geostyler = {}   
    geostyler = {"name": layer["name"]}
    if layer["type"] == "CIMFeatureLayer":
        renderer = layer["renderer"]
        rules = []
        if renderer["type"] == "CIMSimpleRenderer":
            rules.append(processSimpleRenderer(renderer))
        elif renderer["type"] == "CIMUniqueimpleRenderer":
            for group in renderer["groups"]:
                rules.extend(processUniqueValueGroup(renderer["fields"], group))
        else:
            _warnings.append(
                "Unsupported renderer type: %s" % str(renderer))
            return            
        '''
        labelingRules = processLabelingLayer(layer)
        if labelingRules is not None:
            rules = rules + labelingRules
        '''
        geostyler["rules"] = rules
    elif layer["type"] == "CIMRasterLayer":
        rules = [{"name": layer["name"], "symbolizers": [
            rasterSymbolizer(layer)]}]
        geostyler["rules"] = rules

    return geostyler

def processSimpleRenderer(renderer):
    rule = {"name": "",
            "symbolizers": processSymbolReference(renderer["symbol"])}
    return rule

def processUniqueValueGroup(fields, group):
    def _and(a, b):
        return ["And", a, b]
    def _or(a, b):
        return ["Or", a, b]
    def _equal(name, val):
        return ["PropertyIsEqualTo",
                    [
                        "PropertyName",
                        name
                    ],
                    val
                ]
    for clazz in group["classes"]:
        rule = {"name": clazz["label"]}
        values = clazz["values"]
        conditions = []
        for v in values:
            fieldValues = v["fieldValues"]
            condition = _equal(fields[0], fieldValues[0])
            for fieldValue, fieldName in zip(fieldValues[1:], fields[1:]):
                condition = _and(condition, _equal(fieldName, fieldValue))
            conditions.append(condition)

        ruleFilter = conditions[0]
        for condition in conditions[1:]:
            ruleFilter = _or(ruleFilter, condition)

        rule["filter"] = ruleFilter
        rule["symbolizers"] = processSymbolReference(clazz["symbol"])
        rules.append(rule)
    return rules


def processSymbolReference(symbolref):
    symbol = symbolref["symbol"]
    symbolizers = []
    if "symbolLayers" in symbol:
        for layer in symbol["symbolLayers"]:
            symbolizers.append(processSymbolLayer(layer))
    return symbolizers

def processSymbolLayer(layer):
    if layer["type"] == "CIMSolidStroke":
        return {
            "kind": "Line",
            "color": processColor(layer["color"]),
            "opacity": 1.0,
            "width": layer["width"],
            "perpendicularOffset": 0.0,
            "cap": layer["capStyle"].lower(),
            "join": layer["joinStyle"].lower(),            
        }
    elif layer["type"] == "CIMSolidFill":
        return {
            "kind": "Fill",
            "opacity": 1.0,
            "color": processColor(layer["color"]),
            "fillOpacity": 1.0            
        }
    elif layer["type"] == "CIMCharacterMarker":
        fontFamily = layer["fontFamilyName"]
        hexcode = hex(layer["characterIndex"])
        name = "ttf://%s#%s" % (fontFamily, hexcode)
        try:
            color = processColor(layer["symbol"]["symbolLayers"][0]["color"])
        except KeyError:
            color = "#000000"
        return {
            "opacity": 1.0,
            "rotate": 0.0,
            "kind": "Mark",
            "color": color,
            "wellKnownName": "ttf://Dingbats#0x61",
            "size": layer["size"],
            "Z": 0
            }

    elif layer["type"] == "CIMVectorMarker":
        return{
            "opacity": 1.0,
            "rotate": 0.0,
            "kind": "Mark",
            "color": "#ff0000",
            "wellKnownName": "circle",
            "size": 10,
            "strokeColor": "#000000",
            "strokeWidth": 1,
            "strokeOpacity": 1.0,
            "fillOpacity": 1.0,
            "Z": 0
        }
    else:
        return {}

def processColor(color):
    if color["type"] == "CIMRGBColor":
        values = color["values"]
        return '#%02x%02x%02x' % (values[0], values[1], values[2])
    else:
        return "#000000"