# bridge-style

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md) [![CLA assistant](https://cla-assistant.io/readme/badge/geocat/bridge-style)](https://cla-assistant.io/geocat/bridge-style)

`bridgestyle` is a Python library that allows you to convert cartographic symbology formats.  
It uses [GeoStyler](https://geostyler.org/) (JSON) as an intermediate format, and follows a two-step approach:

1. Convert from the supported original format into the GeoStyler format. 
2. Convert from GeoStyler into a supported destination format.


## Supported formats

In the table below you'll find the symbology formats that can be converted from one to another. 
The *first column* shows the *source* formats, and the *first row* shows the *destination* formats:

|                         | QGIS (QML) | ArcGIS Pro (CIM) | GeoStyler | SLD (GeoServer) | MapLibre GL JS | Mapfile (MapServer) |
|-------------------------|------------|------------------|-----------|-----------------|----------------|---------------------|
| **QGIS (QML)**          | n/a        | ✅                | ✅         | ✅               | ✅              | ✅                   |
| **ArcGIS Pro (CIM)**    | ❌          | n/a              | ✅         | ✅               | ✅              | ✅                   |
| **GeoStyler**           | ❌          | ❌                | n/a       | ✅               | ✅              | ✅                   |
| **SLD (GeoServer)**     | ❌          | ❌                | ❌         | n/a             | ❌              | ❌                   |
| **MapLibre GL JS**      | ❌          | ❌                | ❌         | ❌               | n/a            | ❌                   |
| **Mapfile (MapServer)** | ❌          | ❌                | ❌         | ❌               | ❌              | n/a                 |

As you can see, the current main goal of this library is:
- to convert QGIS symbology via GeoStyler into all other formats  
  *OR*
- to convert ArcGIS Pro `.lyrx` files via GeoStyler into all other formats **except QGIS**.

> ⚠️ **WARNING** ⚠️  
> *Converting from QGIS symbology (QML) into something else requires the QGIS Python API. In that case, you can only use this library in a QGIS runtime environment.*

ArcGIS Pro users can create a Python toolbox that utilizes `bridgestyle` either directly (requires installation so you can import it) or by calling [`style2style`](#style2style) using `subprocess` for example.

### Limitations
Because symbology formats are very different and the software they are intended for have different capabilities, not all symbology features can be converted between formats.

To find out what the *exact* limitations are, you will have to check the code... 😥

However, there is a [document for QGIS](https://github.com/GeoCat/bridge-style/blob/master/docs/qgis.md) that lists the QGIS symbology features that are (not) supported by the GeoStyler format.
For more elaborate information, you can consult the [GeoCat Bridge for QGIS documentation](https://geocat.github.io/qgis-bridge-plugin/latest/supported_symbology.html).

If you wish to convert ArcGIS Pro `.lyrx` files into SLD, you may want to read [this document](https://github.com/GeoCat/bridge-style/blob/master/docs/arcgis.md). There are also some notes on [MapServer](https://github.com/GeoCat/bridge-style/blob/master/docs/mapserver.md).

## Installation

Since June 2025, `bridgestyle` is available on [PyPI](https://pypi.org/project/bridgestyle/), which means you can install it using [pip](https://pip.pypa.io/en/stable/).
In your active Python environment, run the following command:

```bash   
pip install bridgestyle
```

However, if you wish to use the library in QGIS, we highly recommend installing the [GeoCat Bridge for QGIS plugin](https://github.com/GeoCat/qgis-bridge-plugin) instead,
as it already includes `bridgestyle` and provides a style preview and other useful features.  
The plugin is available in the [QGIS plugin repository](https://plugins.qgis.org/plugins/geocatbridge/), and can be installed directly from the QGIS Plugin Manager.



## Usage

Here is an example how to export the symbology of a selected QGIS layer into a zip file containing an SLD style file and all the icons files (SVG, PNG, etc.) used by the layer:

```python
from bridgestyle.qgis import saveLayerStyleAsZippedSld
warnings = saveLayerStyleAsZippedSld(iface.activeLayer(), "/my/path/mystyle.zip")
```

The `warnings` variable will contain a list of strings with the issues found during the conversion.

Conversion can be performed outside QGIS, using the library as a standalone element. Each format has its own Python package, which contains two modules: `togeostyler` and `fromgeostyler`, each of them with a `convert` method to do the conversion work. It returns the converted style as a string, and a list of strings with issues found during the conversion (such as unsupported symbology elements that could not be correctly converted).

Here is an example how to convert a GeoStyler JSON file into an SLD file:

```python
from bridgestyle import sld
input_file = "/my/path/input.geostyler"
output_file = "/my/path/output.sld"

# We load the GeoStyler code from the input file
with open(input_file) as f:
    geostyler = json.load(f)

'''
We pass it to the fromgeostyler.convert method from the sld package.
There is one such module and function for each supported format, which 
takes a Python object representing the GeoStyler JSON object and returns 
a string with the style in the destination format.
'''
converted, warnings, obj = sld.fromgeostyler.convert(geostyler)

# We save the resulting string in the destination file
with open(output_file) as f:
    f.write(f)
```

### style2style

A basic command line tool (CLI) is also available. When the library is installed in your Python environment, you will have a `style2style` script available to be run in your console, with the following syntax:

```
style2style original_style_file.ext destination_style_file.ext
```

The file format is inferred from the file extension.

The example conversion shown above would be run with the console tool as follows:

```
style2style /my/path/input.geostyler /my/path/output.sld
```

## Contributing

If you would like to contribute to `bridgestyle` in any way, please read the [contributing guidelines](https://github.com/GeoCat/bridge-style/blob/master/CONTRIBUTING.md).

Some of the things you can do to help are:
- Fix bugs and issues
- Add new features (e.g. support for new formats, or add bidirectional conversion)
- Improve documentation
- Add tests
