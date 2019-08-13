import os
import zipfile
import json
from bridgestyle import qgis
from bridgestyle import sld
from bridgestyle import mapboxgl

def layerStyleAsSld(layer):
    geostyler, icons, warnings = qgis.togeostyler.convert(layer)
    sldString, sldWarnings = sld.fromgeostyler.convert(geostyler)        
    warnings.extend(sldWarnings)
    return sldString, icons, warnings

def saveLayerStyleAsSld(layer, filename):
    sldstring, icons, warnings = layerStyleAsSld(layer)       
    with open(filename, "w") as f:
        f.write(sldstring)
    return warnings

def saveLayerStyleAsZippedSld(layer, filename):
    sldstring, icons, warnings = layerStyleAsSld(layer)
    z = zipfile.ZipFile(filename, "w")
    for icon in icons.keys():
        z.write(icon, os.path.basename(icon))
    z.writestr(layer.name() + ".sld", sldstring)
    z.close()
    return warnings

def layerStyleAsMapbox(layer):
    geostyler, icons, warnings = qgis.togeostyler.convert(layer)
    mbox, mbWarnings = mapboxgl.fromgeostyler.convert(geostyler)
    warnings.extend(mbWarnings)
    return mbox, icons, warnings

def layerStyleAsMapboxFolder(layer, folder):
    geostyler, icons, warnings = qgis.togeostyler.convert(layer)
    mbox, mbWarnings = mapboxgl.fromgeostyler.convert(geostyler)    
    filename = os.path.join(folder, "style.mapbox")
    with open(filename, "w") as f:
        f.write(mbox)
    saveSpritesSheet(icons, folder)
    return warnings
    
NO_ICON = "no_icon"

def saveSymbolLayerSprite(symbolLayer):
    sl = symbolLayer.clone()
    if isinstance(sl, QgsSVGFillSymbolLayer):
        patternWidth = sl.patternWidth()
        color = sl.svgFillColor()
        outlineColor = sl.svgOutlineColor()
        sl = QgsSvgMarkerSymbolLayerV2(sl.svgFilePath())
        sl.setFillColor(color)
        sl.setOutlineColor(outlineColor)
        sl.setSize(patternWidth)
        sl.setOutputUnit(QgsSymbolV2.Pixel)
    sl2x = sl.clone()
    try:
        sl2x.setSize(sl2x.size() * 2)
    except AttributeError:
        return None, None
    newSymbol = QgsMarkerSymbolV2()
    newSymbol.appendSymbolLayer(sl)
    newSymbol.deleteSymbolLayer(0)
    newSymbol2x = QgsMarkerSymbolV2()
    newSymbol2x.appendSymbolLayer(sl2x)
    newSymbol2x.deleteSymbolLayer(0)
    img = newSymbol.asImage(QSize(sl.size(), sl.size()))
    img2x = newSymbol2x.asImage(QSize(sl2x.size(), sl2x.size()))
    return img, img2x

def saveSpritesSheet(icons, folder):
    sprites = {}
    for iconPath, sl in icons:
        iconName = os.path.splitext(os.path.basename(iconPath))[0]
        sprites[iconName] = saveSymbolLayerSprite(sl)
    if sprites:
        height = max([s.height() for s,s2x in sprites.values()])
        width = sum([s.width() for s,s2x in sprites.values()])
        img = QImage(width, height, QImage.Format_ARGB32)
        img.fill(QColor(Qt.transparent))
        img2x = QImage(width * 2, height * 2, QImage.Format_ARGB32)
        img2x.fill(QColor(Qt.transparent))
        painter = QPainter(img)
        painter.begin(img)
        painter2x = QPainter(img2x)
        painter2x.begin(img2x)
        spritesheet = {NO_ICON:{"width": 0,
                             "height": 0,
                             "x": 0,
                             "y": 0,
                             "pixelRatio": 1}}
        spritesheet2x = {NO_ICON:{"width": 0,
                             "height": 0,
                             "x": 0,
                             "y": 0,
                             "pixelRatio": 1}}
        x = 0
        for name, sprites in sprites.iteritems():
            s, s2x = sprites
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
            x += s.width()
        painter.end()
        painter2x.end()
        img.save(os.path.join(folder, "spriteSheet.png"))
        img2x.save(os.path.join(folder, "spriteSheet@2x.png"))
        with open(os.path.join(folder, "spriteSheet.json"), 'w') as f:
            json.dump(spritesheet, f)
        with open(os.path.join(folder, "spriteSheet@2x.json"), 'w') as f:
            json.dump(spritesheet2x, f)
