import base64
import math
import os
import tempfile
import uuid
from typing import Union


from .constants import ESRI_SYMBOLS_FONT, POLYGON_FILL_RESIZE_FACTOR, OFFSET_FACTOR, pt_to_px
from .expressions import convertExpression, convertWhereClause, processRotationExpression
from .wkt_geometries import to_wkt


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
    tolowercase = options.get("tolowercase", False)
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
        
        elif renderer["type"] == "CIMChartRenderer":
            rules.extend(processChartRenderer(renderer, options))
        else:
            _warnings.append("Unsupported renderer type: %s" % str(renderer))
            return geostyler

        if layer.get("labelVisibility", False):
            for labelClass in layer.get("labelClasses", []):
                rules.append(
                    processLabelClass(labelClass, tolowercase)
                )

        rotation = _getSymbolRotationFromVisualVariables(renderer, tolowercase)
        if rotation:
            for rule in rules:
                [symbolizer.update({"rotate": rotation}) for symbolizer in rule["symbolizers"]]

        geostyler["rules"] = rules
    elif layer["type"] == "CIMRasterLayer":
        _warnings.append('CIMRasterLayer are not supported yet.')
        # rules = [{"name": layer["name"], "symbolizers": [rasterSymbolizer(layer)]}]
        # geostyler["rules"] = rules

    return geostyler


def processClassBreaksRenderer(renderer, options):
    rules = []
    symbolsAscending = []
    field = renderer["field"]
    lastbound = None
    tolowercase = options.get("tolowercase", False)
    rotation = _getSymbolRotationFromVisualVariables(renderer, tolowercase)
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
        symbolsAscending.append(symbolizers)
        rules.append(ruledef)
    if not renderer.get('showInAscendingOrder', True):
        rules.reverse()
        for index, rule in enumerate(rules):
            rule["symbolizers"] = symbolsAscending[index]
    return rules


def processChartRenderer(renderer, options):
    rules = []

    # Basic setup for chart renderer
    to_lower = options.get("tolowercase", False)
    fields = renderer.get("fieldNames", [])
    norm_fields = [f.lower() if to_lower else f for f in fields]

    if not norm_fields:
        _warnings.append(
            "CIMChartRenderer skipped: fieldNames list is empty; "
            "chart cannot be generated."
        )
        return rules

    symbol_layers = renderer.get("chartSymbol", {}).get("symbol", {}).get("symbolLayers", [])
    chart_layer = next(
        (
            ly for ly in symbol_layers
            if ly.get("type") in {"CIMPieChartMarker", "CIMBarChartMarker", "CIMStackedBarChartMarker"}
        ),
        None
    )
    if not chart_layer:
        _warnings.append(
            "CIMChartRenderer skipped: unsupported symbol layer "
            "(only CIMPieChartMarker, CIMBarChartMarker, or CIMStackedBarChartMarker are handled)."
        )
        return rules

    # Colors & opacities
    fill_colors = []
    opacities = []

    for part in chart_layer.get("parts", []):
        polygon_symbol = part.get("polygonSymbol", {})
        fill_layer = next(
            (
                sl for sl in polygon_symbol.get("symbolLayers", [])
                if sl.get("type") == "CIMSolidFill" and sl.get("enable", True)
            ),
            None,
        )
        color = fill_layer.get("color") if fill_layer else None
        fill_colors.append(_processColor(color).lstrip("#") if color else "000000")
        opacities.append(_processOpacity(color) if color else 1.0)

    avg_opacity = sum(opacities) / len(opacities) if opacities else 1.0

    # Build Image-Chart expression
    total_expr = "(" + " + ".join(norm_fields) + ")"
    expr_list = [f"${{100 * {fld} / {total_expr}}}" for fld in norm_fields]

    if chart_layer["type"] == "CIMPieChartMarker":
        chart_type = "p3"
        chart_data = ",".join(expr_list)
    elif chart_layer["type"] == "CIMBarChartMarker":
        chart_type = "bvg"
        chart_data = "|".join(expr_list)
    else:  # CIMStackedBarChartMarker
        chart_type = "bvs"
        chart_data = "|".join(expr_list)

    # Size clamping (Esri → Image‑Charts)
    base_size = chart_layer.get("size", 40)
    if chart_type in {"bvg", "bvs"}:
        default_size = max(min(base_size + 10, 80), 48)
    else:  # pie
        default_size = max(min(base_size, 60), 32)

    # Build image‑charts URL
    chart_url = (
        f"http://chart?"
        f"cht={chart_type}"
        f"&chd=t:{chart_data}"
        f"&chco={','.join(fill_colors)}"
        f"&chf=bg,s,FFFFFF00"
    )

    if chart_type == "p3":
        # Rotation only on pie charts (chp) → prefer explicit rotation on the layer; else fall back to visual variable
        rotation_fallback = _getSymbolRotationFromVisualVariables(renderer, to_lower)
        rotation_deg = chart_layer.get("rotation", rotation_fallback or 0)
        chp_deg = (rotation_deg + 180) % 360  # chp is clockwise from 3 o’clock, so add 180 deg
        chp_rad = round(math.radians(chp_deg), 4)
        chart_url += f"&chp={chp_rad}"
    elif chart_type in {"bvg", "bvs"}:  # bar charts need bar‑width param
        chart_url += "&chbh=a,1,2"

    # Final symbolizer & rule
    chart_symbolizer = {
        "kind": "Icon",
        "image": chart_url,
        "size": default_size,
        "opacity": round(avg_opacity, 2),
        "format": "application/chart",
    }

    # Include base symbolizers if a baseSymbol is present
    base_symbolizers = []
    if "baseSymbol" in renderer:
        base_symbolizers = processSymbolReference(renderer["baseSymbol"], options)

    rules.append({
        "name": "Chart",
        "symbolizers": base_symbolizers + [chart_symbolizer],
    })

    return rules


def processLabelClass(labelClass, tolowercase=False):
    textSymbol = labelClass["textSymbol"]["symbol"]
    expression = convertExpression(labelClass["expression"], labelClass["expressionEngine"], tolowercase)
    fontFamily = textSymbol.get("fontFamilyName", "Arial")
    fontSize = _ptToPxProp(textSymbol, 'height', 12, True)
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
    maplexPrimaryOffset = _ptToPxProp(maplexProperties, "primaryOffset", 0)
    maplexPointPlacementMethod = maplexProperties.get("pointPlacementMethod")
    if stdPlacementType == "Line" and maplexPlacementType == "Line":
        # We use this as a flag to later indicate the it is a line label when converting to SLD
        primaryOffset = _ptToPxProp(textSymbol, "primaryOffset", 0)
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
    haloSize = _ptToPxProp(textSymbol, "haloSize", 0)
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

    def _or(listConditions):
        orConditions = listConditions
        orConditions.insert(0, 'Or')
        return orConditions

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
            ruleFilter = conditions[0] if len(conditions) <= 1 else _or(conditions)

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
                # Functions "xyzPoint" and "xyzAngle" are not supported in the legend in GeoServer,
                # so we include this symbol only on the map and not in the legend (using inclusion: "mapOnly")
                if layer["type"] == "CIMCharacterMarker" and _orientedMarkerAtRatioOfLine(layer["markerPlacement"], 1):
                    symbolizer = _processOrientedMarkerAtFunctionOfLine(layer, "end", options)
                    symbolizer["inclusion"] = "mapOnly"
                elif layer["type"] == "CIMCharacterMarker" and _orientedMarkerAtRatioOfLine(layer["markerPlacement"], 0.5):
                    symbolizer = _processOrientedMarkerAtFunctionOfLine(layer, "mid", options)
                    symbolizer["inclusion"] = "mapOnly"
                elif layer["type"] == "CIMCharacterMarker" and _orientedMarkerAtRatioOfLine(layer["markerPlacement"], 0):
                    symbolizer = _processOrientedMarkerAtFunctionOfLine(layer, "start", options)
                    symbolizer["inclusion"] = "mapOnly"
                else:
                    symbolizer = _formatLineSymbolizer(symbolizer)
            elif symbol["type"] == "CIMPolygonSymbol":
                markerPlacement = layer.get("markerPlacement",{})
                symbolizer = _formatPolygonSymbolizer(symbolizer, markerPlacement)
        symbolizers.append(symbolizer)
    return symbolizers

def _formatLineSymbolizer(symbolizer):
    return {
        "kind": "Line",
        "opacity": 1.0,
        "perpendicularOffset": 0.0,
        "graphicStroke": [symbolizer],
        "graphicStrokeInterval": _ptToPxProp(symbolizer, "size", 0) * 2,  # TODO
        "graphicStrokeOffset": 0.0,
        "Z": 0,
    }

def _formatPolygonSymbolizer(symbolizer, markerPlacement):
    markerPlacementType = markerPlacement.get("type")
    if markerPlacementType == "CIMMarkerPlacementInsidePolygon":
        margin = processMarkerPlacementInsidePolygon(symbolizer, markerPlacement)
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
            "size": _ptToPxProp(symbolizer, "size", 10),
            "perpendicularOffset": _ptToPxProp(symbolizer, "perpendicularOffset", 0.0),
            "graphicStroke": [symbolizer],
            "Z": 0,
        }
    return symbolizer

def _processOrientedMarkerAtFunctionOfLine(layer, functionPrefix, options):
    replaceesri = options.get("replaceesri", False)
    fontFamily = layer["fontFamilyName"]
    charindex = layer["characterIndex"]
    hexcode = hex(charindex)
    if fontFamily == ESRI_SYMBOLS_FONT and replaceesri:
        name = _esriFontToStandardSymbols(charindex)
    else:
        name = "ttf://%s#%s" % (fontFamily, hexcode)
    rotation = layer.get("rotation", 0)
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
        "fillOpacity": fillOpacity,
        "strokeColor": strokeColor,
        "strokeOpacity": strokeOpacity,
        "strokeWidth": strokeWidth,
        "rotate": ["Add", [f"{functionPrefix}Angle", ["geometry"]], rotation],
        "kind": "Mark",
        "color": fillColor,
        "wellKnownName": name,
        "size": _ptToPxProp(layer, "size", 10),
        "Z": 0,
        "Geometry": [f"{functionPrefix}Point", ["geometry"]],
    }


def processMarkerPlacementInsidePolygon(symbolizer, markerPlacement):
    # In case of markers in a polygon fill, it seems ArcGIS does some undocumented resizing of the marker.
    # We use an empirical factor to account for this, which works in most cases (but not all)
    # Size is already in pixel.
    size = round(symbolizer.get("size", 0) * POLYGON_FILL_RESIZE_FACTOR)
    symbolizer["size"] = size
    # We use SLD graphic-margin as top, right, bottom, left to mimic the combination of
    # ArcGIS stepX, stepY, offsetX, offsetY
    if symbolizer.get("maxX") and symbolizer.get("maxY"):
        # MaxX and MaxY are a custom property for shapes and already in px.
        maxX = math.floor(symbolizer["maxX"] * POLYGON_FILL_RESIZE_FACTOR)
        maxY = math.floor(symbolizer["maxY"] * POLYGON_FILL_RESIZE_FACTOR)
    else:
        maxX = size / 2
        maxY = size / 2
    stepX = _ptToPxProp(markerPlacement, "stepX", 0)
    stepY = _ptToPxProp(markerPlacement, "stepY", 0)
    offsetX = _ptToPxProp(markerPlacement, "offsetX", 0)
    offsetY = _ptToPxProp(markerPlacement, "offsetY", 0)
    right = round(stepX / 2 - maxX - offsetX)
    left = round(stepX / 2 - maxX + offsetX)
    top = round(stepY / 2 - maxY - offsetY)
    bottom = round(stepY / 2 - maxY + offsetY)
    return [top, right, bottom, left]


def _extractEffect(layer):
    effects = {}
    if "effects" in layer:
        for effect in layer["effects"]:
            effects.update(_processEffect(effect))
    return effects


def _processEffect(effect):
    ptToPxAndCeil = lambda v : math.ceil(pt_to_px(v))
    if effect["type"] == "CIMGeometricEffectDashes":
        dasharrayValues = list(map(ptToPxAndCeil, effect.get("dashTemplate",[])))
        return {
            "dasharrayValues": dasharrayValues,
            "dasharray": " ".join(str(v) for v in dasharrayValues)
        }
    else:
        return {}


def _getStraightHatchMarker():
    return ["shape://horline", "shape://vertline"]


def _getTiltedHatchMarker():
    return ["shape://slash", "shape://backslash"]


def _hatchMarkerForAngle(angle):
    straightHatchMarkers = _getStraightHatchMarker()
    tiltedHatchMarkers = _getTiltedHatchMarker()
    quadrant = math.floor(((angle + 22.5) % 180) / 45.0)
    return [
        straightHatchMarkers[0],
        tiltedHatchMarkers[0],
        straightHatchMarkers[1],
        tiltedHatchMarkers[1],
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


def apply_color_substitution(image_data, substitutions):
    try:
        from PIL import Image
        from io import BytesIO
    except ImportError:
        # Optional: emit logging warning instead of print
        print("Warning: Pillow is not installed. Skipping color substitution.")
        return image_data

    try:
        original_image = Image.open(BytesIO(image_data))
        image = original_image.convert("RGBA")
        pixels = image.load()

        color_map = {}
        for sub in substitutions:
            old = _hexToRGB(_processColor(sub["oldColor"]))
            new = _hexToRGB(_processColor(sub["newColor"]))
            color_map[old] = new

        width, height = image.size
        for x in range(width):
            for y in range(height):
                r, g, b, a = pixels[x, y]
                if (r, g, b) in color_map:
                    nr, ng, nb = color_map[(r, g, b)]
                    pixels[x, y] = (nr, ng, nb, a)

        output = BytesIO()
        # Use PNG as Python writes in BGR order, but Java cannot read it
        image.save(output, format="PNG")
        return output.getvalue()

    except Exception as e:
        print(f"Warning: Failed to apply color substitution: {e}")
        return None

def processSymbolLayer(layer, symboltype, options):
    replaceesri = options.get("replaceesri", False)
    if layer["type"] == "CIMSolidStroke":
        effects = _extractEffect(layer)
        if symboltype == "CIMPolygonSymbol":
            stroke = {
                "kind": "Fill",
                "outlineColor": _processColor(layer.get("color")),
                "outlineOpacity": _processOpacity(layer.get("color")),
                "outlineWidth": _ptToPxProp(layer, "width", 0),
            }
            if "dasharray" in effects:
                stroke["outlineDasharray"] = effects["dasharray"]
        else:
            stroke = {
                "kind": "Line",
                "color": _processColor(layer.get("color")),
                "opacity": _processOpacity(layer.get("color")),
                "width": _ptToPxProp(layer, "width", 0),
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
                "opacity": _processOpacity(color),
                "color": _processColor(color),
                "fillOpacity": 1.0,
            }
    elif layer["type"] == "CIMCharacterMarker":
        fontFamily = layer["fontFamilyName"]
        charindex = layer["characterIndex"]
        hexcode = hex(charindex)
        size = _ptToPxProp(layer, "size", 12)
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
        if layer['size']:
            layer['size'] = _ptToPxProp(layer, "size", 3)
        # Default values
        fillColor = "#ff0000"
        strokeColor = "#000000"
        strokeWidth = 1.0
        markerSize = 10
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
                maxX = _ptToPxProp(shape, "maxX", 0)
                maxY = _ptToPxProp(shape, "maxY", 0)

        marker = {
            "opacity": 1.0,
            "rotate": 0.0,
            "kind": "Mark",
            "color": fillColor,
            "wellKnownName": wellKnownName,
            "size": markerSize,
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
            marker["outlineDasharray"] = "4 0 4 7"
            marker["size"] = 6
            marker["perpendicularOffset"] = -3.5
        elif markerPlacement == [15]:
            marker["outlineDasharray"] = "0 5 9 1"
            marker["size"] = 10
        return marker

    elif layer["type"] == "CIMHatchFill":
        rotation = layer.get("rotation", 0)
        size = _ptToPxProp(layer, "separation", 3)
        symbolLayers = layer["lineSymbol"]["symbolLayers"]
        color, width = _extractStroke(symbolLayers)
        wellKnownName = _hatchMarkerForAngle(rotation)
        # separation is distance between lines, for diagonal lines, it is along the orthogonal axis,
        # so we need to multiply it by sqrt(2) to get the size of the separation
        if "slash" in wellKnownName:
            size = size * math.sqrt(2)
        offset = _extractOffset(layer)
        fill = {
            "kind": "Fill",
            "opacity": 1.0,
            "graphicFill": [
                {
                    "kind": "Mark",
                    "color": color,
                    "wellKnownName": wellKnownName,
                    "size": size,
                    "strokeColor": color,
                    "strokeWidth": width,
                    "cap": "round",
                    "rotate": 0,
                    "offset": offset
                }
            ],
            "Z": 0,
        }
        effects = _extractEffect(symbolLayers[0])
        if "dasharray" in effects:
            fill["graphicFill"][0]["outlineDasharray"] = effects["dasharray"]
            # In case of dash array, the size must be at least as long as the dash pattern sum.
            neededSize = sum(effects["dasharrayValues"])
            if wellKnownName in _getStraightHatchMarker():
                # To keep the "original size", we play with a negative margin
                negativeMargin = (neededSize - size) / 2 * -1
                if wellKnownName == _getStraightHatchMarker()[0]:
                    fill['graphicFillMargin'] = [negativeMargin, 0, negativeMargin, 0]
                else:
                    fill['graphicFillMargin'] = [0, negativeMargin, 0, negativeMargin]
            else:
                # In case of slash pattern, the pattern is the hypotenuse, we want the X (or Y) value for the size.
                neededSize = math.cos(math.radians(45)) * neededSize
                # The trick with the margin to keep the original size is not possible.
                _warnings.append('Unable to keep the original size of CIMHatchFill with tilted symbol (slash).')
            fill["graphicFill"][0]["size"] = neededSize
        return fill

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
                image = base64.decodebytes(data.encode())
                colorSubstitutions = layer.get("colorSubstitutions")
                if colorSubstitutions:
                    image = apply_color_substitution(image, colorSubstitutions)
                    ext = "png" # Color substitution requires PNG format
                iconName = f"{str(uuid.uuid4())}.{ext}"
                iconFile = os.path.join(path, iconName)
                os.makedirs(path, exist_ok=True)
                with open(iconFile, "wb") as f:
                    f.write(image)
                    _usedIcons.append(iconFile)
                url = iconFile

        rotate = layer.get("rotation", 0)
        size = _ptToPxProp(layer, "height", _ptToPxProp(layer, "size", 0))
        if layer["type"] == "CIMPictureFill":
            return {
                "kind": "Fill",
                "opacity": 1.0,
                "graphicFill": [
                    {
                        "opacity": 1.0,
                        "rotate": 0.0,
                        "kind": "Icon",
                        "color": None,
                        "image": url,
                        "size": size,
                        "Z": 0,
                    }
                ],
                "Z": 0,
                }
        else:
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


def _getSymbolRotationFromVisualVariables(renderer, tolowercase):
    for visualVariable in renderer.get("visualVariables", []):
        if visualVariable["type"] == "CIMRotationVisualVariable":
            expression = \
                visualVariable["visualVariableInfoZ"].get("valueExpressionInfo", {}).get("expression") or \
                    visualVariable["visualVariableInfoZ"].get("expression")
            rotationType = visualVariable["rotationTypeZ"]
            return processRotationExpression(
                    expression,
                    rotationType,
                    tolowercase
                )
    return None


def _orientedMarkerAtRatioOfLine(markerPlacement, ratio):
    if markerPlacement["type"] == "CIMMarkerPlacementAtRatioPositions":
        return markerPlacement["positionArray"] == [ratio] and markerPlacement["angleToLine"]
    return False


def _extractOffset(symbolLayer):
    # Offsets in ArcGIS are in points, but we need them in pixels. Also, they are orientated same as in SLD
    # (x points to the right, y points up). Finally, Arcgis looks to apply a strange factor.
    offset_x = _ptToPxProp(symbolLayer, "offsetX", 0) * OFFSET_FACTOR
    offset_y = _ptToPxProp(symbolLayer, "offsetY", 0) * OFFSET_FACTOR
    if offset_x == 0 and offset_y == 0:
        return None
    return [offset_x, offset_y]


def _extractStroke(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidStroke":
            color = _processColor(sl.get("color"))
            width = _ptToPxProp(sl, "width", 0)
            return color, width
    return "#000000", 0


def _extractStrokeOpacity(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidStroke":
            return _processOpacity(sl["color"])
    return 1.0


def _extractFillColor(symbolLayers):
    color = "#ffffff"
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidFill":
            color = _processColor(sl.get("color"))
        elif sl["type"] == "CIMCharacterMarker":
            color = _extractFillColor(sl["symbol"]["symbolLayers"])
    return color


def _extractFillOpacity(symbolLayers):
    for sl in symbolLayers:
        if sl["type"] == "CIMSolidFill":
            return _processOpacity(sl["color"])
    return 1.0


def _processOpacity(color):
    if color is None:
        return 1.0
    return color["values"][-1] / 100


def _processColor(color):
    if color is None:
        return "#000000"
    values = color["values"]
    if color["type"] == "CIMRGBColor":
        return "#%02x%02x%02x" % (int(values[0]), int(values[1]), int(values[2]))
    elif color["type"] == "CIMCMYKColor":
        r, g, b = _cmyk2Rgb(values)
        return "#%02x%02x%02x" % (r, g, b)
    elif color["type"] == "CIMHSVColor":
        r, g, b = _hsv2rgb(values)
        return "#%02x%02x%02x" % (int(r), int(g), int(b))
    elif color["type"] == "CIMGrayColor":
        return "#%02x%02x%02x" % (int(values[0]), int(values[0]), int(values[0]))
    else:
        return "#000000"
    
def _hexToRGB(hex_string):
    """Convert '#rrggbb' to (r, g, b) tuple."""
    hex_string = hex_string.lstrip("#")
    return tuple(int(hex_string[i:i+2], 16) for i in (0, 2, 4))    

def _cmyk2Rgb(cmyk_array):
    c = cmyk_array[0]
    m = cmyk_array[1]
    y = cmyk_array[2]
    k = cmyk_array[3]

    r = int(255 * (1 - c / 100) * (1 - k / 100))
    g = int(255 * (1 - m / 100) * (1 - k / 100))
    b = int(255 * (1 - y / 100) * (1 - k / 100))

    return r, g, b


def _hsv2rgb(hsv_array):
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


def _ptToPxProp(obj: dict, prop: str, defaultValue: Union[float, int], asFloat=True) -> Union[float, int]:
    """
    :return: The property's value in pt transformed into a px value, or the provided defaultValue.
    """
    if obj.get(prop) is None:
        return defaultValue
    value = pt_to_px(float(obj.get(prop)))
    return value if asFloat else round(value)
