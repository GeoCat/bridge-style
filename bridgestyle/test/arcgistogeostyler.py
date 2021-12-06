import json
import os
import unittest

from bridgestyle.arcgis import togeostyler

test_data_folder = os.path.join(os.path.dirname(__file__), "data", "arcgis")

def resource_path(name):
    return os.path.join(test_data_folder, name)

class ArcgisTestTest(unittest.TestCase):

    def test_conversion(self):
        for filename in os.listdir(test_data_folder):
            path = os.path.join(test_data_folder, filename)
            with open(path) as f:
                arcgis = json.load(f)
            ret = togeostyler.convert(arcgis)
            print(ret)

if __name__ == '__main__':
    unittest.main()