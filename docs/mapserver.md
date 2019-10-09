# Mapserver support in bridge style

Bridge-style is able to create layer definitions for [mapserver](https://mapserver.org) mapfiles. 
Use bridge-style to convert geostyler to mapfile syntax and combine the output with a mapfile 
header/footer and run it in mapserver

## Mapserver on Windows

For windows you best install [MS4W](https://www.ms4w.com). MS4W installs mapserver and apache preconfigured to instantly run.

## Mapserver on Docker

Various [prepared images](https://hub.docker.com/r/mapserver/mapserver) are available on Docker hub.

## Mapserver on Apple

Mapserver is available via Homebrew (requires python). Try:

```
brew install mapserver
```

## Running mapserver from command line

Mapserver offers some capabilities via command line. You can run from command line for example:

```
mapserv QUERY_STRING="map=example.map&service=wms&request=getcapabilities"
```
