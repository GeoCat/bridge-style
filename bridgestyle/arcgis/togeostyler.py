import base64
import math
import os
import tempfile
import uuid

from .expressions import convertExpression, convertWhereClause
from .wkt_geometries import to_wkt

ESRI_SYMBOLS_FONT = "ESRI Default Marker"
PT_TO_PX_FACTOR = 4/3

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
    # layer is a dictionary with the ArcGIS Pro Json style
    options = options or {}
    geostyler = {}
    geostyler = {"name": layer["name"]}
    if layer["type"] == "CIMFeatureLayer":
        renderer = layer["renderer"]
        rules = []
        if renderer["type"] == "CIMSimpleRenderer":
            rules.append(processSimpleRenderer(renderer, options))
        elif renderer["type"] == "CIMUniqueValueRenderer":
            if "groups" in renderer:
                for group in renderer["groups"]:
                    rules.extend(
                        processUniqueValueGroup(renderer["fields"], group, options)
                    )
            else:
                if "defaultSymbol" in renderer:
                    # this is really a simple renderer
                    rule = {
                        "name": "",
                        "symbolizers": processSymbolReference(
                            renderer["defaultSymbol"], options
                        ),
                    }
                    rules.append(rule)

        elif (
            renderer["type"] == "CIMClassBreaksRenderer"
            and renderer.get("classBreakType") in ["GraduatedColor", "GraduatedSymbol"]
        ):
            rules.extend(processClassBreaksRenderer(renderer, options))
        else:
            _warnings.append("Unsupported renderer type: %s" % str(renderer))
            return geostyler

        if layer.get("labelVisibility", False):
            for labelClass in layer.get("labelClasses", []):
                rules.append(
                    processLabelClass(labelClass, options.get("tolowercase", False))
                )

        geostyler["rules"] = rules
    elif layer["type"] == "CIMRasterLayer":
        rules = [{"name": layer["name"], "symbolizers": [rasterSymbolizer(layer)]}]
        geostyler["rules"] = rules

    return geostyler


def processClassBreaksRenderer(renderer, options):
    rules = []
    field = renderer["field"]
    lastbound = None
    tolowercase = options.get("tolowercase", False)
    rotation = _getGraduatedSymbolRotation(renderer, tolowercase) if renderer.get("classBreakType") == "GraduatedSymbol" else None
    for classbreak in renderer.get("breaks", []):
        symbolizers = processSymbolReference(classbreak["symbol"], options)
        upperbound = classbreak.get("upperBound", 0)
        if lastbound is not None:
            filt = [
                "And",
                [
                    "PropertyIsGreaterThan",
                    ["PropertyName", field.lower() if tolowercase else field],
                    lastbound,
                ],
                [
                    "PropertyIsLessThanOrEqualTo",
                    ["PropertyName", field.lower() if tolowercase else field],
                    upperbound,
                ],
            ]
        else:
            filt = [
                "PropertyIsLessThanOrEqualTo",
                ["PropertyName", field.lower() if tolowercase else field],
                upperbound,
            ]
        lastbound = upperbound
        if rotation:
            [symbolizer.update({"rotate": rotation}) for symbolizer in symbolizers]
        ruledef = {
            "name": classbreak.get("label", "classbreak"),
            "symbolizers": symbolizers,
            "filter": filt,
        }
        rules.append(ruledef)

    return rules


def processLabelClass(labelClass, tolowercase=False):
    textSymbol = labelClass["textSymbol"]["symbol"]
    expression = convertExpression(labelClass["expression"], labelClass["expressionEngine"], tolowercase)
    fontFamily = textSymbol.get("fontFamilyName", "Arial")
    fontSize = float(textSymbol.get("height", 12))
    color = _extractFillColor(textSymbol["symbol"]["symbolLayers"])
    fontWeight = textSymbol.get("fontStyleName", "Regular")
    rotationProps = labelClass.get("maplexLabelPlacementProperties", {}).get(
        "rotationProperties", {}
    )
    rotationField = rotationProps.get("rotationField")
    symbolizer = {
        "kind": "Text",
        "anchor": "right",
        "rotate": 0.0,
        "color": color,
        "font": fontFamily,
        "label": expression,
        "size": fontSize,
    }

    stdProperties = labelClass.get("standardLabelPlacementProperties", {})
    stdPlacementType = stdProperties.get("featureType")
    stdPointPlacementType = stdProperties.get("pointPlacementMethod")
    maplexProperties = labelClass.get("maplexLabelPlacementProperties", {})
    maplexPlacementType = maplexProperties.get("featureType")
    maplexPrimaryOffset = maplexProperties.get("primaryOffset", 0)
    maplexPointPlacementMethod = maplexProperties.get("pointPlacementMethod")
    if stdPlacementType == "Line" and maplexPlacementType == "Line":
        # We use this as a flag to later indicate the it is a line label when converting to SLD
        primaryOffset = float(textSymbol.get("primaryOffset", 0))
        symbolizer["perpendicularOffset"] = primaryOffset + fontSize
    elif maplexPlacementType == "Point" and maplexPointPlacementMethod == "AroundPoint":
        offset = maplexPrimaryOffset + fontSize / 2
        symbolizer["offset"] = [offset, offset]
        symbolizer["anchorPointX"] = symbolizer["anchorPointY"] = 0.0
    elif stdPlacementType == "Point" and stdPointPlacementType == "AroundPoint":
        offset = maplexPrimaryOffset + fontSize / 2
        symbolizer["offset"] = [offset, offset]
        symbolizer["anchorPointX"] = symbolizer["anchorPointY"] = 0.0
    else:
        symbolizer["offset"] = [0.0, 0.0]
    if rotationField is not None:
        symbolizer["rotate"] = [
            "Mul",
            ["PropertyName", rotationField.lower() if tolowercase else rotationField],
            -1,
        ]
    else:
        symbolizer["rotate"] = 0.0
    haloSize = textSymbol.get("haloSize")
    if haloSize and "haloSymbol" in textSymbol:
        haloColor = _extractFillColor(textSymbol["haloSymbol"]["symbolLayers"])
        symbolizer.update(
            {"haloColor": haloColor, "haloSize": haloSize, "haloOpacity": 1}
        )

    # Grouping labels if thinDuplicateLabels is true, or in case of polygons, if numLabelsOption is OneLabelPerName
    symbolizer["group"] = (
        (labelClass.get("maplexLabelPlacementProperties", {}).get("thinDuplicateLabels"))
        or (
            (maplexPlacementType == "Polygon")
            and (labelClass.get("standardLabelPlacementProperties", {}).get("numLabelsOption") == "OneLabelPerName")
        )
    )

    rule = {"name": "", "symbolizers": [symbolizer]}

    scaleDenominator = {}
    minimumScale = labelClass.get("minimumScale")
    if minimumScale is not None:
        scaleDenominator = {"max": minimumScale}
    maximumScale = labelClass.get("maximumScale")
    if maximumScale is not None:
        scaleDenominator = {"min": maximumScale}
    if scaleDenominator:
        rule["scaleDenominator"] = scaleDenominator

    if "whereClause" in labelClass:
        rule["filter"] = convertWhereClause(labelClass["whereClause"], tolowercase)

    return rule


def processSimpleRenderer(renderer, options):
    rule = {
        "name": renderer.get("label", ""),
        "symbolizers": processSymbolReference(renderer["symbol"], options),
    }
    return rule


def processUniqueValueGroup(fields, group, options):
    tolowercase = options.get("tolowercase", False)

    def _and(a, b):
        return ["And", a, b]

    def _or(a, b):
        return ["Or", a, b]

    def _equal(name, val):
        if val == "<Null>":
            return [
                "PropertyIsNull",
                ["PropertyName", name.lower() if tolowercase else name],
            ]
        return [
            "PropertyIsEqualTo",
            ["PropertyName", name.lower() if tolowercase else name],
            val,
        ]

    rules = []
    for clazz in group.get("classes", []):
        rule = {"name": clazz.get("label", "label")}
        values = clazz["values"]
        conditions = []
        for v in values:
            if "fieldValues" in v:
                fieldValues = v["fieldValues"]
                condition = _equal(fields[0], fieldValues[0])
                for fieldValue, fieldName in zip(fieldValues[1:], fields[1:]):
                    condition = _and(condition, _equal(fieldName, fieldValue))
                conditions.append(condition)
        if conditions:
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
    if "symbolLayers" not in symbol:
        return symbolizers
    for layer in symbol["symbolLayers"][::-1]:  # drawing order for geostyler is inverse of rule order
        if not layer["enable"]:
            continue
        symbolizer = processSymbolLayer(layer, symbol["type"], options)
        if symbolizer is None:
            continue
        if layer["type"] in [
            "CIMVectorMarker",
            "CIMPictureFill",
            "CIMCharacterMarker",
        ]:
            if symbol["type"] == "CIMLineSymbol":
                symbolizer = {
                    "kind": "Line",
                    "opacity": 1.0,
                    "perpendicularOffset": 0.0,
                    "graphicStroke": [symbolizer],
                    "graphicStrokeInterval": symbolizer["size"] * 2,  # TODO
                    "graphicStrokeOffset": 0.0,
                    "Z": 0,
                }
            elif symbol["type"] == "CIMPolygonSymbol":
                markerPlacementType = layer.get("markerPlacement",{}).get("type")
                if markerPlacementType == "CIMMarkerPlacementInsidePolygon":
                    markerPlacement = layer.get("markerPlacement", {})
                    maxX = symbolizer.get("maxX") or symbolizer["size"] / 2
                    maxY = symbolizer.get("maxY") or symbolizer["size"] / 2
                    margin = proccessMarkerPlacementInsidePolygon(markerPlacement, maxX, maxY)
                    symbolizer = {
                        "kind": "Fill",
                        "opacity": 1.0,
                        "perpendicularOffset": 0.0,
                        "graphicFill": [symbolizer],
                        "graphicFillMargin": margin,
                        "Z": 0,
                    }
                elif markerPlacementType == "CIMMarkerPlacementAlongLineSameSize":
                    symbolizer = {
                        "kind": "Line",
                        "opacity": 1.0,
                        "size": symbolizer.get("size", 10),
                        "perpendicularOffset": symbolizer.get("perpendicularOffset", 0.0),
                        "graphicStroke": [symbolizer],
                        "Z": 0,
                    }
        symbolizers.append(symbolizer)
    return symbolizers


def proccessMarkerPlacementInsidePolygon(markerPlacement, maxX, maxY):
    # We use SLD graphic-margin as top, right, bottom, left to mimic the combination of
    # ArcGIS stepX, stepY, offsetX, offsetY
    stepX = markerPlacement.get("stepX", 0)
    stepY = markerPlacement.get("stepY", 0)
    offsetX = markerPlacement.get("offsetX", 0)
    offsetY = markerPlacement.get("offsetY", 0)
    if offsetX:
        right = offsetX % stepX
        left = stepX - right
    else:
        right = left = stepX - maxX
    if offsetY:
        top = offsetY % stepY
        bottom = stepY - top
    else:
        top = bottom = stepY - maxY
    return [top, right, bottom, left]


def processEffect(effect):
    if effect["type"] == "CIMGeometricEffectDashes":
        return {
            "dasharray": " ".join(str(math.ceil(v)) for v in effect.get("dashTemplate",[]))
        }
    else:
        return {}


def _hatchMarkerForAngle(angle):
    quadrant = math.floor(((angle + 22.5) % 180) / 45.0)
    return [
        "shape://horline",
        "shape://slash",
        "shape://vertline",
        "shape://backslash",
    ][quadrant]


def _esriFontToStandardSymbols(charindex):
    mapping = {
        33: "circle",
        34: "square",
        35: "triangle",
        40: "circle",
        41: "square",
        42: "triangle",
        94: "star",
        95: "star",
        203: "cross",
        204: "cross",
    }
    if charindex in mapping:
        return mapping[charindex]
    else:
        _warnings.append(
            f"Unsupported symbol from ESRI font (character index {charindex}) replaced by default marker"
        )
        return "circle"


def processSymbolLayer(layer, symboltype, options):
    replaceesri = options.get("replaceesri", False)
    if layer["type"] == "CIMSolidStroke":
        effects = {}
        if "effects" in layer:
            for effect in layer["effects"]:
                effects.update(processEffect(effect))
        if symboltype == "CIMPolygonSymbol":
            stroke = {
                "kind": "Fill",
                "outlineColor": processColor(layer.get("color")),
                "outlineOpacity": processOpacity(layer.get("color")),
                "outlineWidth": layer["width"],
            }
            if "dasharray" in effects:
                stroke["outlineDasharray"] = effects["dasharray"]
        else:
            stroke = {
                "kind": "Line",
                "color": processColor(layer.get("color")),
                "opacity": processOpacity(layer.get("color")),
                "width": layer["width"],
                "perpendicularOffset": 0.0,
                "cap": layer["capStyle"].lower(),
                "join": layer["joinStyle"].lower(),
            }
            if "dasharray" in effects:
                stroke["dasharray"] = effects["dasharray"]
        return stroke
    elif layer["type"] == "CIMSolidFill":
        color = layer.get("color")
        if color is not None:
            return {
                "kind": "Fill",
                "opacity": processOpacity(color),
                "color": processColor(color),
                "fillOpacity": 1.0,
            }
    elif layer["type"] == "CIMCharacterMarker":
        fontFamily = layer["fontFamilyName"]
        charindex = layer["characterIndex"]
        hexcode = hex(charindex)
        # Sizes are in pt in ArcGIS, in px in SLD
        size = layer["size"] * PT_TO_PX_FACTOR
        if fontFamily == ESRI_SYMBOLS_FONT and replaceesri:
            name = _esriFontToStandardSymbols(charindex)
        else:
            name = "ttf://%s#%s" % (fontFamily, hexcode)
        rotate = layer.get("rotation", 0)
        # Rotation direction is by default counterclockwise in lyrx (clockwise in SLD)
        rotateClockwise = layer.get("rotateClockwise", False)
        if not rotateClockwise:
            rotate *= -1
        try:
            symbolLayers = layer["symbol"]["symbolLayers"]
            fillColor = _extractFillColor(symbolLayers)
            fillOpacity = _extractFillOpacity(symbolLayers)
            strokeOpacity = _extractStrokeOpacity(symbolLayers)
            strokeColor, strokeWidth = _extractStroke(symbolLayers)
        except KeyError:
            fillColor = "#000000"
            fillOpacity = 1.0
            strokeOpacity = 0
            strokeColor = "#000000"
            strokeWidth = 0.0
        return {
            "opacity": 1.0,
            "offset": _extractOffset(layer),
            "fillOpacity": fillOpacity,
            "strokeColor": strokeColor,
            "strokeOpacity": strokeOpacity,
            "strokeWidth": strokeWidth,
            "rotate": rotate,
            "kind": "Mark",
            "color": fillColor,
            "wellKnownName": name,
            "size": size,
            "Z": 0,
        }

    elif layer["type"] == "CIMVectorMarker":
        # Default values
        fillColor = "#ff0000"
        strokeColor = "#000000"
        strokeWidth = 1.0
        size = 10
        wellKnownName = "circle"
        maxX = maxY = None

        markerGraphics = layer.get("markerGraphics", [])
        if markerGraphics:
            # TODO: support multiple marker graphics
            markerGraphic = markerGraphics[0]
            marker = processSymbolReference(markerGraphic, {})[0]
            sublayers = [sublayer for sublayer in markerGraphic["symbol"]["symbolLayers"] if sublayer["enable"]]
            fillColor = _extractFillColor(sublayers)
            strokeColor, strokeWidth = _extractStroke(sublayers)
            size = marker.get("size", 10)
            if markerGraphic["symbol"]["type"] == "CIMPointSymbol":
                wellKnownName = marker["wellKnownName"]
            elif markerGraphic["symbol"]["type"] in ["CIMLineSymbol", "CIMPolygonSymbol"]:
                shape = to_wkt(markerGraphic.get("geometry"))
                wellKnownName = shape["wellKnownName"]
                maxX = shape.get("maxX")
                maxY = shape.get("maxY")

        marker = {
            "opacity": 1.0,
            "rotate": 0.0,
            "kind": "Mark",
            "color": fillColor,
            "wellKnownName": wellKnownName,
            "size": size,
            "strokeColor": strokeColor,
            "strokeWidth": strokeWidth,
            "strokeOpacity": 1.0,
            "fillOpacity": 1.0,
            "Z": 0,
        }
        if maxX:
            marker["maxX"] = maxX
        if maxY:
            marker["maxY"] = maxY
        markerPlacement = layer.get("markerPlacement", {}).get("placementTemplate")
        # Conversion of dash arrays is made on a case-by-case basis
        if markerPlacement == [12, 3]:
            marker["strokeDasharray"] = "4 0 4 7"
            marker["size"] = 6
            marker["perpendicularOffset"] = -3.5
        elif markerPlacement == [15]:
            marker["strokeDasharray"] = "0 5 9 1"
            marker["size"] = 10
        return marker

    elif layer["type"] == "CIMHatchFill":
        rotation = layer.get("rotation", 0)
        separation = layer.get("separation", 2)
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
                    "size": separation + width,
                    "strokeColor": color,
                    "strokeWidth": width,
                    "rotate": 0,
                }
            ],
            "Z": 0,
        }

    elif layer["type"] in ["CIMPictureFill", "CIMPictureMarker"]:
        url = layer["url"]
        if not os.path.exists(url):
            tokens = url.split(";")
            if len(tokens) == 2:
                ext = tokens[0].split("/")[-1]
                data = tokens[1][len("base64,") :]
                path = os.path.join(
                    tempfile.gettempdir(),
                    "bridgestyle",
                    str(uuid.uuid4()).replace("-", ""),
                )
                iconName = f"{str(uuid.uuid4())}.{ext}"
                iconFile = os.path.join(path, iconName)
                os.makedirs(path, exist_ok=True)
                with open(iconFile, "wb") as f:
                    f.write(base64.decodebytes(data.encode()))
                    _usedIcons.append(iconFile)
                url = iconFile

        rotate = layer.get("rotation", 0)
        size = layer.get("height", layer.get("size"))
        return {
            "opacity": 1.0,
            "rotate": 0.0,
            "kind": "Icon",
            "color": None,
            "image": url,
            "size": size,
            "Z": 0,
        }
    else:
        return None


def _getGraduatedSymbolRotation(renderer, tolowercase):
    visualVariables = renderer.get("visualVariables", [])
    for visualVariable in visualVariables:
        if visualVariable.get("visualVariableInfoZ",{}).get("visualVariableInfoType") == "Expression":
            return _processArcadeRotationExpression(
                visualVariable.get("visualVariableInfoZ",{}).get("valueExpressionInfo",{}).get("expression"),
                tolowercase
            )


def _processArcadeRotationExpression(expression, tolowercase):
    field = expression.replace("$feature.","")
    return [
            "Sub",
            ["PropertyName", field.lower() if tolowercase else field],
            90,
        ]


def _extractStroke(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidStroke":
            color = processColor(sl.get("color"))
            width = sl["width"]
            return color, width
    return "#000000", 0


def _extractStrokeOpacity(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidStroke":
            try:
                opacity = sl["color"]["values"][3] / 100
            except (KeyError, IndexError):
                opacity = 1.0
            return opacity
    return 1.0


def _extractFillColor(symbolLayers):
    color = "#ffffff"
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidFill":
            color = processColor(sl.get("color"))
        elif sl["type"] == "CIMCharacterMarker":
            color = _extractFillColor(sl["symbol"]["symbolLayers"])
    return color


def _extractFillOpacity(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidFill":
            try:
                opacity = sl["color"]["values"][-1] / 100
            except (KeyError, IndexError):
                opacity = 1.0
            return opacity
    return 1.0


def _extractOffset(symbolLayer):
    # Arcgis looks to round part-pixel values.
    offset_x = round(symbolLayer.get("offsetX", 0))
    offset_y = round(symbolLayer.get("offsetY", 0) * -1)
    if offset_x == 0 and offset_y != 0:
        return None
    return [offset_x, offset_y]


def processOpacity(color):
    if color is None:
        return 1.0
    return color["values"][-1] / 100


def processColor(color):
    if color is None:
        return "#000000"
    values = color["values"]
    if color["type"] == "CIMRGBColor":
        return "#%02x%02x%02x" % (int(values[0]), int(values[1]), int(values[2]))
    elif color["type"] == "CIMCMYKColor":
        r, g, b = cmyk2Rgb(values)
        return "#%02x%02x%02x" % (r, g, b)
    elif color["type"] == "CIMHSVColor":
        r, g, b = hsv2rgb(values)
        return "#%02x%02x%02x" % (int(r), int(g), int(b))
    elif color["type"] == "CIMGrayColor":
        return "#%02x%02x%02x" % (int(values[0]), int(values[0]), int(values[0]))
    else:
        return "#000000"


def cmyk2Rgb(cmyk_array):
    c = cmyk_array[0]
    m = cmyk_array[1]
    y = cmyk_array[2]
    k = cmyk_array[3]

    r = int(255 * (1 - c / 100) * (1 - k / 100))
    g = int(255 * (1 - m / 100) * (1 - k / 100))
    b = int(255 * (1 - y / 100) * (1 - k / 100))

    return r, g, b


def hsv2rgb(hsv_array):
    h = hsv_array[0] / 360
    s = hsv_array[1] / 100
    v = hsv_array[2] / 100
    if s == 0.0:
        v *= 255
        return (v, v, v)
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = 255 * (v * (1.0 - s))
    q = 255 * (v * (1.0 - s * f))
    t = 255 * (v * (1.0 - s * (1.0 - f)))
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
