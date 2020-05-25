import os
import unittest
import json
import context

from bridgestyle.arcgis import togeostyler

def resource_path(name):
    return os.path.join(os.path.dirname(__file__), "data", name)

class ArcgisTestTest(unittest.TestCase):

    def test_conversion(self):
        with open(resource_path("test.lyrx")) as f:
            arcgis = json.load(f)
        ret = togeostyler.convert(arcgis)
        print(ret)

if __name__ == '__main__':
    unittest.main()