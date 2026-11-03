import unittest
from pathlib import Path


class UpscaleCopyTests(unittest.TestCase):
    def test_model_help_describes_four_times_restoration(self):
        qml = (Path(__file__).resolve().parents[1] /
               'plasma-widget/org.troyborg.weatherhorde/contents/ui/main.qml').read_text()
        self.assertIn('4× upscaler', qml)
        self.assertNotIn('2× upscaler', qml)
