import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]

class HolidayPackagingTests(unittest.TestCase):
    def test_runtime_revision_changes_when_only_theme_data_changes(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            for p in list(ROOT.glob('*.py'))+list(ROOT.glob('holiday*.json')): shutil.copy2(p,d/p.name)
            cmd=[sys.executable,'-c','from weather_controller import SOURCE_REVISION; print(SOURCE_REVISION)']
            before=subprocess.check_output(cmd,cwd=d,text=True)
            p=d/'holiday_themes.json'; p.write_text(p.read_text()+'\n')
            after=subprocess.check_output(cmd,cwd=d,text=True)
            self.assertNotEqual(before,after,'runtime fingerprint ignores theme data')

    def test_package_contains_exact_calendar_data(self):
        with zipfile.ZipFile(ROOT/'artifacts/org.troyborg.weatherhorde.plasmoid') as archive:
            for name in ('holiday_catalog.json','holiday_themes.json'):
                self.assertIn('contents/data/'+name,archive.namelist())
                self.assertEqual(archive.read('contents/data/'+name),(ROOT/name).read_bytes())
        with zipfile.ZipFile(ROOT/'artifacts/weather-horde-controller.zip') as archive:
            for name in ('calendar_context.py','holiday_prompt.py','holiday_catalog.json','holiday_themes.json'):
                self.assertEqual(archive.read(name),(ROOT/name).read_bytes())
