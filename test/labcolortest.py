import json
import os
import unittest

from bridgestyle.arcgis import togeostyler

test_data_folder = os.path.join(os.path.dirname(__file__), "data", "arcgis")

def resource_path(name):
    return os.path.join(test_data_folder, name)

class LabColorConversionTest(unittest.TestCase):
    """Test LAB color conversion functionality"""

    def test_lab_color_conversion(self):
        """Test that CIMLABColor types are properly converted to RGB hex"""
        # Test the direct LAB to RGB conversion function
        lab_values = [40.859999999999999, -51.189999999999998, 41.390000000000001]
        r, g, b = togeostyler._lab2rgb(lab_values)
        
        # Basic validation - should be valid RGB values
        self.assertTrue(0 <= r <= 255, f"Red value {r} out of range")
        self.assertTrue(0 <= g <= 255, f"Green value {g} out of range") 
        self.assertTrue(0 <= b <= 255, f"Blue value {b} out of range")
        
        # This specific LAB value should produce a dark green color
        self.assertGreater(g, r, "Should be more green than red")
        self.assertGreater(g, b, "Should be more green than blue")

    def test_lab_color_processing(self):
        """Test that _processColor handles CIMLABColor correctly"""
        lab_color = {
            "type": "CIMLABColor",
            "values": [40.859999999999999, -51.189999999999998, 41.390000000000001, 100]
        }
        
        hex_color = togeostyler._processColor(lab_color)
        
        # Should return a valid hex color
        self.assertTrue(hex_color.startswith("#"), "Should start with #")
        self.assertEqual(len(hex_color), 7, "Should be 7-character hex")
        self.assertNotEqual(hex_color, "#000000", "Should not be black (old bug)")
        
        # Test that it's a valid hex string
        try:
            int(hex_color[1:], 16)
        except ValueError:
            self.fail("Returned color is not a valid hex string")

    def test_lab_gradient_conversion(self):
        """Test conversion of a full LAB color gradient"""
        # Heat island gradient colors (green to red)
        lab_colors = [
            [40.86, -51.19, 41.39, 100],  # Dark green
            [61.16, -40.00, 58.11, 100],  # Medium green
            [86.21, 4.75, 82.19, 100],    # Yellow
            [58.27, 71.88, 68.38, 100]    # Red
        ]
        
        hex_colors = []
        for lab_values in lab_colors:
            color_obj = {"type": "CIMLABColor", "values": lab_values}
            hex_color = togeostyler._processColor(color_obj)
            hex_colors.append(hex_color)
        
        # Should have unique colors (not all black)
        unique_colors = set(hex_colors)
        self.assertEqual(len(unique_colors), 4, "Should have 4 distinct colors")
        
        # None should be black
        for hex_color in hex_colors:
            self.assertNotEqual(hex_color, "#000000", "No gradient color should be black")

    def test_lab_color_layer_conversion(self):
        """Test LAB color conversion using test data file"""
        # Load the LAB color test file
        test_file = resource_path("lab_colors_test.lyrx")
        if os.path.exists(test_file):
            with open(test_file) as f:
                arcgis_data = json.load(f)
            
            geostyler, icons, warnings = togeostyler.convert(arcgis_data)
            
            # Check that conversion completed without errors
            self.assertIsNotNone(geostyler)
            self.assertIn("rules", geostyler)
            
            # Check that LAB colors were converted properly
            rules = geostyler.get("rules", [])
            for rule in rules:
                symbolizers = rule.get("symbolizers", [])
                for symbolizer in symbolizers:
                    if symbolizer.get("kind") == "Fill" and "color" in symbolizer:
                        color = symbolizer["color"]
                        self.assertNotEqual(color, "#000000", 
                                          f"LAB color should not be black in rule: {rule.get('name', 'unnamed')}")

    def test_existing_color_types_still_work(self):
        """Regression test: ensure other color types still work after LAB support"""
        test_cases = [
            # RGB color
            ({"type": "CIMRGBColor", "values": [255, 128, 64, 100]}, "#ff8040"),
            # CMYK color  
            ({"type": "CIMCMYKColor", "values": [0, 50, 75, 0, 100]}, None),  # Just check it doesn't crash
            # HSV color
            ({"type": "CIMHSVColor", "values": [120, 100, 50, 100]}, None),  # Just check it doesn't crash
            # Gray color
            ({"type": "CIMGrayColor", "values": [128, 100]}, "#808080"),
        ]
        
        for color_obj, expected in test_cases:
            hex_color = togeostyler._processColor(color_obj)
            self.assertTrue(hex_color.startswith("#"), f"Should return hex color for {color_obj['type']}")
            if expected:
                self.assertEqual(hex_color, expected, f"Expected {expected} for {color_obj['type']}")

    def test_none_color_handling(self):
        """Test that None colors are handled gracefully"""
        hex_color = togeostyler._processColor(None)
        self.assertEqual(hex_color, "#000000", "None should return black")

if __name__ == '__main__':
    unittest.main()
