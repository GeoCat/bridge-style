import os
import math
import json

import tempfile

_warnings = []
_source_name = "vector-source"

_processTextSymbolizer = False


def convert(geostyler):
    global _warnings
    _warnings = []
    layers = processLayer(geostyler)
    layers.sort(key=lambda l: l["Z"])
    obj = {
        "version": 8,
        "glyphs": "mapbox://fonts/mapbox/{fontstack}/{range}.pbf",

        "name": geostyler["name"],
        "sources": {
            _source_name: {
                "type": "vector",
                "tiles": [
                    tileURL(geostyler)
                ],
                "minZoom": 0,
                "maxZoom": 20 # todo: might be able to determine these from style
            },
        },
        "layers": layers,
        "sprite": "spriteSheet",
    }

    return json.dumps(obj, indent=4), _warnings

# requires configuration with the tiles server URL
# This is only available during publishing
# TODO: inject this
#  "http://localhost:8080/geoserver/gwc/service/wmts?REQUEST=GetTile&SERVICE=WMTS&VERSION=1.0.0&LAYER=Quickstart2:quickstart&STYLE=&TILEMATRIX=EPSG:900913:{z}&TILEMATRIXSET=EPSG:900913&FORMAT=application/x-protobuf;type=mapbox-vector&TILECOL={x}&TILEROW={y}"

def tileURL(geostyler):
    return "URL to tiles - " + geostyler["name"]

def tileURLFull(baseurl, workspace, layer):
    return "{0}/gwc/service/wmts?REQUEST=GetTile&SERVICE=WMTS&VERSION=1.0.0&LAYER={1}:{2}" \
            "&STYLE=&TILEMATRIX=EPSG:900913:{{z}}" \
            "&TILEMATRIXSET=EPSG:900913&FORMAT=application/x-protobuf;type=mapbox-vector&TILECOL={{x}}&TILEROW={{y}}" \
            .format(baseurl, workspace, layer)

def spriteURLFull(baseurl, workspace, layer):
    return "{0}/styles/{1}/spriteSheet" \
         .format(baseurl, workspace, layer)

def _toZoomLevel(scale):
    if scale < 1:  # scale=0 is valid in QGIS
        return 24  # 24 is largest value (according to mapbox spec)
    #val = int(math.log(1000000000 / scale, 2))
    # https://docs.mapbox.com/help/glossary/zoom-level/
    # https://wiki.openstreetmap.org/wiki/Zoom_levels
    # and experimentation
    val = (math.log(279581257 / scale, 2))

    return min(max(val, 0), 24)  # keep between 0 and 24


def processLayer(layer):
    allLayers = []

    ruleNumber = 0
    for rule in layer.get("rules", []):
        layers = processRule(rule, layer["name"], ruleNumber)
        ruleNumber += 1
        allLayers += layers

    return allLayers


def processRule(rule, source, ruleNumber):
    filt = convertExpression(rule.get("filter", None))
    minzoom = None
    maxzoom = None
    if "scaleDenominator" in rule:
        scale = rule["scaleDenominator"]
        if "max" in scale:
            minzoom = max(_toZoomLevel(scale["max"]), 0)  # mapbox gl has maxzoom as the larger zoom number
        if "min" in scale:
            maxzoom = _toZoomLevel(scale["min"])  # mapbox gl has minzoom as the smaller zoom number
    name = rule.get("name", "rule")
    layers = [processSymbolizer(s) for s in rule["symbolizers"]]
    layers = [item for sublist in layers for item in sublist]   # flattens list
    layers = [x for x in layers if x is not None]  # remove None symbolizers
    for i, lay in enumerate(layers):
        try:
            if filt is not None:
                lay["filter"] = filt
            lay["source"] = _source_name
            lay["source-layer"] = source
            lay["id"] = source + ":"  + "(rule#"+str(ruleNumber)+")" + name + ":" + str(i)  # this needs to be globally unique
            if minzoom is not None:
                lay["minzoom"] = minzoom
            if maxzoom is not None:
                lay["maxzoom"] = maxzoom
        except Exception as e:
            _warnings.append("Empty style rule: '%s'" % (name + ":" + str(i)))
    return layers


func = {"PropertyName": "get",
        "Or": "any",
        "And": "all",
        "PropertyIsEqualTo": "==",
        "PropertyIsNotEqualTo": "!=",
        "PropertyIsLessThanOrEqualTo": "<=",
        "PropertyIsGreaterThanOrEqualTo": ">=",
        "PropertyIsLessThan": "<",
        "PropertyIsGreaterThan": ">",
        "Add": "+",
        "Sub": "-",
        "Mul": "*",
        "Div": "/",
        "Not": "!",
        "toRadians": None,
        "toDegrees": None,
        "floor": "floor",
        "ceil": "ceil",
        "if_then_else": "case",
        "Concatenate": "concat",
        "strSubstr": None,
        "strToLower": "downcase",
        "strToUpper": "upcase",
        "strReplace": None,
        "acos": "acos",
        "asin": "asin",
        "atan": "atan",
        "atan2": "atan2",
        "sin": "sin",
        "cos": "cos",
        "tan": "tan",
        "log": "ln",
        "strCapitalize": None,
        "min": "min",
        "max": "max"}  # TODO


def convertExpression(exp):
    if exp is None:
        return None
    if isinstance(exp, list):
        funcName = func.get(exp[0], None)
        if funcName is None:
            _warnings.append("Unsupported expression function for mapbox conversion: '%s'" % exp[0])
            return None
        else:
            convertedExp = [funcName]
            for arg in exp[1:]:
                convertedExp.append(convertExpression(arg))
            return convertedExp
    else:
        return exp


def processSymbolizer(sl):
    symbolizerType = sl["kind"]
    if symbolizerType == "Icon":
        symbolizer = [_iconSymbolizer(sl)]
    if symbolizerType == "Line":
        symbolizer = [_lineSymbolizer(sl)]
    if symbolizerType == "Fill":
        symbolizer = _fillSymbolizer(sl)
    if symbolizerType == "Mark":
        symbolizer =[ _markSymbolizer(sl)]
    if symbolizerType == "Text":
        symbolizer = [_textSymbolizer(sl)]
    if symbolizerType == "Raster":
        symbolizer = [_rasterSymbolizer(sl)]

    geom = _geometryFromSymbolizer(sl)
    if geom is not None:
        _warnings.append("Derived geometries are not supported in mapbox gl")

    for s in symbolizer:
        if s:  # might be None
            s["Z"] = sl["Z"]

    return symbolizer


def _symbolProperty(sl, name, default=None):
    if name in sl:
        return convertExpression(sl[name])
    else:
        return default


def _textSymbolizer(sl):
    if not _processTextSymbolizer:
        return None
    layout = {}
    paint = {}
    color = _symbolProperty(sl, "color")
    fontFamily = _symbolProperty(sl, "font")
    label = _symbolProperty(sl, "label")
    size = _symbolProperty(sl, "size")
    if "offset" in sl:
        offset = sl["offset"]
        offsetx = convertExpression(offset[0])
        offsety = convertExpression(offset[1])
        layout["text-offset"] = [offsetx, offsety]
    elif "perpendicularOffset" in sl:
        offset = sl["perpendicularOffset"]
        layout["text-offset"] = offset

    if "haloColor" in sl and "haloSize" in sl:
        paint["text-halo-width"] = _symbolProperty(sl, "haloSize")
        paint["text-halo-color"] = _symbolProperty(sl, "haloColor")

    layout["text-field"] = label
    layout["text-size"] = float(size)
    layout["text-font"] = [fontFamily]

    paint["text-color"] = color

    '''
    rotation = -1 * float(qgisLayer.customProperty("labeling/angleOffset"))
    layout["text-rotate"] = rotation

    ["text-opacity"] = (255 - int(qgisLayer.layerTransparency())) / 255.0

    if str(qgisLayer.customProperty("labeling/scaleVisibility")).lower() == "true":
        layer["minzoom"]  = _toZoomLevel(float(qgisLayer.customProperty("labeling/scaleMin")))
        layer["maxzoom"]  = _toZoomLevel(float(qgisLayer.customProperty("labeling/scaleMax")))
    '''

    return {"type": "symbol", "paint": paint, "layout": layout}


def _lineSymbolizer(sl, graphicStrokeLayer=0):
    opacity = _symbolProperty(sl, "opacity")
    color = sl.get("color", None)
    graphicStroke = sl.get("graphicStroke", None)
    width = _symbolProperty(sl, "width")
    dasharray = _symbolProperty(sl, "dasharray")
    cap = _symbolProperty(sl, "cap")
    join = _symbolProperty(sl, "join")
    offset = _symbolProperty(sl, "offset")

    paint = {}
    if graphicStroke is not None:
        _warnings.append("Marker lines not supported for Mapbox GL conversion")
        # TODO

    if color is None:
        paint["visibility"] = "none"
    else:
        paint["line-width"] = width
        paint["line-opacity"] = opacity
        paint["line-color"] = color
    if dasharray is not None:
        paint["line-dasharray"] = _parseSpaceArray(dasharray)
    if offset is not None:
        paint["line-offset"] = offset

    return {"type": "line", "paint": paint}

def number(str):
    try:
        return int(str)
    except ValueError:
        return float(str)

#"1 2" -> [1,2]
def _parseSpaceArray(str):
    return [number(x) for x in str.split(" ")]

def _geometryFromSymbolizer(sl):
    geomExpr = convertExpression(sl.get("Geometry", None))
    return geomExpr


def _iconSymbolizer(sl):
    path = os.path.splitext(os.path.basename(sl["image"])[0])
    rotation = _symbolProperty(sl, "rotate")

    paint = {}
    paint["icon-image"] = path
    paint["icon-rotate"] = rotation
    size = _symbolProperty(sl, "size", 16) / 64.0
    paint["icon-size"] = size
    return {"type": "symbol", "paint": paint}


def _markSymbolizer(sl):
    paint = {}
    paint["icon-image"] = _symbolProperty(sl, "spriteName")

    rotation = _symbolProperty(sl, "rotate")
    paint["icon-rotate"] = rotation

    size = _symbolProperty(sl, "size", 16) / 64.0
    paint["icon-size"] = size
    return {"type": "symbol", "layout": paint}
    # if shape.startswith("file://"):
    #     svgFilename = shape.split("//")[-1]
    #     name = os.path.splitext(svgFilename)[0]
    #     paint = {}
    #     paint["icon-image"] = name
    #     rotation = _symbolProperty(sl, "rotate")
    #     paint["icon-rotate"] = rotation
    #
    #     size = _symbolProperty(sl, "size", 16)/64.0
    #     paint["icon-size"] = size
    #
    #     #paint["icon-rotate"] = rotation
    #     return {"type": "symbol", "layout": paint}
    # else:
    #     size = _symbolProperty(sl, "size")
    #     opacity = _symbolProperty(sl, "opacity")
    #     color = _symbolProperty(sl, "color")
    #     outlineColor = _symbolProperty(sl, "strokeColor")
    #     outlineWidth = _symbolProperty(sl, "strokeWidth")
    #
    #     paint = {}
    #     paint["circle-radius"] = ["/", size, 2]
    #     paint["circle-color"] = color
    #     paint["circle-opacity"] = opacity
    #     paint["circle-stroke-width"] = outlineWidth
    #     paint["circle-stroke-color"] = outlineColor
    #
    #     return {"type": "circle", "layout": paint}


def _fillSymbolizer(sl):
    paint = {}
    opacity = _symbolProperty(sl, "opacity")
    color = sl.get("color", None)
    graphicFill = sl.get("graphicFill", None)
    if graphicFill is not None:
        _warnings.append("Marker fills not supported for Mapbox GL conversion")
        # TODO
        # fill = {"type": "fill", "paint": {
        #     "fill-color":   _symbolProperty(graphicFill[0], "color"),
        #     "fill-opacity": opacity
        # }}
        fill = None # don't fill -- this causes issues either way...
    else:
        paint["fill-opacity"] = opacity * _symbolProperty(sl, "fillOpacity",1)
        if color is not None:
            paint["fill-color"] = color
        fill = {"type": "fill", "paint": paint}
    line = None
    outlineColor = _symbolProperty(sl, "outlineColor")
    if outlineColor is not None:
        line = {"type": "line",
                "paint": {
                    "line-width": _symbolProperty(sl, "outlineWidth") or 1,
                    "line-opacity": (_symbolProperty(sl, "outlineOpacity") or 1) * opacity,
                    "line-color": outlineColor
                }}
    if line:
        return [fill, line]
    return [fill]


def _rasterSymbolizer(sl):
    return {"type": "raster"}  # TODO
