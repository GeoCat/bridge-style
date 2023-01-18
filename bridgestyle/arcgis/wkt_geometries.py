def to_wkt(geometry):
    if geometry.get("rings"):
        rings = geometry["rings"][0]
        coordinates = ", ".join([" ".join([str(i) for i in j]) for j in rings])
        return {
                    "wellKnownName": f"wkt://POLYGON(({coordinates}))",
                    "maxX": max([coord[0] for coord in rings]),
                    "maxY": max([coord[1] for coord in rings]),
        }
    return {"wellKnownName": "circle"}
