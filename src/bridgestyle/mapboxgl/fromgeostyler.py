import json
import math
import os
import tempfile

from ..qgis import togeostyler as qgis2geostyler
from ..qgis.expressions import (
    OGC_PROPERTYNAME,
    OGC_IS_EQUAL_TO,
    OGC_IS_NULL,
    OGC_IS_NOT_NULL,
    OGC_SUB
)

# Globals
_warnings = []

# Constants
SOURCE_NAME = "vector-source"


def convertGroup(group, qgis_layers, baseUrl, workspace, name):
    obj = {
        "version": 8,
        "glyphs": "mapbox://fonts/mapbox/{fontstack}/{range}.pbf",
        "name": name,
        "sources": {
            SOURCE_NAME: {
                "type": "vector",
                "tiles": [
                    tileURLFull(baseUrl, workspace, name)
                ],
                "minZoom": 0,
                "maxZoom": 20  # todo: might be able to determine these from style
            },
        },
        "sprite": spriteURLFull(baseUrl, workspace, name),
        "layers": []
    }

    geostylers = {}
    mapboxstyles = {}
    mblayers = []
    allSprites = {}
    allWarnings = []

    # build geostyler and mapbox styles
    for layername in group["layers"]:
        layer = qgis_layers[layername]
        geostyler, icons, sprites, warnings = qgis2geostyler.convert(layer)
        allWarnings.extend(warnings)
        allSprites.update(sprites)  # combine/accumulate sprites
        geostylers[layername] = geostyler
        mbox, mbWarnings = convert(geostyler, None)
        allWarnings.extend(mbWarnings)
        mbox_obj = json.loads(mbox)
        mapboxstyles[layername] = mbox_obj
        mblayers.extend(mbox_obj.get("layers", []))

    obj["layers"] = mblayers

    return json.dumps(obj, indent=4), allWarnings, obj, toSpriteSheet(allSprites)


# allSprites ::== sprite name -> {"image":Image, "image2x":Image}
def toSpriteSheet(allSprites):
    if not allSprites:
        return None

    height = qgis2geostyler.SPRITE_SIZE
    width = qgis2geostyler.SPRITE_SIZE * len(allSprites)
    img, img2x, painter, painter2x, spritesheet, spritesheet2x = qgis2geostyler.initSpriteSheet(width, height)
    x = 0
    for name, _sprites in allSprites.items():
        name_without_ext = os.path.splitext(name)[0]
        s = _sprites["image"]
        s2x = _sprites["image2x"]
        qgis2geostyler.drawSpriteSheet(name_without_ext, painter, painter2x, spritesheet, spritesheet2x, x, s, s2x)
        x += s.width()
    painter.end()
    painter2x.end()
    folder = tempfile.gettempdir()
    qgis2geostyler.writeSpritesOutput(folder, img, img2x, spritesheet, spritesheet2x)
    return {"img": img, "img2x": img2x, "json": json.dumps(spritesheet), "json2x": json.dumps(spritesheet2x)}


def convert(geostyler, options=None):
    global _warnings
    _warnings = []
    layers = processLayer(geostyler)
    layers.sort(key=lambda l: l["Z"])
    [l.pop('Z', None) for l in layers]
    layers.sort(key=lambda l: l["type"]=="symbol")
    obj = {
        "version": 8,
        "glyphs": "mapbox://fonts/mapbox/{fontstack}/{range}.pbf",

        "name": geostyler["name"],
        "sources": {
            SOURCE_NAME: {
                "type": "vector",
                "tiles": [
                    tileURL(geostyler)
                ],
                "minZoom": 0,
                "maxZoom": 20  # todo: might be able to determine these from style
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
    # val = int(math.log(1000000000 / scale, 2))
    # https://docs.mapbox.com/help/glossary/zoom-level/
    # https://wiki.openstreetmap.org/wiki/Zoom_levels
    # and experimentation
    val = (math.log(279581257 / scale, 2))

    return min(max(val, 0), 24)  # keep between 0 and 24


def processLayer(layer):
    allLayers = []

    ruleNumber = 0
    rules = layer.get("rules", [])
    for rule in rules:
        layers = processRule(rule, layer["name"], ruleNumber, rules)
        ruleNumber += 1
        allLayers += layers

    return allLayers


def processRule(rule, source, ruleNumber, rules):
    filt = convertExpression(rule.get("filter", None))
    if filt == "ELSE":  # None of the other filters apply
        filt = _processElseFilter(rule, ruleNumber, rules)

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
    layers = [item for sublist in layers for item in sublist]  # flattens list
    layers = [x for x in layers if x is not None]  # remove None symbolizers
    for i, lay in enumerate(layers):
        try:
            if filt is not None:
                lay["filter"] = filt  # noqa
            lay["source"] = SOURCE_NAME
            lay["source-layer"] = source
            lay["id"] = source + ":" + "(rule#" + str(ruleNumber) + ")" + name + ":" + str(
                i)  # this needs to be globally unique
            if minzoom is not None:
                lay["minzoom"] = minzoom  # noqa
            if maxzoom is not None:
                lay["maxzoom"] = maxzoom  # noqa
        except Exception:
            _warnings.append("Empty style rule: '%s'" % (name + ":" + str(i)))
    return layers

def _processElseFilter(elseRule, ruleNumber, rules):
    # Wrap the other rules in a NOT ( ANY (rule1, rule2...)) to construct an explicit ELSE filter
    otherFilters = ["any"]
    for idx, rule in enumerate(rules):
        if idx == ruleNumber:  # This is the ElseFilter
            continue
        filt = convertExpression(rule.get("filter", None))
        if filt:
            otherFilters.append(filt)

    elseFilter = ["!", otherFilters]
    return elseFilter

func = {
    OGC_PROPERTYNAME: "get",
    "Or": "any",
    "And": "all",
    OGC_IS_EQUAL_TO: "==",
    "PropertyIsNotEqualTo": "!=",
    "PropertyIsLessThanOrEqualTo": "<=",
    "PropertyIsGreaterThanOrEqualTo": ">=",
    "PropertyIsLessThan": "<",
    "PropertyIsGreaterThan": ">",
    OGC_IS_NULL: "!",
    OGC_IS_NOT_NULL: "has",
    "Add": "+",
    OGC_SUB: "-",
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
    "max": "max",
    "parseLong": "to-number",
    "parseDouble": "to-number",
    "to_string": "to-string",
}


def convertExpression(exp):
    if exp is None:
        return None
    if isinstance(exp, list):
        funcName = func.get(exp[0], None)
        if funcName is None:
            _warnings.append("Unsupported expression function for mapbox conversion: '%s'" % exp[0])
            return None
        else:
            if funcName == "!" and isinstance(exp[1], list):
                # Special case to add "is null" support
                convertedExp = [func.get("Not", None)]
                convertedExp.append(["has", convertExpression(exp[1][-1])])
            elif funcName == "has" and isinstance(exp[1], list):
                # Special case to add "is not null" support
                convertedExp = [funcName]
                convertedExp.append(convertExpression(exp[1][-1]))
            else:
                convertedExp = [funcName]
                for arg in exp[1:]:
                    convertedExp.append(convertExpression(arg))
            return convertedExp
    else:
        return exp


def processSymbolizer(sl):
    sl_type = sl.get('kind')
    processor = {
        "Icon": _iconSymbolizer,
        "Line": _lineSymbolizer,
        "Fill": _fillSymbolizer,
        "Mark": _markSymbolizer,
        "Text": _textSymbolizer,
        "Raster": _rasterSymbolizer
    }.get(sl_type)
    if not processor:
        _warnings.append(f"Unknown or unsupported symbol type '{sl_type}'")

    geom = _geometryFromSymbolizer(sl)
    if geom is not None:
        _warnings.append("Derived geometries are not supported in mapbox gl")

    result = processor(sl)
    symbolizers = []
    if result:
        if isinstance(result, list):
            symbolizers.extend(r for r in result if r)
        else:
            symbolizers.append(result)
    for s in symbolizers:
        s["Z"] = sl.get("Z", 0)

    return symbolizers


def _symbolProperty(sl, name, default=None):
    if name in sl:
        return convertExpression(sl[name])
    else:
        return default


def _textSymbolizer(sl):
    layout = {}
    paint = {}
    color = _symbolProperty(sl, "color")
    fontFamily = _symbolProperty(sl, "font")
    label = _symbolProperty(sl, "label")
    size = _symbolProperty(sl, "size")
    if "perpendicularOffset" in sl:
        offset = sl["perpendicularOffset"]
        layout["text-offset"] = offset
    elif "offset" in sl:
        offset = sl["offset"]
        offsetx = convertExpression(offset[0])
        offsety = convertExpression(offset[1])
        layout["text-offset"] = [offsetx, offsety]

    if "haloColor" in sl and "haloSize" in sl:
        paint["text-halo-width"] = float(_symbolProperty(sl, "haloSize"))
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
    layout = {}
    if graphicStroke is not None:
        _warnings.append("Marker lines not supported for Mapbox GL conversion")
        # TODO

    if color is None:
        paint["visibility"] = "none"
    else:
        paint["line-width"] = width
        paint["line-opacity"] = opacity
        paint["line-color"] = color
        layout["line-cap"] = cap
        layout["line-join"] = join
    if isinstance(dasharray, str):
        paint["line-dasharray"] = _parseSpaceArray(dasharray)
    if offset is not None:
        paint["line-offset"] = offset

    return {"type": "line", "paint": paint, "layout": layout}


def number(string):
    try:
        return int(string)
    except ValueError:
        return float(string)


# "1 2" -> [1,2]
def _parseSpaceArray(string):
    return [number(x) for x in string.split(" ")]


def _geometryFromSymbolizer(sl):
    geomExpr = convertExpression(sl.get("Geometry", None))
    return geomExpr


def _iconSymbolizer(sl):
    image = sl.get('image')
    if not image:
        _warnings.append("Icon symbol has no image")
        return {"type": "symbol"}
    path = os.path.splitext(os.path.basename(image)[0])
    rotation = _symbolProperty(sl, "rotate")

    paint = {}
    paint["icon-image"] = path
    paint["icon-rotate"] = rotation
    size = _symbolProperty(sl, "size", 16) / 64.0
    paint["icon-size"] = size
    return {"type": "symbol", "paint": paint}


def _markSymbolizer(sl):
    shape = sl.get('wellKnownName')
    if shape != None and shape != "circle":
        name = os.path.splitext(shape)[0]
        rotation = _symbolProperty(sl, "rotate")
        size = _symbolProperty(sl, "size", 16) / 64.0

        paint = {}
        paint["icon-image"] = name
        paint["icon-rotate"] = rotation
        paint["icon-size"] = size

        return {"type": "symbol", "layout": paint}
    else:
        size = _symbolProperty(sl, "size")
        opacity = _symbolProperty(sl, "opacity")
        color = _symbolProperty(sl, "color")
        outlineColor = _symbolProperty(sl, "strokeColor")
        outlineWidth = _symbolProperty(sl, "strokeWidth")
        dasharray    = _symbolProperty(sl, "dasharray")
    
        paint = {}
        paint["circle-radius"] = ["/", size, 2]
        paint["circle-color"] = color
        paint["circle-opacity"] = opacity
        paint["circle-stroke-width"] = outlineWidth
        paint["circle-stroke-color"] = outlineColor
    
        return {"type": "circle", "paint": paint}


def _fillSymbolizer(sl):
    paint = {}
    opacity = _symbolProperty(sl, "opacity")
    color = sl.get("color", None)
    dasharray = _symbolProperty(sl, "outlineDasharray")
    join = _symbolProperty(sl, "join")
    offset = _symbolProperty(sl, "offset")
    graphicFills = sl.get("graphicFill", None)
    if graphicFills is not None:
        fill = []
        for graphicFill in graphicFills:
            fill.append({
                    "type": "fill", 
                    "paint": {
                        "fill-opacity": graphicFill.get("fillOpacity", 1.0),
                        "fill-pattern": graphicFill["spriteName"],
                     }
            })
    else:
        paint["fill-opacity"] = opacity * _symbolProperty(sl, "fillOpacity", 1)
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
                },
                "layout":{
                    "line-join": join
                }}
        if isinstance(dasharray, str):
            line['paint']["line-dasharray"] = _parseSpaceArray(dasharray)
        if offset is not None:
            line['paint']["line-offset"] = offset
    if line:
        return [fill, line]
    return fill


def _rasterSymbolizer(sl):
    return {"type": "raster"}  # TODO
