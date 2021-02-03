import os
import sys
import sld
import geostyler
import mapboxgl
import arcgis

_exts = {"sld": sld, "geostyler": geostyler, "mapbox": mapboxgl, "lyrx": arcgis}


def convert(fileA, fileB):
    extA = os.path.splitext(fileA)[1][1:]
    extB = os.path.splitext(fileB)[1][1:]
    if extA not in _exts:
        print("Unsupported style type: '%s'" % extA)
        return
    if extB not in _exts:
        print("Unsupported style type: '%s'" % extB)
        return

    with open(fileA) as f:
        styleA = f.read()

    geostyler = _exts[extA].toGeostyler(styleA)
    styleB = _exts[extB].fromGeostyler(geostyler)


    with open(fileB, "w") as f:
        f.write(styleB)



if len(sys.argv) != 3:
    print(
        "Wrong number of parameters\nUsage: style2style original_style_file.ext destination_style_file.ext"
    )
else:
    convert(sys.argv[1], sys.argv[2])
