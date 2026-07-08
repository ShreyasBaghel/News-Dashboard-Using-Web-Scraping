import sys
import os
import unittest

# Ensure project root is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.language_detector import is_english

class TestLanguageDetector(unittest.TestCase):
    def test_english_text(self):
        # Plain English title and description
        self.assertTrue(is_english(
            "Dalmia Cement Unveils Carbon Capture Pilot Plant in India",
            "The plant will capture carbon dioxide emissions from kiln operations."
        ))

    def test_non_english_chinese(self):
        # Chinese title
        self.assertFalse(is_english(
            "达米亚水泥在印度推出碳捕集试点工厂"
        ))

    def test_non_english_norwegian(self):
        # Norwegian title
        self.assertFalse(is_english(
            "Dalmia Cement avduker pilotanlegg for karbonfangst i India"
        ))

    def test_non_english_french(self):
        # French title
        self.assertFalse(is_english(
            "Dalmia Cement dévoile une usine pilote de captage du carbone en Inde"
        ))

    def test_empty_or_featureless_text(self):
        # Empty inputs
        self.assertFalse(is_english("", ""))
        # Only numbers/punctuation
        self.assertFalse(is_english("1234567890", "!!! ??? ..."))

if __name__ == "__main__":
    unittest.main()
