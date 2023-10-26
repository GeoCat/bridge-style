# bridge-style

A Python library to convert map styles between multiple formats.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)

The library uses [GeoStyler](https://geostyler.org/) as an intermediate format, and uses a two-step approach:

1. Converting from the original format into the GeoStyler format. 
2. Converting from GeoStyler into a supported destination format.


## Supported formats

These are the formats currently supported:

- GeoStyler
- SLD (with GeoServer vendor options)
- MapLibre GL JS
- Mapfile (for MapServer)
- ArcGIS Pro CIM (.lyrx)

The library can also be run from GIS applications, so it can convert from the data objects corresponding to map layer and features in those applications via GeoStyler into something else. 
If you wish to use the library in QGIS, we recommend using the [QGIS Bridge](https://github.com/GeoCat/qgis-bridge-plugin) plugin. ArcGIS Pro users can create a Python toolbox that utilizes `bridgestyle` either directly (requires installation so you can import it) or by calling `style2style` (CLI) using `subprocess` for example.

So far, all formats can be exported from QGIS, but the inverse conversion is not available for all of them. The same applies to ArcGIS Pro styles (.lyrx).
To see which QGIS symbology features are correctly converted to GeoStyler and supported by the other target formats, see [this document](docs/qgis.md).

## Example usage

Here is an example of how to export the symbology of the currently selected QGIS layer into a zip file containing an SLD style file and all the icons files (SVG, PNG, etc.) used by the layer.

```python
	from bridgestyle.qgis import saveLayerStyleAsZippedSld
	warnings = saveLayerStyleAsZippedSld(iface.activeLayer(), "/my/path/mystyle.zip")
```

The `warnings` variable will contain a list of strings with the issues found during the conversion.

Conversion can be performed outside of QGIS, just using the library as a standalone element. Each format has its own Python package, which contains two modules: `togeostyler` and `fromgeostyler`, each of them with a `convert` method to do the conversion work. It returns the converted style as a string, and a list of strings with issues found during the conversion (such as unsupported symbology elements that could not be correctly converted).

Here's, for instance, how to convert a GeoStyler file into a SLD file.

```python
from bridgestyle import sld
input_file = "/my/path/input.geostyler"
output_file = "/my/path/output.sld"

# We load the GeoStyler code from the input file
with open(input_file) as f:
    geostyler = json.load(f)

'''
We pass it to the fromgeostyler.convert method from the sld package.
There is one such module and function for each  supported format, which 
takes a Python object representing the GeoStyler json object and returns 
a string with the style in the destination format	
'''
converted, warnings, obj = sld.fromgeostyler.convert(geostyler)

# We save the resulting string in the destination file
with open(output_file) as f:
    f.write(f)
```

A command line tool (CLI) is also available. When the library is installed in your Python installation, you will have a `style2style` script available to be run in your console, with the following syntax:

```
style2style original_style_file.ext destination_style_file.ext
```

The file format is inferred from the file extension.

The example conversion shown above would be run with the console tool as follows:

```
style2style /my/path/input.geostyler /my/path/output.sld
```





