import json
import os
import re
import unittest

from bridgestyle.mapserver import fromgeostyler

test_data_folder = os.path.join(os.path.dirname(__file__), "data", "mapserver")


def resource_path(name):
    return os.path.join(test_data_folder, name)


def load_geostyler(name):
    with open(resource_path(name)) as f:
        return json.load(f)


class MapserverFromGeostylerTest(unittest.TestCase):
    """Checks that the emitted mapfile uses the syntax MapServer accepts.

    MapServer stops reading the map at the first token it cannot parse, so a
    single wrong keyword takes the whole layer down.
    """

    def setUp(self):
        geostyler = load_geostyler("dashed_line_with_label.geostyler")
        self.mapfile, _, _ = fromgeostyler.convert(geostyler)

    def test_linecap_and_linejoin_are_not_quoted(self):
        self.assertIn("LINECAP square", self.mapfile)
        self.assertIn("LINEJOIN bevel", self.mapfile)
        self.assertNotIn('"square"', self.mapfile)
        self.assertNotIn('"bevel"', self.mapfile)

    def test_linecap_and_linejoin_are_left_out_when_not_set(self):
        geostyler = load_geostyler("dashed_line_with_label.geostyler")
        line = geostyler["rules"][0]["symbolizers"][0]
        del line["cap"]
        del line["join"]
        mapfile, _, _ = fromgeostyler.convert(geostyler)
        self.assertNotIn("LINECAP", mapfile)
        self.assertNotIn("LINEJOIN", mapfile)

    def test_pattern_is_a_block(self):
        pattern = re.search(
            r"PATTERN\s*\n\s*8 5\s*\n\s*END", self.mapfile
        )
        self.assertIsNotNone(pattern, self.mapfile)

    def test_label_is_a_member_of_class_and_not_of_style(self):
        blocks = []
        labels = 0
        for line in self.mapfile.splitlines():
            keyword = line.strip().split(" ")[0]
            if keyword == "END":
                blocks.pop()
            elif keyword in ("LAYER", "CLASS", "STYLE", "LABEL", "PATTERN"):
                if keyword == "LABEL":
                    labels += 1
                    self.assertEqual(
                        "CLASS",
                        blocks[-1],
                        "LABEL sits in %s, not in CLASS:\n%s"
                        % (blocks[-1], self.mapfile),
                    )
                blocks.append(keyword)
        self.assertEqual(1, labels)


if __name__ == "__main__":
    unittest.main()
