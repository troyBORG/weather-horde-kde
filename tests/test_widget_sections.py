"""Focused navigation contract; real Plasma coverage is in test_scene_qml."""
from pathlib import Path
import unittest

QML = Path('plasma-widget/org.troyborg.weatherhorde/contents/ui/main.qml')

class WidgetSections(unittest.TestCase):
    def test_navigation_and_build_identity(self):
        text = QML.read_text()
        for name in ('wallpaperPage', 'schedulePage', 'scenePage', 'advancedPage',
                     'sectionTabs', 'diagnosticsDisclosure', 'widgetBuildIdentity', 'runtimeBuildIdentity'):
            self.assertIn('objectName: "' + name + '"', text)
        self.assertIn('source_revision', text)
        self.assertNotIn('Catch-up waits for 60 seconds', text)
        self.assertIn('property bool connectedPanorama: false', text)

if __name__ == '__main__': unittest.main()
