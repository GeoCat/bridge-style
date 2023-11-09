from enum import Enum


ESRI_SYMBOLS_FONT = "ESRI Default Marker"
PT_TO_PX_FACTOR = 4/3
POLYGON_FILL_RESIZE_FACTOR = 2/3
OFFSET_FACTOR = 4/3

class MarkerPlacementPosition(Enum):
    START = "startPoint"
    END = "endPoint"

class MarkerPlacementAngle(Enum):
    START = "startAngle"
    END = "endAngle"

def pt_to_px(pt):
    return pt * PT_TO_PX_FACTOR
