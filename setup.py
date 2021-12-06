from setuptools import setup, find_packages

exec(open('bridgestyle/version.py').read())
setup(
    name="bridgestyle",
    version=__version__,
    author="GeoCat BV",
    author_email="volaya@geocat.net",
    description="A Python library to convert between different map style formats",
    license="MIT",
    keywords=["GeoCat", "Bridge", "style", "symbology", "styling", "mapping", "SLD", "cartography",
              "Mapfile", "CIM", "GeoStyler", "Mapbox", "QGIS", "GeoServer", "Esri"],
    url="https://github.com/GeoCat/bridge-style",
    packages=find_packages(),
    entry_points={"console_scripts": ["style2style=bridgestyle.style2style:main"]},
)
