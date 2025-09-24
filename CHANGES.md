Bridgestyle Changelog
=====================

## 0.1.5 (2025-09-24)
---------------------
- QGIS: support IS TRUE and IS NOT TRUE operators in expressions (thanks @benvanbasten-ns)
- MapLibre (thanks @benvanbasten-ns): 
  - fix conversion to float for text-halo-width 
  - add support for ELSE filter
  - basic support for QgsLinePatternFillSymbolLayer
- Upgrade for QGIS 4 / Qt6 (thanks @benvanbasten-ns)


## 0.1.4 (2025-08-26)
---------------------
- ArcGIS: Picture fill support, improved hatch fills, color substitution, marker along line (thanks @aaime) 
- Fix URLs in README for PyPI (thanks @geraldo)


## 0.1.3 (2025-06-24)
--------------------------------------
- Updated README
- Changes related to PyPI package (thanks @elisalle):
  - Use `pyproject.toml` instead of `setup.py`
  - Use src layout instead of flat layout
  - Make package PyPI-compatible
  - Add GitHub Actions release workflow

0.1.2
-----
- Added support for CIMChartRenderer (thanks @Idohalbany)
- Various bug fixes and improvements (thanks @benvanbasten-ns, @hoanphungt, @caspervdw, @geraldo)