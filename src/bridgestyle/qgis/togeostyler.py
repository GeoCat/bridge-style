import json
import math
import os
from typing import Optional

from .expressions import ExpressionConverter, UnsupportedExpressionException

try:
    from qgis.core import *
    from qgis.PyQt.QtCore import QSize, Qt
    from qgis.PyQt.QtGui import QColor, QImage, QPainter
except:
    QPainter = None

# Constants
NO_ICON = "no_icon"
MM2PIXEL = 3.571428571428571  # 1/0.28 -- OGC defines a pixel as 0.28*0.28mm
POINT2PIXEL = MM2PIXEL * 0.353  # 1/72 * 25.4 = 0.353  -- 1 pt = 1/72inch  25.4 mm in an inch
SPRITE_SIZE = 64  # should be power of 2
if QPainter is None:
    BLEND_MODES = {}
else:
    BLEND_MODES = {
        QPainter.CompositionMode.CompositionMode_Plus: "addition",
        QPainter.CompositionMode.CompositionMode_Multiply: "multiply",
        QPainter.CompositionMode.CompositionMode_Screen: "screen",
        QPainter.CompositionMode.CompositionMode_Overlay: "overlay",
        QPainter.CompositionMode.CompositionMode_Darken: "darken",
        QPainter.CompositionMode.CompositionMode_Lighten: "lighten",
        QPainter.CompositionMode.CompositionMode_ColorDodge: "dodge",
        QPainter.CompositionMode.CompositionMode_ColorBurn: "color-burn",
        QPainter.CompositionMode.CompositionMode_HardLight: "hard-light",
        QPainter.CompositionMode.CompositionMode_SoftLight: "soft-light",
        QPainter.CompositionMode.CompositionMode_Difference: "difference"
    }
PATTERN_NAMES = {
    "horizontal": "shape://horline",
    "vertical": "shape://vertline",
    "cross": "shape://times"
    # TODO
}
FIXED_PATTERN_SIZE = 10
SHAPE_NAMES = {
    "regular_star": "star",
    "cross2": "shape://times",
    "equilateral_triangle": "triangle",
    "rectangle": "square",
    "arrowhead": "shape://oarrow",
    "filled_arrowhead": "shape://coarrow",
    "line": "shape://vertline",
    "cross": "shape://plus",
    "cross_filled": "shape://plus"
}

# Global variable
_expressionConverter: Optional[ExpressionConverter] = None
_usedIcons = {}
_usedSprites = {}  # sprite name -> {"image":Image, "image2x":Image}
_warnings = []


def convert(layer, options=None):
    """ Main entry point for converting a QGIS layer to a GeoStyler style. """
    global _usedIcons, _usedSprites, _warnings

    _usedIcons = {}
    _usedSprites = {}
    _warnings = []

    geostyler = processLayer(layer)
    if geostyler is None:
        geostyler = {"name": layer.name()}

    return geostyler, _usedIcons, _usedSprites, _warnings


def processLayer(layer):
    global _expressionConverter

    _expressionConverter = ExpressionConverter(layer)

    geostyler = {"name": layer.name()}
    if layer.type() == layer.VectorLayer:
        rules = []
        renderer = layer.renderer()
        if renderer is None:
            _warnings.append("No renderer found for layer: %s" % layer.name())
            return
        if isinstance(renderer, QgsHeatmapRenderer):
            symbolizer, transformation = heatmapRenderer(renderer)
            if symbolizer and transformation:
                rules = [{"name": layer.name(), "symbolizers": [symbolizer]}]
                geostyler["rules"] = rules
                geostyler["transformation"] = transformation
        else:
            if not isinstance(renderer, QgsNullSymbolRenderer):
                if not isinstance(renderer, QgsRuleBasedRenderer):
                    ruleRenderer = QgsRuleBasedRenderer.convertFromRenderer(
                        renderer)
                else:
                    ruleRenderer = renderer
                if ruleRenderer is None:
                    _warnings.append(
                        "Unsupported renderer type: %s" % str(renderer))
                    return
                for rule in ruleRenderer.rootRule().children():
                    if rule.active():
                        rules.extend(processRule(rule, None, layer.opacity(), layer))
            labelingRules = processLabelingLayer(layer)
            if labelingRules:
                rules = rules + labelingRules
            geostyler["rules"] = rules
    elif layer.type() == layer.RasterLayer:
        rules = [{"name": layer.name(), "symbolizers": [
            rasterSymbolizer(layer)]}]
        geostyler["rules"] = rules

    if layer.blendMode() in BLEND_MODES:
        geostyler["blendMode"] = BLEND_MODES[layer.blendMode()]

    return geostyler


def heatmapRenderer(renderer):
    hmRadius = renderer.radius()
    colorRamp = renderer.colorRamp()
    if not isinstance(colorRamp, QgsGradientColorRamp):
        _warnings.append("Unsupported color ramp class: %s" % str(colorRamp))
        return None, None
    colMap = {}
    colMap["type"] = "intervals" if colorRamp.isDiscrete() else "ramp"
    mapEntries = []
    mapEntries.append({"color": colorRamp.color1().name(), "quantity": 0,
                       "opacity": colorRamp.color1().alphaF(), "label": ""})
    for stop in colorRamp.stops():
        mapEntries.append({"color": stop.color.name(), "quantity": stop.offset,
                           "opacity": stop.color.alphaF(), "label": ""})
    mapEntries.append({"color": colorRamp.color2().name(), "quantity": 1,
                       "opacity": colorRamp.color2().alphaF(), "label": ""})
    colMap["colorMapEntries"] = mapEntries

    weightAttr = renderer.weightExpression()
    radius = renderer.radius()
    if renderer.radiusUnit() != QgsUnitTypes.RenderUnit.RenderPixels:
        _warnings.append(
            "Radius for heatmap renderer can only be expressed in pixels")

    channel = {"grayChannel": {"sourceChannelName": 1}}
    symbolizer = {"kind": "Raster", "opacity": 1,
                  "channelSelection": channel, "colorMap": colMap}
    transformation = {"type": "vec:Heatmap",
                      "radiusPixels": radius, "weightAttr": weightAttr}
    return symbolizer, transformation


def rasterSymbolizer(layer):
    renderer = layer.renderer()
    symbolizer = {"kind": "Raster", "opacity": renderer.opacity(),
                  "channelSelection": channelSelection(renderer)}
    colMap = colorMap(renderer)
    if colMap:
        symbolizer["colorMap"] = colMap
    return symbolizer


def channelSelection(renderer):
    # handle a WMS layer -- this is wrong, but it throws exceptions...
    if isinstance(renderer, QgsSingleBandColorDataRenderer):
        return {"grayChannel": {"sourceChannelName": str(renderer.usesBands()[0])}}
    if isinstance(renderer, QgsSingleBandGrayRenderer):
        return {"grayChannel": {"sourceChannelName": str(renderer.grayBand())}}
    elif isinstance(renderer, (QgsSingleBandPseudoColorRenderer, QgsPalettedRasterRenderer)):
        return {"grayChannel": {"sourceChannelName": str(renderer.band())}}
    elif isinstance(renderer, QgsMultiBandColorRenderer):
        bands = renderer.usesBands()
        channels = {}
        if len(bands) > 0:
            channels["redChannel"] = {"sourceChannelName": str(bands[0])}
        if len(bands) > 1:
            channels["greenChannel"] = {"sourceChannelName": str(bands[1])}
        if len(bands) > 2:
            channels["blueChannel"] = {"sourceChannelName": str(bands[2])}
        return channels
    else:
        _warnings.append(
            "Unsupported raster renderer class: '%s'" % str(renderer))
        return {}


def colorMap(renderer):
    colMap = {}
    mapEntries = []
    if isinstance(renderer, QgsSingleBandGrayRenderer):
        colMap["type"] = "ramp"
        entries = renderer.legendSymbologyItems()
        for entry in entries:
            mapEntries.append({"color": entry[1].name(), "quantity": float(entry[0]),
                               "opacity": entry[1].alphaF(), "label": entry[0]})
    elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
        cm_type = "ramp"
        shader = renderer.shader().rasterShaderFunction()
        if isinstance(shader, QgsColorRampShader):
            shader_type = shader.colorRampType()
            if shader_type == QgsColorRampShader.Type.Exact:
                cm_type = "values"
            elif shader_type == QgsColorRampShader.Type.Discrete:
                cm_type = "intervals"
        colMap["type"] = cm_type
        items = shader.colorRampItemList()
        for item in items:
            mapEntries.append({"color": item.color.name(), "quantity": item.value,
                               "label": item.label, "opacity": item.color.alphaF()})
    elif isinstance(renderer, QgsPalettedRasterRenderer):
        colMap["type"] = "values"
        classes = renderer.classes()
        for c in classes:
            mapEntries.append({"color": c.color.name(), "quantity": c.value,
                               "label": c.label, "opacity": c.color.alphaF()})
    elif isinstance(renderer, QgsMultiBandColorRenderer):
        _warnings.append(f"Unsupported raster renderer class: '{str(renderer)}'")  # TODO
        return None
    else:
        _warnings.append(f"Unsupported raster renderer class: '{str(renderer)}'")
        return None

    colMap["extended"] = True
    if mapEntries is not None:
        colMap["colorMapEntries"] = mapEntries
    return colMap


quadOffset = ["top", "top-right", "left", "center",
              "right", "bottom-left", "bottom", "bottom-right"]


# is the rule something that can be labeled?
# note #getLabelExpression() will throw exception if you shouldn't be labeling with this rule
def labelThisRule(labeling):
    if labeling.settings() is None:
        return False
    if labeling.settings().fieldName != '':
        return True
    return labeling.settings().isExpression


def processLabelingLayer(layer):
    if not layer.labelsEnabled():
        return []
    labeling = layer.labeling()
    if labeling is None:
        return []

    if isinstance(labeling, QgsRuleBasedLabeling):
        return processRuleLabeling(layer, labeling.rootRule(), "labeling")
    if not isinstance(labeling, QgsVectorLayerSimpleLabeling):
        _warnings.append("Unsupported labeling class: '%s'" % str(labeling))
        return []
    return [processLabeling(layer, labeling)]


# given a rule, calculate the full filter
# i.e. its an AND of the rule and its parents (and grand parents)
def getHierarchicalFilter(rule, filter=None):
    if rule is None:
        return filter
    filter = andFilter(
        processExpression(rule.filterExpression()),
        getHierarchicalFilter(rule.parent()))
    return filter


def processRuleLabeling(layer, labeling, name):
    result = []
    for child in labeling.children():
        if child.active():
            fullname = name + " - " + child.description()
            # filter = andFilter(filter, processExpression(
            #    child.filterExpression()))
            filter = getHierarchicalFilter(child)
            if labelThisRule(child):
                symbolizer = processLabeling(layer, child, fullname, filter)
                result.append(symbolizer)
            result += processRuleLabeling(layer, child, name)
    return result


def processLabeling(layer, labeling, name="labeling", filter=None):
    symbolizer = {"kind": "Text"}
    settings = labeling.settings()
    textFormat = settings.format()

    size = _labelingProperty(settings, textFormat,
                             "size", QgsPalLayerSettings.Property.Size)
    sizeUnits = _labelingProperty(settings, textFormat,
                                  "sizeUnit", QgsPalLayerSettings.Property.FontSizeUnit)
    size = str(_handleUnits(size, sizeUnits))
    color = textFormat.color().name()
    font = textFormat.font().family()
    rotation = _labelingProperty(
        settings, None, "angleOffset", QgsPalLayerSettings.Property.LabelRotation)
    buff = textFormat.buffer()
    if buff.enabled():
        haloColor = buff.color().name()
        haloSize = _labelingProperty(
            settings, buff, "size", QgsPalLayerSettings.Property.BufferSize)
        haloSizeUnit = _labelingProperty(
            settings, buff, "sizeUnit", QgsPalLayerSettings.Property.BufferUnit)
        haloSize = str(_handleUnits(haloSize, haloSizeUnit))
        symbolizer.update({"haloColor": haloColor,
                           "haloSize": haloSize,
                           "haloOpacity": buff.opacity()})

    if layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
        offset = _labelingProperty(settings, None, "dist")
        symbolizer["perpendicularOffset"] = offset
        if settings.placement == QgsPalLayerSettings.Placement.Curved:
            symbolizer["followLine"] = True
    else:
        anchor = quadOffset[settings.quadOffset]
        offsetX = _labelingProperty(settings, None, "xOffset")
        offsetY = _labelingProperty(settings, None, "yOffset")
        symbolizer.update({"offset": [offsetX, offsetY],
                           "anchor": anchor,
                           "rotate": rotation})

    label = None
    exp = settings.getLabelExpression()
    try:
        label = _expressionConverter.convert(exp)
    except UnsupportedExpressionException as e:
        _warnings.append(str(e))

    if label is None:
        label = ''  # default to empty string if expression is bad

    symbolizer.update({"color": color,
                       "font": font,
                       "label": label,
                       "size": size})
    # background (i.e. road shields)
    addBackground(textFormat, symbolizer)

    result = {"symbolizers": [symbolizer], "name": name}
    if filter is not None:
        result["filter"] = filter

    # labels rendering scale-based visibility
    scale = None
    if settings.scaleVisibility:
        scale = {"max": settings.minimumScale, "min": settings.maximumScale}
    elif hasattr(labeling, 'dependsOnScale') and labeling.dependsOnScale():
        scale = processRuleScale(labeling)
    elif layer.hasScaleBasedVisibility():
        scale = processRuleScale(layer)
        
    if scale:
        result["scaleDenominator"] = scale

    return result


def addBackground(textFormat, symbolizer):
    background = textFormat.background()
    if not background.enabled():
        return
    background_type = background.type()
    background_sizeType = background.sizeType()
    background_size = background.size()
    background_sizeUnit = background.sizeUnit()

    shapeType = "square"
    if background_type == QgsTextBackgroundSettings.ShapeType.ShapeRectangle:
        shapeType = "rectangle"
    if background_type == QgsTextBackgroundSettings.ShapeType.ShapeSquare:
        shapeType = "square"
    if background_type == QgsTextBackgroundSettings.ShapeType.ShapeEllipse:
        shapeType = "elipse"
    if background_type == QgsTextBackgroundSettings.ShapeType.ShapeCircle:
        shapeType = "circle"

    sizeType = "buffer"
    if background_sizeType == QgsTextBackgroundSettings.SizeType.SizeFixed:
        sizeType = "fixed"

    sizeUnits = "MM"
    if background_sizeUnit == QgsUnitTypes.RenderUnit.RenderPixels:
        sizeUnits = "Pixel"
    if background_sizeUnit == QgsUnitTypes.RenderUnit.RenderPoints:
        sizeUnits = "Point"

    sizeX = _handleUnits(background_size.width(), sizeUnits)
    sizeY = _handleUnits(background_size.height(), sizeUnits)

    fillColor = _toHexColorQColor(background.fillColor())
    strokeColor = _toHexColorQColor(background.strokeColor())
    opacity = background.opacity()

    result = {"shapeType": shapeType,
              "sizeType": sizeType,
              "sizeX": sizeX,
              "sizeY": sizeY,
              "fillColor": fillColor,
              "strokeColor": strokeColor,
              "opacity": opacity}

    symbolizer["background"] = result


# AND two expressions together (handle nulls)
def andFilter(f1, f2):
    if f1 is None and f2 is None:
        return None
    if f1 is None:
        return f2
    if f2 is None:
        return f1
    return ['And', f1, f2]


def processRule(rule, filters=None, layerOpacity=1, layer=None):
    ruledefs = []

    if rule.isElse():
        filt = "ELSE"
    else:
        filt = andFilter(processExpression(rule.filterExpression()), filters)

    for subrule in rule.children():
        if subrule.active():
            ruledefs.extend(processRule(subrule, filt, layerOpacity, layer))

    symbol = rule.symbol()
    if symbol is not None:
        symbolizers = _createSymbolizers(rule.symbol(), layerOpacity)
        name = rule.label()
        ruledef = {"name": name,
                   "symbolizers": symbolizers}
        if filt is not None:
            ruledef["filter"] = filt
        scaleRule = getScaleRule(rule, layer)
        if scaleRule is not None:
            scale = processRuleScale(scaleRule)
            ruledef["scaleDenominator"] = scale
        ruledefs.append(ruledef)

    return ruledefs


# note - this will usually return a Rule, but could return the layer
#  they both have the same .minimumScale() functions, so this isn't a problem.
def getScaleRule(rule, layer):
    if rule is None:
        if layer.hasScaleBasedVisibility():
            return layer
        return None
    if rule.dependsOnScale():
        return rule
    return getScaleRule(rule.parent(), layer)


def processRuleScale(rule):
    # in QGIS, minimumScale() is a large number (i.e. very zoomed out).
    # however, these are backwards if you think in terms of RF.
    return {"max": rule.minimumScale(),
            "min": rule.maximumScale()}


def processExpression(expstr):
    try:
        if expstr:
            exp = QgsExpression(expstr)
            return _expressionConverter.convert(exp)
        else:
            return None
    except UnsupportedExpressionException as e:
        _warnings.append(str(e))
        return None


def _cast(v):
    if isinstance(v, str):
        try:
            return float(v)
        except:
            return v
    else:
        return v


def _handleUnits(value, units, propertyConstant=None):
    if propertyConstant == QgsSymbolLayer.Property.PropertyStrokeWidth and str(value) in ["0", "0.0"]:
        return 1  # hairline width
    if units in ["Point", QgsUnitTypes.RenderUnit.RenderPoints]:
        if isinstance(value, list):
            return ["Mul", POINT2PIXEL, value]
        else:
            return float(value) * POINT2PIXEL
    if units in ["MM", QgsUnitTypes.RenderUnit.RenderMillimeters]:
        if isinstance(value, list):
            return ["Mul", MM2PIXEL, value]
        else:
            return float(value) * MM2PIXEL
    elif units == "RenderMetersInMapUnits":
        if isinstance(value, list):
            _warnings.append(
                "Cannot render in map units when using a data-defined size value: '%s'" % str(value))
            return value
        else:
            return str(value) + "m"
    elif units in ["Pixel", QgsUnitTypes.RenderUnit.RenderMillimeters]:
        return value
    else:
        _warnings.append("Unsupported units: '%s'" % units)
        return value


def _labelingProperty(settings, obj, name, propertyConstant=-1):
    ddProps = settings.dataDefinedProperties()
    v = None
    if propertyConstant in ddProps.propertyKeys():
        v = processExpression(ddProps.property(
            propertyConstant).asExpression())  # could return None if expression is bad
    if v is None:
        v = getattr(obj or settings, name)
        try:
            v = v()
        except:
            pass
    if v is None:
        return ''
    return _cast(v)


def _symbolProperty(symbolLayer, name, propertyConstant=-1, default=0):
    ddProps = symbolLayer.dataDefinedProperties()
    if propertyConstant in ddProps.propertyKeys():
        v = processExpression(ddProps.property(
            propertyConstant).asExpression()) or ""
    else:
        v = symbolLayer.properties().get(name, default)

    units = symbolLayer.properties().get(name + "_unit")
    if units is not None:
        v = _handleUnits(v, units, propertyConstant)
    return _cast(v)


def _toHexColorQColor(qcolor):
    try:
        return '#%02x%02x%02x' % (qcolor.red(), qcolor.green(), qcolor.blue())
    except:
        return qcolor


def _rgba(color) -> tuple:
    """ Returns an R,G,B,A integer tuple from a symbolizer color property. May raise exceptions! """
    # Color should be a string like '50,95,40,255' (RGBA), but in later QGIS versions, it may be
    # '50,95,40,255,rgb:0.19607843137254902,0.37254901960784315,0.15686274509803921,1'
    values = str(color).split(",")
    return tuple(map(int, values[:4]))


def _toHexColor(color) -> str:
    try:
        r, g, b, a = _rgba(color)
        return '#%02x%02x%02x' % (int(r), int(g), int(b))
    except:
        return color


def _opacity(color) -> float:
    try:
        a = _rgba(color)[-1]
        return float(a) / 255.
    except:
        return 1.0


def _createSymbolizers(symbol, layerOpacity=1):
    opacity = symbol.opacity() * layerOpacity
    symbolizers = []

    for indx in range(len(symbol.symbolLayers())):
        sl = symbol.symbolLayers()[indx]
        symbolizer = _createSymbolizer(sl, opacity)
        if symbolizer is not None:
            if not isinstance(symbolizer, list):
                symbolizer = [symbolizer]
            for s in symbolizer:
                s["Z"] = sl.renderingPass()
                symbolizers.append(s)

    return symbolizers


def _createSymbolizer(sl, opacity):
    symbolizer = None
    if isinstance(sl, QgsSimpleMarkerSymbolLayer):
        symbolizer = _simpleMarkerSymbolizer(sl, opacity)
    elif isinstance(sl, QgsSimpleLineSymbolLayer):
        symbolizer = _lineSymbolizer(sl, opacity)
    elif isinstance(sl, QgsMarkerLineSymbolLayer):
        symbolizer = _markerLineSymbolizer(sl, opacity)
    elif isinstance(sl, QgsSimpleFillSymbolLayer):
        symbolizer = _simpleFillSymbolizer(sl, opacity)
    elif isinstance(sl, QgsPointPatternFillSymbolLayer):
        symbolizer = _pointPatternFillSymbolizer(sl, opacity)
    elif isinstance(sl, QgsLinePatternFillSymbolLayer):
        symbolizer = _linePatternFillSymbolizer(sl, opacity)
    elif isinstance(sl, QgsSvgMarkerSymbolLayer):
        symbolizer = _svgMarkerSymbolizer(sl, opacity)
    elif type(sl) is QgsRasterMarkerSymbolLayer:  # only support this exact class but no derived classes (e.g. QgsAnimatedMarkerSymbolLayer)
        symbolizer = _rasterImageMarkerSymbolizer(sl, opacity)
    elif isinstance(sl, QgsGeometryGeneratorSymbolLayer):
        symbolizer = _geomGeneratorSymbolizer(sl, opacity)
    elif isinstance(sl, QgsFontMarkerSymbolLayer):
        symbolizer = _fontMarkerSymbolizer(sl, opacity)

    if symbolizer is None:
        _warnings.append("Symbol layer type not supported: '%s'" %
                         sl.__class__.__name__)
    return symbolizer


def _fontMarkerSymbolizer(sl, opacity):
    symbolizer = _basePointSimbolizer(sl, opacity)
    color = _toHexColor(sl.properties()["color"])
    fontFamily = _symbolProperty(sl, "font")
    character = str(_symbolProperty(
        sl, "chr", QgsSymbolLayer.Property.PropertyCharacter))
    size = _symbolProperty(sl, "size", QgsSymbolLayer.Property.PropertySize)
    if len(character) == 1:
        hexcode = hex(ord(character))
        name = "ttf://%s#%s" % (fontFamily, hexcode)
        symbolizer.update({"kind": "Mark",
                           "color": color,
                           "wellKnownName": name,
                           "size": ["Div", size, 2]
                           # we use half of the size, since QGIS uses this as radius, not char height
                           })
    else:
        symbolizer.update({"kind": "Text",
                           "size": size,
                           "label": character,
                           "font": fontFamily,
                           "color": color})

    return symbolizer


def _lineSymbolizer(sl, opacity):
    props = sl.properties()
    color = _toHexColor(props["line_color"])
    strokeOpacity = _opacity(props["line_color"])
    width = _symbolProperty(
        sl, "line_width", QgsSymbolLayer.Property.PropertyStrokeWidth)
    lineStyle = _symbolProperty(
        sl, "line_style", QgsSymbolLayer.Property.PropertyStrokeStyle)
    cap = _symbolProperty(sl, "capstyle", QgsSymbolLayer.Property.PropertyCapStyle)
    cap = "butt" if cap == "flat" else cap
    join = _symbolProperty(sl, "joinstyle", QgsSymbolLayer.Property.PropertyJoinStyle)
    offset = _symbolProperty(sl, "offset", QgsSymbolLayer.Property.PropertyOffset)
    symbolizer = {"kind": "Line",
                  "color": color,
                  "opacity": opacity * strokeOpacity,
                  "width": width,
                  "perpendicularOffset": offset,
                  "cap": cap,
                  "join": join
                  }
    if lineStyle =='dot':
        symbolizer["dasharray"] = "3 5"
    elif lineStyle =='dash':
        symbolizer["dasharray"] = "8 5"
    elif lineStyle =='dash dot':
        symbolizer["dasharray"] = "8 5 3 5"
    elif lineStyle =='dash dot dot':
        symbolizer["dasharray"] = "8 5 3 5 3 5"
    elif lineStyle != "solid":
        symbolizer["dasharray"] = "5 2"
    return symbolizer


def _markerLineSymbolizer(sl, opacity):
    offset = _symbolProperty(sl, "offset", QgsSymbolLayer.Property.PropertyOffset)
    symbolizer = {"kind": "Line",
                  "opacity": opacity,
                  "perpendicularOffset": offset}
    subSymbolizers = []
    for subsl in sl.subSymbol().symbolLayers():
        subSymbolizer = _createSymbolizer(subsl, 1)
        if subSymbolizer is not None:
            subSymbolizers.append(subSymbolizer)
    if subSymbolizers:
        interval = _symbolProperty(
            sl, "interval", QgsSymbolLayer.Property.PropertyInterval)
        offsetAlong = _symbolProperty(
            sl, "offset_along_line", QgsSymbolLayer.Property.PropertyOffsetAlongLine)
        symbolizer["graphicStroke"] = subSymbolizers
        symbolizer["graphicStrokeInterval"] = interval
        symbolizer["graphicStrokeOffset"] = offsetAlong

    return symbolizer


def _geomGeneratorSymbolizer(sl, opacity):
    subSymbol = sl.subSymbol()
    symbolizers = _createSymbolizers(subSymbol, opacity)
    geomExp = sl.geometryExpression()
    geom = processExpression(geomExp)
    for symbolizer in symbolizers:
        symbolizer["Geometry"] = geom
    return symbolizers


def _svgMarkerSymbolizer(sl, opacity):
    marker = _basePointSimbolizer(sl, opacity)
    color = _toHexColor(sl.properties()["color"])
    marker["color"] = color
    svg = _markGraphic(sl)
    marker.update(svg)
    return marker


def _rasterImageMarkerSymbolizer(sl, opacity):
    marker = _basePointSimbolizer(sl, opacity)
    img = _iconGraphic(sl)
    marker.update(img)
    return marker


def _simpleMarkerSymbolizer(sl, opacity):
    marker = _basePointSimbolizer(sl, opacity)
    mark = _markGraphic(sl)
    marker.update(mark)
    return marker


def _basePointSimbolizer(sl, opacity):
    props = sl.properties()
    rotation = _symbolProperty(sl, "angle", QgsSymbolLayer.Property.PropertyAngle)
    x, y = sl.offset().x(), sl.offset().y()

    symbolizer = {
        "opacity": opacity,
        "rotate": rotation
    }

    if x or y:
        symbolizer["offset"] = [x, y]
        # exp = "translate($geometry, %s,%s)" % (str(x), str(y))
        # symbolizer["geometry"] = processExpression(exp)

    return symbolizer


def _createSprite(sl):
    sl = sl.clone()
    if hasattr(sl, "setSize"):
        newSymbol = QgsMarkerSymbol()
        newSymbol.appendSymbolLayer(sl)
        newSymbol.deleteSymbolLayer(0)
        newSymbol.setSizeUnit(QgsUnitTypes.RenderPixels)

        sl.setSize(SPRITE_SIZE)
        img = newSymbol.asImage(QSize(int(sl.size()), int(sl.size())))
        sl.setSize(SPRITE_SIZE * 2)
        img2x = newSymbol.asImage(QSize(int(sl.size()), int(sl.size())))
    elif hasattr(sl, "toTiledPatternImage"):  # QgsFillSymbolLayer
        img = sl.toTiledPatternImage()
        img2x = sl.toTiledPatternImage().scaled(img.width()*2, img.height()*2)

    return {"image": img, "image2x": img2x}

def _markLineFillGraphic(sl):
    global _usedSprites
    
    props = sl.properties()
    opacity = _opacity(props["color"])
    spriteName = ""
    name = SHAPE_NAMES["line"]
    outlineStyle = _symbolProperty(
        sl, "outline_style", QgsSymbolLayer.PropertyStrokeStyle)
    spriteName = name.replace(":", "_").replace("/", "_")
    # We might need to generate the same sprite in multiple colors, append color to spritename
    col = sl.color()
    spriteName += f"{col.red()}_{col.green()}_{col.blue()}_{col.alpha()}"
   
    _usedSprites[spriteName] = _createSprite(sl)

    linefill = {"strokeOpacity": opacity}
    if spriteName != "":
        linefill["spriteName"] = spriteName

    if outlineStyle =='dot':
        linefill["outlineDasharray"] = "3 5"
    elif outlineStyle =='dash':
        linefill["outlineDasharray"] = "8 5"
    elif outlineStyle =='dash dot':
        linefill["outlineDasharray"] = "8 5 3 5"
    elif outlineStyle =='dash dot dot':
        linefill["outlineDasharray"] = "8 5 3 5 3 5"
    elif outlineStyle not in  ["solid", "no"]:
        linefill["outlineDasharray"] = "5 2"

    return linefill


def _markGraphic(sl):
    global _usedIcons, _usedSprites

    props = sl.properties()
    size = _symbolProperty(sl, "size", QgsSymbolLayer.Property.PropertySize)
    color = _toHexColor(props["color"])
    outlineColor = _toHexColor(props["outline_color"])
    outlineWidth = _symbolProperty(
        sl, "outline_width", QgsSymbolLayer.Property.PropertyStrokeWidth)
    fillOpacity = _opacity(props["color"])
    strokeOpacity = _opacity(props["outline_color"])
    spriteName = ""
    try:
        path = sl.path()
        name = os.path.basename(path)
        spriteName = name.replace(":", "_").replace("/", "_")
        _usedIcons[sl.path()] = sl
        _usedSprites[spriteName] = _createSprite(sl)
        outlineStyle = "solid"
        size = _symbolProperty(sl, "size", QgsSymbolLayer.Property.PropertyWidth)
    except:
        name = props["name"]
        name = SHAPE_NAMES.get(name, name.replace("_", ""))
        outlineStyle = _symbolProperty(
            sl, "outline_style", QgsSymbolLayer.Property.PropertyStrokeStyle)
        if outlineStyle == "no":
            outlineWidth = 0
        spriteName = name.replace(":", "_").replace("/", "_")
        _usedSprites[spriteName] = _createSprite(sl)

    mark = {"kind": "Mark",
            "color": color,
            "wellKnownName": name,
            "size": size,
            "strokeColor": outlineColor,
            "strokeWidth": outlineWidth,
            "strokeOpacity": strokeOpacity,
            "fillOpacity": fillOpacity
            }
    if spriteName != "":
        mark["spriteName"] = spriteName

    if outlineStyle =='dot':
        mark["outlineDasharray"] = "3 5"
    elif outlineStyle =='dash':
        mark["outlineDasharray"] = "8 5"
    elif outlineStyle =='dash dot':
        mark["outlineDasharray"] = "8 5 3 5"
    elif outlineStyle =='dash dot dot':
        mark["outlineDasharray"] = "8 5 3 5 3 5"
    elif outlineStyle not in  ["solid", "no"]:
        mark["outlineDasharray"] = "5 2"

    return mark


def _markFillPattern(shape, color, size=FIXED_PATTERN_SIZE, strokeWidth=1, rotation=0):
    shape = SHAPE_NAMES.get(shape, shape)
    return {"kind": "Mark",
            "color": color,
            "wellKnownName": shape,
            "size": size,
            "strokeColor": color,
            "strokeWidth": strokeWidth,
            "rotate": rotation
            }


def _iconGraphic(sl, color=None):
    global _usedIcons
    _usedIcons[sl.path()] = sl
    path = os.path.basename(sl.path())
    size = _symbolProperty(sl, "size", QgsSymbolLayer.Property.PropertySize)
    return {"kind": "Icon",
            "color": color,
            "image": path,
            "size": size,
            }


def _baseFillSymbolizer(sl, opacity):
    return {"kind": "Fill",
            "opacity": opacity}


def _linePatternFillSymbolizer(sl, opacity):
    symbolizer = _baseFillSymbolizer(sl, opacity)
    color = sl.color().name()
    strokeWidth = _symbolProperty(sl, "line_width")
    size = _symbolProperty(sl, "distance", QgsSymbolLayer.Property.PropertyLineDistance)
    rotation = _symbolProperty(sl, "angle", QgsSymbolLayer.Property.PropertyLineAngle)
    marker = _hatchMarkerForAngle(rotation)
    subSymbolizer = _markFillPattern(marker, color, size, strokeWidth, 0)
    subSymbolizer.update(_markLineFillGraphic(sl))
    symbolizer["graphicFill"] = [subSymbolizer]
    return symbolizer


def _hatchMarkerForAngle(angle):
    quadrant = math.floor(((angle + 22.5) % 180) / 45.)
    return ["shape://vertline", "shape://slash", "shape://horline", "shape://backslash"][quadrant]


def _pointPatternFillSymbolizer(sl, opacity):
    symbolizer = _baseFillSymbolizer(sl, opacity)
    subSymbolizers = []
    for subsl in sl.subSymbol().symbolLayers():
        subSymbolizer = _createSymbolizer(subsl, 1)
        if subSymbolizers is not None:
            subSymbolizers.append(subSymbolizer)
    if subSymbolizers:
        distancex = _symbolProperty(
            sl, "distance_x", QgsSymbolLayer.Property.PropertyDistanceX)
        distancey = _symbolProperty(
            sl, "distance_y", QgsSymbolLayer.Property.PropertyDistanceY)
        symbolizer["graphicFill"] = subSymbolizers
        distancex = ["Div", distancex, 2] if isinstance(
            distancex, list) else distancex / 2.0
        distancey = ["Div", distancex, 2] if isinstance(
            distancey, list) else distancey / 2.0
        symbolizer["graphicFillMarginX"] = distancex
        symbolizer["graphicFillMarginY"] = distancey

    return symbolizer


def _simpleFillSymbolizer(sl, opacity):
    props = sl.properties()
    style = props["style"]

    symbolizer = _baseFillSymbolizer(sl, opacity)

    if style != "no":
        color = _toHexColor(props["color"])
        fillOpacity = _opacity(props["color"])
        if style == "solid":
            symbolizer["color"] = color
            symbolizer["fillOpacity"] = fillOpacity
        else:
            style = PATTERN_NAMES.get(style, style)
            marker = _markFillPattern(style, color)
            symbolizer["graphicFill"] = [marker]
            symbolizer["graphicFillDistanceX"] = FIXED_PATTERN_SIZE / 2.0
            symbolizer["graphicFillDistanceY"] = FIXED_PATTERN_SIZE / 2.0

    outlineColor = _toHexColor(props["outline_color"])
    outlineOpacity = _opacity(props["outline_color"])
    outlineStyle = _symbolProperty(
        sl, "outline_style", QgsSymbolLayer.Property.PropertyStrokeStyle)
    join = _symbolProperty(sl, "joinstyle", QgsSymbolLayer.Property.PropertyJoinStyle)
    if outlineStyle != "no":
        outlineWidth = _symbolProperty(
            sl, "outline_width", QgsSymbolLayer.Property.PropertyStrokeWidth)
        symbolizer.update({"outlineColor": outlineColor,
                           "outlineWidth": outlineWidth,
                           "outlineOpacity": outlineOpacity,
                           "join": join})
    if outlineStyle =='dot':
        symbolizer["outlineDasharray"] = "3 5"
    elif outlineStyle =='dash':
        symbolizer["outlineDasharray"] = "8 5"
    elif outlineStyle =='dash dot':
        symbolizer["outlineDasharray"] = "8 5 3 5"
    elif outlineStyle =='dash dot dot':
        symbolizer["outlineDasharray"] = "8 5 3 5 3 5"
    elif outlineStyle not in  ["solid", "no"]:
        symbolizer["outlineDasharray"] = "5 2"

    x, y = sl.offset().x(), sl.offset().y()
    if x or y:
        symbolizer["offset"] = [x, y]
        # symbolizer["geometry"] = processExpression("translate(%s,%s)" % (str(x), str(y)))

    return symbolizer


def saveSymbolLayerSprite(symbolLayer):
    sl = symbolLayer.clone()
    if isinstance(sl, QgsSVGFillSymbolLayer):
        patternWidth = sl.patternWidth()
        color = sl.svgFillColor()
        outlineColor = sl.svgOutlineColor()
        sl = QgsSvgMarkerSymbolLayer(sl.svgFilePath())
        sl.setFillColor(color)
        sl.setOutlineColor(outlineColor)
        sl.setSize(patternWidth)
        sl.setOutputUnit(QgsSymbol.Pixel)
    sl2x = sl.clone()
    try:
        sl.setSize(64)
        sl2x.setSize(int(sl.size()) * 2)
    except AttributeError:
        return None, None
    newSymbol = QgsMarkerSymbol()
    newSymbol.appendSymbolLayer(sl)
    newSymbol.deleteSymbolLayer(0)
    newSymbol.setSizeUnit(QgsUnitTypes.RenderUnit.RenderPixels)

    newSymbol2x = QgsMarkerSymbol()
    newSymbol2x.appendSymbolLayer(sl2x)
    newSymbol2x.deleteSymbolLayer(0)
    newSymbol2x.setSizeUnit(QgsUnitTypes.RenderUnit.RenderPixels)

    img = newSymbol.asImage(QSize(int(sl.size()), int(sl.size())))
    img2x = newSymbol2x.asImage(QSize(int(sl2x.size()), int(sl2x.size())))
    return img, img2x


def initSpriteSheet(width, height):
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor(Qt.GlobalColor.transparent))
    img2x = QImage(width * 2, height * 2, QImage.Format.Format_ARGB32)
    img2x.fill(QColor(Qt.GlobalColor.transparent))
    painter = QPainter(img)
    painter.begin(img)
    painter2x = QPainter(img2x)
    painter2x.begin(img2x)
    spritesheet = {NO_ICON: {"width": 0,
                             "height": 0,
                             "x": 0,
                             "y": 0,
                             "pixelRatio": 1}}
    spritesheet2x = {NO_ICON: {"width": 0,
                               "height": 0,
                               "x": 0,
                               "y": 0,
                               "pixelRatio": 1}}
    return img, img2x, painter, painter2x, spritesheet, spritesheet2x


def drawSpriteSheet(name, painter, painter2x, spritesheet, spritesheet2x, x, s, s2x):
    painter.drawImage(x, 0, s)
    painter2x.drawImage(x * 2, 0, s2x)
    spritesheet[name] = {"width": s.width(),
                         "height": s.height(),
                         "x": x,
                         "y": 0,
                         "pixelRatio": 1}
    spritesheet2x[name] = {"width": s2x.width(),
                           "height": s2x.height(),
                           "x": x * 2,
                           "y": 0,
                           "pixelRatio": 2}


def writeSpritesOutput(folder, img, img2x, spritesheet, spritesheet2x):
    img.save(os.path.join(folder, "spriteSheet.png"))
    img2x.save(os.path.join(folder, "spriteSheet@2x.png"))
    with open(os.path.join(folder, "spriteSheet.json"), 'w') as f:
        json.dump(spritesheet, f)
    with open(os.path.join(folder, "spriteSheet@2x.json"), 'w') as f:
        json.dump(spritesheet2x, f)


def saveSpritesSheet(icons, folder):
    sprites = {}
    for iconPath, sl in icons.items():
        iconName = os.path.splitext(os.path.basename(iconPath))[0]
        sprites[iconName] = saveSymbolLayerSprite(sl)
    if not sprites:
        return
    height = max([s.height() for s, s2x in sprites.values()])
    width = sum([s.width() for s, s2x in sprites.values()])
    img, img2x, painter, painter2x, spritesheet, spritesheet2x = initSpriteSheet(width, height)
    x = 0
    for name, _sprites in sprites.items():
        s, s2x = _sprites
        drawSpriteSheet(name, painter, painter2x, spritesheet, spritesheet2x, x, s, s2x)
        x += s.width()
    painter.end()
    painter2x.end()
    writeSpritesOutput(folder, img, img2x, spritesheet, spritesheet2x)
