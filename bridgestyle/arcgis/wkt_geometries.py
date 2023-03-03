from .constants import pt_to_px

def to_wkt(geometry):
    if geometry.get("rings"):
        rings = geometry["rings"][0]
        coordinates = ", ".join([" ".join([str(pt_to_px(i)) for i in j]) for j in rings])
        return {
                    "wellKnownName": f"wkt://POLYGON(({coordinates}))",
                    "maxX": pt_to_px(max([coord[0] for coord in rings])),
                    "maxY": pt_to_px(max([coord[1] for coord in rings])),
        }
    # The following corresponds to the geometry of the line symbolizer in ArcGIS
    elif geometry.get("paths") and geometry["paths"][0] == [[2, 0], [-2, 0]]:
        return {"wellKnownName": "wkt://MULTILINESTRING((0 2, 0 0))"}
    return {"wellKnownName": "circle"}
