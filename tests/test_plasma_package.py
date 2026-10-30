import json
from pathlib import Path
import unittest
import zipfile


def assert_plasma6_metadata(test, metadata):
    # Package installation and custom QML loading do not check shell admission.
    test.assertEqual(metadata.get("X-Plasma-API-Minimum-Version"), "6.0")
    test.assertEqual(metadata.get("KPackageStructure"), "Plasma/Applet")
    test.assertNotIn("X-Plasma-API", metadata)
    test.assertNotIn("X-Plasma-MainScript", metadata)


class PlasmaPackageTests(unittest.TestCase):
    def test_source_declares_plasma6_shell_compatibility(self):
        metadata = json.loads(Path('plasma-widget/org.troyborg.weatherhorde/metadata.json').read_text())
        assert_plasma6_metadata(self, metadata)

    def test_release_archive_declares_plasma6_shell_compatibility(self):
        with zipfile.ZipFile('artifacts/org.troyborg.weatherhorde.plasmoid') as archive:
            metadata = json.loads(archive.read('metadata.json'))
        assert_plasma6_metadata(self, metadata)
        source = json.loads(Path('plasma-widget/org.troyborg.weatherhorde/metadata.json').read_text())
        self.assertEqual(metadata, source, 'Rebuild the release archive after source changes')

    def test_isolated_install_declares_plasma6_shell_compatibility(self):
        receipt = json.loads(Path('artifacts/package-receipt.json').read_text())
        installed = Path(receipt['validation_root']) / 'org.troyborg.weatherhorde/metadata.json'
        metadata = json.loads(installed.read_text())
        assert_plasma6_metadata(self, metadata)
        self.assertEqual(metadata, json.loads(Path('plasma-widget/org.troyborg.weatherhorde/metadata.json').read_text()))

    def test_widget_exposes_all_control_sections_over_localhost_only(self) -> None:
        root = Path("plasma-widget/org.troyborg.weatherhorde")
        metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        qml = (root / "contents/ui/main.qml").read_text(encoding="utf-8")

        self.assertEqual(metadata["KPlugin"]["Id"], "org.troyborg.weatherhorde")
        self.assertRegex(qml, r'(?s)^(?:import [^\n]+\n|\s)*PlasmoidItem\s*\{')
        self.assertEqual(qml.count('PlasmoidItem {'),1)
        self.assertIn("http://127.0.0.1:8734", qml)
        self.assertIn('"/v1/status"', qml)
        self.assertNotIn("https://", qml)
        for control in (
            "Automation",
            "Interval",
            "Monitor",
            "Generate now",
            "Restore previous",
            "ZIP code",
            "Use this location",
        ):
            self.assertIn(control, qml)
        self.assertIn('"force": true', qml)
        self.assertIn("games, VR, or unsafe GPU use", qml)


    def test_widget_integrates_authenticated_preview_and_confirmation(self):
        qml = Path('plasma-widget/org.troyborg.weatherhorde/contents/ui/main.qml').read_text()
        for contract in ('Authorization', 'Bearer ', 'confirmation_id', '"/v1/preview"',
                         'Preview only', '52742', 'DeWitt', 'previewText', 'requestTimeout',
                         'intervalMinutes', 'ScrollView'):
            self.assertIn(contract, qml)
        self.assertNotIn('"location_confirmation": true', qml)

if __name__ == "__main__":
    unittest.main()
