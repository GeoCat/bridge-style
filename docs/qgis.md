# QGIS supported functionality

The following elements are supported and correctly exported to the Geostyler format - and from there to any other format, if it also supports that kind of element.

## Renderers

Most renderers and elements are supported. Here is a short list of the main ones that are **not** supported yet:

- Shapeburst fills
- Point placement
- Point clusters
- Heatmaps
- Vector field markers
- Line pattern polygon fills (use point pattern fills with lines or crosses as markers for a similar effect)

You can find a complete list of supported renderers and elements [here](https://geocat.github.io/qgis-bridge-plugin/latest/supported_symbology.htm).

## Geometry generators

Geometry generators are supported, although not all geometry functions are available (see [Expressions](#expressions)).


## Size units

Size values can be applied in millimeters, pixels or real world meters. In this last case, only constant values are allowed (no expressions).

However, note that it's generally safer to use pixels instead of millimeters (the default unit in QGIS), since pixels (px) is the assumed unit for "screen formats" like SLD, which means that no unit conversion is needed. 

## Expressions

Expressions are supported wherever they are available in QGIS. However, not all functions and operators are supported. See [here](https://geocat.github.io/qgis-bridge-plugin/latest/supported_symbology.html#expressions) for a list of supported ones.

There are two exceptions to this:

- Expressions are never supported in color values.
- Expressions are not supported for size measurements, when those measures are not expressed in pixels or mm (i.e. if you are using map units or real world meters for a size that changes with the current map scale).