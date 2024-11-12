import re
from enum import Enum


ESRI_SYMBOLS_FONT = "ESRI Default Marker"
PT_TO_PX_FACTOR = 4 / 3
POLYGON_FILL_RESIZE_FACTOR = 2 / 3
OFFSET_FACTOR = 4 / 3
PROPERTY_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class MarkerPlacementPosition(Enum):
    START = "startPoint"
    END = "endPoint"


class MarkerPlacementAngle(Enum):
    START = "startAngle"
    END = "endAngle"


def pt_to_px(pt):
    return pt * PT_TO_PX_FACTOR
