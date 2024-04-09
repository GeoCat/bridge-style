import math

def height_normalized(coords: list[list[float]]) -> list[list[float]]:
    height = max([coord[1] for coord in coords]) - min([coord[1] for coord in coords])
    return [[coord[0] / height, coord[1] / height] for coord in coords]

def distanceBetweenPoints(a: list, b: list) -> float:
    return math.sqrt((b[0]-a[0])**2 + (b[1]-a[1])**2)

def to_wkt(geometry: dict) -> dict:
    defaultMarker = {"wellKnownName": "circle"}

    if geometry.get("rings"):
        rings = geometry["rings"][0]
        # GeoServer will rescale the symbol using the specified size, using the height as a reference
        # So we normalize the coordinates to have a height of 1
        rings = height_normalized(rings)
        coordinates = ", ".join([" ".join([str(i) for i in j]) for j in rings])
        return {
                    "wellKnownName": f"wkt://POLYGON(({coordinates}))",
                    "maxX": max([coord[0] for coord in rings]),
                    "maxY": max([coord[1] for coord in rings]),
        }

    # The following corresponds to the geometry of the line symbolizer in ArcGIS
    elif geometry.get("paths") and geometry["paths"][0] == [[2, 0], [-2, 0]]:
        return {"wellKnownName": "wkt://MULTILINESTRING((0 2, 0 0))"}

    # For documentation on curveRings, see
    # https://developers.arcgis.com/documentation/common-data-types/geometry-objects.htm
    elif geometry.get("curveRings"):
        curveRing = geometry["curveRings"][0]
        startPoint = curveRing[0]
        curve = curveRing[1].get("a") or curveRing[1].get("c")
        if not curve:
            return defaultMarker
        endPoint = curve[0]
        centerPoint = curve[1]
        if not endPoint == startPoint:
            return defaultMarker
        radius = distanceBetweenPoints(startPoint, centerPoint)
        return {
                    "wellKnownName": "circle",
                    "maxX": radius,
                    "maxY": radius,
        }
    return defaultMarker
