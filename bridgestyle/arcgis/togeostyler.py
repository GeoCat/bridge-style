import math
import os
import base64
import uuid
import tempfile

ESRI_SYMBOLS_FONT = "ESRI Default Marker"

_usedIcons = []
_warnings = []


def convert(arcgis, options=None):
    global _usedIcons
    _usedIcons = []
    global _warnings
    _warnings = []
    geostyler = processLayer(arcgis["layerDefinitions"][0], options)
    return geostyler, _usedIcons, _warnings


def processLayer(layer, options=None):
    #layer is a dictionary with the ArcGIS Pro Json style
    options = options or {}
    geostyler = {}
    geostyler = {"name": layer["name"]}
    if layer["type"] == "CIMFeatureLayer":
        renderer = layer["renderer"]
        rules = []
        if renderer["type"] == "CIMSimpleRenderer":
            rules.append(processSimpleRenderer(renderer, options))
        elif renderer["type"] == "CIMUniqueValueRenderer":
            for group in renderer["groups"]:
                rules.extend(processUniqueValueGroup(renderer["fields"],
                            group, options))
        else:
            _warnings.append(
                "Unsupported renderer type: %s" % str(renderer))
            return

        if layer.get("labelVisibility", False):
            for labelClass in layer.get("labelClasses", []):
                rules.append(processLabelClass(labelClass, options.get("tolowercase", False)))

        geostyler["rules"] = rules
    elif layer["type"] == "CIMRasterLayer":
        rules = [{"name": layer["name"], "symbolizers": [
            rasterSymbolizer(layer)]}]
        geostyler["rules"] = rules

    return geostyler


def processLabelClass(labelClass, tolowercase=False):
    textSymbol = labelClass["textSymbol"]["symbol"]
    expression = labelClass["expression"].replace("[", "").replace("]", "")
    fontFamily = textSymbol.get('fontFamilyName', 'Arial')
    fontSize = textSymbol.get('height', 12)
    color = _extractFillColor(textSymbol["symbol"]['symbolLayers'])
    fontWeight = textSymbol.get('fontStyleName', 'Regular')
    #minimumScale = labelParse['minimumScale'] or ''

    symbolizer = {
            "kind": "Text",
            "offset": [
                0.0,
                0.0
            ],
            "anchor": "right",
            "rotate": 0.0,
            "color": color,
            "font": fontFamily,
            "label": [
                "PropertyName",
                expression.lower() if tolowercase else expression
            ],
            "size": fontSize
        }

    haloSize = textSymbol.get("haloSize")
    if haloSize:
        haloColor = _extractFillColor(textSymbol["haloSymbol"]['symbolLayers'])
        symbolizer.update({"haloColor": haloColor,
                           "haloSize": haloSize,
                           "haloOpacity": 1})
    rule = {"name": "",
            "symbolizers": [symbolizer]}

    return rule


def processSimpleRenderer(renderer, options):
    rule = {"name": "",
            "symbolizers": processSymbolReference(renderer["symbol"], options)}
    return rule


def processUniqueValueGroup(fields, group, options):
    tolowercase = options.get("tolowercase", False)
    def _and(a, b):
        return ["And", a, b]
    def _or(a, b):
        return ["Or", a, b]
    def _equal(name, val):
        return ["PropertyIsEqualTo",
                    [
                        "PropertyName",
                        name.lower() if tolowercase else name
                    ],
                    val
                ]
    rules = []
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
        rule["symbolizers"] = processSymbolReference(clazz["symbol"], options)
        rules.append(rule)
    return rules


def processSymbolReference(symbolref, options):
    symbol = symbolref["symbol"]
    symbolizers = []
    if "symbolLayers" in symbol:
        for layer in symbol["symbolLayers"]:
            symbolizer = processSymbolLayer(layer, options)
            if layer["type"] in ["CIMVectorMarker", "CIMPictureFill", "CIMCharacterMarker"]:
                if symbol["type"] == "CIMLineSymbol":
                    symbolizer = {"kind": "Line",
                        "opacity": 1.0,
                        "perpendicularOffset": 0.0,
                        "graphicStroke": [symbolizer],
                        "graphicStrokeInterval": symbolizer["size"] * 2, #TODO
                        "graphicStrokeOffset": 0.0,
                        "Z": 0}
                elif symbol["type"] == "CIMPolygonSymbol":
                    symbolizer = {"kind": "Fill",
                        "opacity": 1.0,
                        "perpendicularOffset": 0.0,
                        "graphicFill": [symbolizer],
                        "graphicFillMarginX": symbolizer["size"] * 2, #TODO
                        "graphicFillMarginY": symbolizer["size"] * 2,
                        "Z": 0}
            symbolizers.append(symbolizer)
    return symbolizers

def processEffect(effect):
    if effect["type"] == "CIMGeometricEffectDashes":
        return {"dasharray": " ". join(str(v) for v in effect["dashTemplate"])}
    else:
        return {}

def _hatchMarkerForAngle(angle):
    quadrant = math.floor(((angle + 22.5) % 180) / 45.0)
    return [
        "shape://horline",
        "shape://backslash",
        "shape://vertline",
        "shape://slash"
    ][quadrant]


def _esriFontToStandardSymbols(charindex):
    mapping = {42: "triangle",
               35: "triangle",
               33: "square",
               94: "star",
               95: "star",
               203: "cross",
               204: "cross"}
    if charindex in mapping:
        return mapping[charindex]
    else:
        _warnings.append(
                f"Unsupported symbol from ESRI font (character index {charindex}) replaced by default marker")
        return "circle"

def processSymbolLayer(layer, options):
    replaceesri = options.get("replaceesri", False)
    if layer["type"] == "CIMSolidStroke":
        stroke = {
            "kind": "Line",
            "color": processColor(layer["color"]),
            "opacity": 1.0,
            "width": layer["width"],
            "perpendicularOffset": 0.0,
            "cap": layer["capStyle"].lower(),
            "join": layer["joinStyle"].lower(),
        }
        if "effects" in layer:
            for effect in layer["effects"]:
                stroke.update(processEffect(effect))
        return stroke
    elif layer["type"] == "CIMSolidFill":
        return {
            "kind": "Fill",
            "opacity": 1.0,
            "color": processColor(layer["color"]),
            "fillOpacity": 1.0
        }
    elif layer["type"] == "CIMCharacterMarker":
        fontFamily = layer["fontFamilyName"]
        charindex = layer["characterIndex"]
        hexcode = hex(charindex)
        if fontFamily == ESRI_SYMBOLS_FONT and replaceesri:
            name = _esriFontToStandardSymbols(charindex)
        else:
            name = "ttf://%s#%s" % (fontFamily, hexcode)
        rotate = layer.get("rotation", 0)
        try:
            color = processColor(layer["symbol"]["symbolLayers"][0]["color"])
        except KeyError:
            color = "#000000"
        return {
            "opacity": 1.0,
            "rotate": rotate,
            "kind": "Mark",
            "color": color,
            "wellKnownName": name,
            "size": layer["size"],
            "Z": 0
            }

    elif layer["type"] == "CIMVectorMarker":
        #TODO
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
    elif layer["type"] == "CIMHatchFill":
        rotation = layer.get("rotation", 0)
        separation =  layer.get("separation", 2) #This parameter can't really be translated to geostyler
        symbolLayers = layer["lineSymbol"]["symbolLayers"]
        color, width = _extractStroke(symbolLayers)

        return {
            "kind": "Fill",
            "opacity": 1.0,
            "graphicFill": [
                {
                    "kind": "Mark",
                    "color": color,
                    "wellKnownName": _hatchMarkerForAngle(rotation),
                    "size": 3,
                    "strokeColor": color,
                    "strokeWidth": width,
                    "rotate": 0
                }
            ],
            "Z": 0
        }
    elif layer["type"] == "CIMPictureFill":
        url = layer["url"]
        if not os.path.exists(url):
            tokens = url.split(";")
            if len(tokens) == 2:
                ext = tokens[0].split("/")[-1]
                data = tokens[1][len("base64,"):]
                path = os.path.join(tempfile.gettempdir(), "bridgestyle",
                                    str(uuid.uuid4()).replace("-", ""))
                iconName = f"{len(_usedIcons)}.{ext}"
                iconFile = os.path.join(path, iconName)
                os.makedirs(path, exist_ok=True)
                with open(iconFile, "wb") as f:
                    f.write(base64.decodebytes(data.encode()))
                    _usedIcons.append(iconFile)
                url = iconFile

        rotate = layer.get("rotation", 0)
        height = layer["height"]
        return {
                "opacity": 1.0,
                "rotate": 0.0,
                "kind": "Icon",
                "color": None,
                "image": url,
                "size": height,
                "Z": 0
                }
    else:
        return {}


def _extractStroke(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidStroke":
            color = processColor(sl["color"])
            width = sl["width"]
            return color, width
    return "#000000", 1


def _extractFillColor(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidFill":
            color = processColor(sl["color"])
            return color
    return "#000000"


def processColor(color):
    values = color["values"]
    if color["type"] == "CIMRGBColor":
        return '#%02x%02x%02x' % (values[0], values[1], values[2])
    elif color["type"] == 'CIMCMYKColor':
        r, g, b = cmyk2Rgb(values)
        return '#%02x%02x%02x' % (r, g, b)
    elif color["type"] == 'CIMHSVColor':
        r, g, b = hsv2rgb(values)
        return '#%02x%02x%02x' % (int(r), int(g), int(b))
    else:
        return "#000000"


def cmyk2Rgb(cmyk_array):
    c = cmyk_array[0]
    m = cmyk_array[1]
    y = cmyk_array[2]
    k = cmyk_array[3]

    r = int((1 - ((c + k)/100)) * 255)
    g = int((1 - ((m + k)/100)) * 255)
    b = int((1 - ((y + k)/100)) * 255)

    return r, g, b


def hsv2rgb(hsv_array):
    h = hsv_array[0] / 360
    s = hsv_array[1] / 100
    v = hsv_array[2] / 100
    if s == 0.0:
        v *= 255
        return (v, v, v)
    i = int(h * 6.)
    f = (h * 6.) - i
    p = 255 * (v * (1. - s))
    q = 255 * (v * (1. - s * f))
    t = 255 * (v*(1. - s * (1. - f)))
    v *= 255
    i %= 6
    if i == 0:
        return (v, t, p)
    if i == 1:
        return (q, v, p)
    if i == 2:
        return (p, v, t)
    if i == 3:
        return (p, q, v)
    if i == 4:
        return (t, p, v)
    if i == 5:
        return (v, p, q)
