import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from weather_controller import Controller
from test_holiday_prompt import LOCATION
ROOT=Path(__file__).resolve().parents[1]

class HolidayPreviewTests(unittest.TestCase):
    def test_manual_theme_override_is_preview_only_and_rejects_unknown(self):
        from holiday_preview import fixture_preview
        import inspect
        self.assertIn('theme_override',inspect.signature(fixture_preview).parameters)
        value=fixture_preview('2026-11-02',LOCATION,theme_override='halloween')
        self.assertEqual(value['selected_theme'],'halloween')
        self.assertEqual(value['calendar_context']['selection_reason'],'manual offline preview override')
        self.assertNotIn('us_halloween',value['holiday_ids'])
        with self.assertRaises(ValueError): fixture_preview('2026-11-02',LOCATION,theme_override='invented')

    def test_offline_cli_from_other_cwd_and_endpoint_is_not_render(self):
        cli=ROOT/'scripts/holiday-preview.py'
        self.assertTrue(cli.exists(),'offline holiday preview CLI missing')
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.run([sys.executable,str(cli),'--date','2026-10-31','--timezone','America/Chicago','--country','US','--subdivision','IA','--scene','town','--width','1080','--height','1920'],cwd=d,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            result=json.loads(p.stdout)
            self.assertEqual(result['selected_theme'],'halloween')
            self.assertEqual(result['calendar_local_date'],'2026-10-31')
            self.assertEqual(result['composition']['width'],1080)
            self.assertIn('fixture',result['weather_evidence']['source'].lower())
            for flag in ('--gpu','--apply'):
                self.assertNotEqual(subprocess.run([sys.executable,str(cli),'--date','2026-10-31',flag],capture_output=True).returncode,0)
            c=Controller(d); c.settings['location']=LOCATION
            with patch('scene.fetch_json',side_effect=AssertionError('network forbidden')),patch.object(c,'render_images',side_effect=AssertionError('GPU forbidden')):
                value=c.dispatch('POST','/v1/calendar/preview',{'date':'2026-10-31'})
            self.assertEqual(value['selected_theme'],'halloween')
            self.assertIsNone(c.preview)
            self.assertIsNone(c.image_preview)
            self.assertFalse(c.scheduler.pending)
            with self.assertRaises(ValueError): c.dispatch('POST','/v1/calendar/preview',{'date':'2026-02-30'})
