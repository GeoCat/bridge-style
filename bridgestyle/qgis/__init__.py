import os
import zipfile
from shutil import copyfile

from .. import mapboxgl
from .. import mapserver
from .. import sld
from . import fromgeostyler
from . import togeostyler


def layerStyleAsSld(layer):
    geostyler, icons, sprites, warnings = togeostyler.convert(layer)
    sldString, sldWarnings = sld.fromgeostyler.convert(geostyler)
    warnings.extend(sldWarnings)
    return sldString, icons, warnings


def saveLayerStyleAsSld(layer, filename):
    sldstring, icons, warnings = layerStyleAsSld(layer)
    with open(filename, "w", encoding='utf-8') as f:
        f.write(sldstring)
    return warnings


def saveLayerStyleAsZippedSld(layer, filename):
    sldstring, icons, warnings = layerStyleAsSld(layer)
    z = zipfile.ZipFile(filename, "w")
    for icon in icons.keys():
        if icon:
            z.write(icon, os.path.basename(icon))
    z.writestr(layer.name() + ".sld", sldstring)
    z.close()
    return warnings


def layerStyleAsMapbox(layer):
    geostyler, icons, sprites, warnings = togeostyler.convert(layer)
    mbox, mbWarnings = mapboxgl.fromgeostyler.convert(geostyler)
    warnings.extend(mbWarnings)
    return mbox, icons, warnings


def layerStyleAsMapboxFolder(layer, folder):
    geostyler, icons, sprites, warnings = togeostyler.convert(layer)
    mbox, mbWarnings = mapboxgl.fromgeostyler.convert(geostyler)
    filename = os.path.join(folder, "style.mapbox")
    with open(filename, "w", encoding='utf-8') as f:
        f.write(mbox)
    # saveSpritesSheet(icons, folder)
    return warnings


def layerStyleAsMapfile(layer):
    geostyler, icons, sprites, warnings = togeostyler.convert(layer)
    mserver, mserverSymbols, msWarnings = mapserver.fromgeostyler.convert(geostyler)
    warnings.extend(msWarnings)
    return mserver, mserverSymbols, icons, warnings


def layerStyleAsMapfileFolder(layer, folder, additional=None):
    geostyler, icons, sprites, warnings = togeostyler.convert(layer)
    mserverDict, mserverSymbolsDict, msWarnings = mapserver.fromgeostyler.convertToDict(geostyler)
    warnings.extend(msWarnings)
    additional = additional or {}
    mserverDict["LAYER"].update(additional)
    mapfile = mapserver.fromgeostyler.convertDictToMapfile(mserverDict)
    symbols = mapserver.fromgeostyler.convertDictToMapfile({"SYMBOLS": mserverSymbolsDict})
    filename = os.path.join(folder, layer.name() + ".txt")
    with open(filename, "w", encoding='utf-8') as f:
        f.write(mapfile)
    filename = os.path.join(folder, layer.name() + "_symbols.txt")
    with open(filename, "w", encoding='utf-8') as f:
        f.write(symbols)
    for icon in icons:
        dst = os.path.join(folder, os.path.basename(icon))
        copyfile(icon, dst)
    return warnings
