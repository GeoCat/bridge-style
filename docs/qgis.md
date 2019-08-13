# QGIS supported functionality

The following elements are supported and correctly exported to the Geostyler format (and from there to any other format, if it also supports that kind of element):

## Renderers

Most renderers and elements are supported. Here is a short list of the main ones not supported yet:

- Shapeburst fills
- Point placement
- Point clusters
- Heatmaps
- Vector field markers
- Line pattern polygon fills (use point pattern fills with lines or crosses as markers for a similar effect)

## Geometry generators

Geoetry generators are supported, although not all geometry functions are available (see 'Expressions')


## size units

Size values can be used in milimeters, pixels or real world meters. In this last case, expressions cannot be used, only fixed values.

Notice that it's, however, a safer option to use pixels instead of milimeters (which are the default unit in QGIS), since pixels is the assumed unit for formats like SLD, and, therefore, no conversion is needed. 

## Expressions

Expressions are supported whenever they are available in QGIS. Not all functions and operators are supported. See [here](qgisfunctions.md) for a list of supported ones.

There are two exceptions to this:

- Expressions are not supported for color values
- Expressions are not supported for size measurements, when those measures are not expressed in pixels or mm (that is, if you are using map units or real word meters for a size that changes with the current map scale)