from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QImage, QPainter
NO_ICON = "no_icon"
from ..qgis.togeostyler import spriteSize
from .fromgeostyler import spriteURLFull, tileURLFull

def convertGroup(group, geostylers, sprites, baseUrl, workspace, name):
    obj = {"version": 8,
        "glyphs": "mapbox://fonts/mapbox/{fontstack}/{range}.pbf",
        "name": name,
        "sources": {
            _source_name: {
                "type": "vector",
                "tiles": [
                    tileURLFull(baseUrl, workspace, name)
                ],
                "minZoom": 0,
                "maxZoom": 20  # todo: might be able to determine these from style
            },
    },
    "sprite": spriteURLFull(baseUrl, workspace, name),
    "layers": []
    }

    warnings = []
    mblayers = []
    allSprites = {}

    # build geostyler and mapbox styles
    for layername in group["layers"]:        
        allSprites.update(sprites[layername])  # combine/accumulate sprites
        geostylers[layername] = geostyler
        mbox, mbWarnings = convert(geostylers[layername])
        warnings.extend(mbWarnings)
        mboObj = json.loads(mbox)
        mblayers.extend(mboxObj["layers"])

    obj["layers"] = mblayers

    return json.dumps(obj, indent=4), warnings, obj, toSpriteSheet(allSprites)

# allSprites ::== sprite name -> {"image":Image, "image2x":Image}
def toSpriteSheet(allSprites):
    if allSprites:
        height = spriteSize
        width = spriteSize * len(allSprites)
        img = QImage(width, height, QImage.Format_ARGB32)
        img.fill(QColor(Qt.transparent))
        img2x = QImage(width * 2, height * 2, QImage.Format_ARGB32)
        img2x.fill(QColor(Qt.transparent))
        painter = QPainter(img)
        painter.begin(img)
        painter2x = QPainter(img2x)
        painter2x.begin(img2x)
        spritesheet = {NO_ICON: {"width": 0,
                                 "height": 0,
                                 "x": 0,
                                 "y": 0,
                                 "pixelRatio": 1}}
        spritesheet2x = {NO_ICON: {"width": 0,
                                   "height": 0,
                                   "x": 0,
                                   "y": 0,
                                   "pixelRatio": 1}}
        x = 0
        for name, _sprites in allSprites.items():
            s = _sprites["image"]
            s2x = _sprites["image2x"]
            painter.drawImage(x, 0, s)
            painter2x.drawImage(x * 2, 0, s2x)
            spritesheet[name] = {"width": s.width(),
                                 "height": s.height(),
                                 "x": x,
                                 "y": 0,
                                 "pixelRatio": 1}
            spritesheet2x[name] = {"width": s2x.width(),
                                   "height": s2x.height(),
                                   "x": x * 2,
                                   "y": 0,
                                   "pixelRatio": 2}
            x += s.width()
        painter.end()
        painter2x.end()
        folder = "/Users/ddd/delme/"
        img.save(os.path.join(folder, "spriteSheet.png"))
        img2x.save(os.path.join(folder, "spriteSheet@2x.png"))
        with open(os.path.join(folder, "spriteSheet.json"), 'w') as f:
            json.dump(spritesheet, f)
        with open(os.path.join(folder, "spriteSheet@2x.json"), 'w') as f:
            json.dump(spritesheet2x, f)

        return {"img": img, "img2x": img2x, "json": json.dumps(spritesheet), "json2x": json.dumps(spritesheet2x)}

    return None