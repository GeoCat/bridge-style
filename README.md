# bridge-style

A Python library to convert map styles between multiple formats.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)

The library uses Geostyler as intermediate format, and uses a two-step approach:

1) Converting from the original format into the Geostyler format. 

2) Converting from Geostyler into the destination format:


## Supported formats

These are the formats currently supported:

- Geostyler.

- SLD. This is mainly targeted at Geoserver users, so it makes use of Geoserver vendor options.

- Mapbox GL.

- Mapserver Mapfiles.

- ArcGIS Pro (lyrx).

Support for YSLD will be implemented soon.

The library also has support for being run from GIS applications, so it can convert from the data objects corresponding to map layer and features in those applications into Geostyler. At the moment, there is support for QGIS, and support from ArcGIS is planned an will soon be added.

So far, all formats can be exported from QGIS, but the inverse conversion is not available for all of them. 

To see which QGIS symbology features are correctly converted to Geostyler (and then supported in the rest of available formats, when possible), see [here](docs/qgis.md): 

## Example usage

Here is an example of how to export the symbology of the currently selected QGIS layer into a zip file containing an SLD style file and all the icons files (svg, png, etc) used by the layer.

```python

	from bridgestyle.qgis import saveLayerStyleAsZippedSld
	warnings = saveLayerStyleAsZippedSld(iface.activeLayer(), "/my/path/mystyle.zip")

```

The `warnings` variable will contain a list of strings with the issues found during the conversion.

Conversion can be performed outside of QGIS, just using the library as a standalone element. Each format has its own Python package, which contains two modules: `togeostyler` and `fromgeostyler`, each of them with a `convert` method to do the conversion work. It returns the converted style as a string, and a list of strings with issues found during the conversion (such as unsupported symbology elements that could not be correctly converted).

Here's, for instance, how to convert a Geostyler file into a SLD file.

```python
from bridgestyle import sld
input_file = "/my/path/input.geostyler"
output_file = "/my/path/output.sld"

#We load the geostyler code from the input file
with open(input_file) as f:
	geostyler = json.load(f)

'''
We pass it to the fromgeostyler.convert method from the sld package.
There is one such module and function for each  supported format, which 
takes a Python object representing the Geostyler json object and returns 
a string with the style in the destination format	
'''
converted, warnings, obj = sld.fromgeostyler.convert(geostyler)

#we save the resulting string in the destination file
with open(output_file) as f:
	f.write(f)
```

A command-line tools is also available. When the library is installed in your Python installation, you will have a `style2style` script available to be run in your console, with the following syntax:

```
style2style original_style_file.ext destination_style_file.ext
```

File format is infered from the file extension.

The example conversion shown above would be run with the console tool as follows:

```
style2style /my/path/input.geostyler /my/path/output.sld
```





