import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import test_wallpaper as wallpaper_tests
from weather_controller import Controller


class RefreshReceiptTests(unittest.TestCase):
    def test_successful_readback_durable_timestamp_recovers_crash(self):
        with tempfile.TemporaryDirectory() as d:
            c, backend = wallpaper_tests.WallpaperTests().setup_controller(d)
            result = c.dispatch('POST','/v1/apply', {'target':'DP-1', 'preview_id':c.image_preview['id'], 'confirmation':'Apply this validated preview'})
            self.assertTrue(result['verified'])
            receipt = json.loads((Path(d)/'wallpaper-restore.json').read_text())['DP-1']
            self.assertGreater(receipt['applied_at'], time.time()-5)
            restarted = Controller(d)
            self.assertEqual(restarted.scheduler.success['image_wallpaper']['DP-1'], receipt['applied_at'])

    def test_restore_invalidates_current_wallpaper_freshness(self):
        with tempfile.TemporaryDirectory() as d:
            c, backend = wallpaper_tests.WallpaperTests().setup_controller(d)
            result=c.dispatch('POST','/v1/apply', {'target':'DP-1', 'preview_id':c.image_preview['id'], 'confirmation':'Apply this validated preview'})
            self.assertEqual(c.status()['refresh']['last_success']['image_wallpaper']['DP-1'], result['applied_at'])
            c.dispatch('POST','/v1/restore', {'target':'DP-1','confirmation':'Restore previous wallpaper'})
            self.assertNotIn('DP-1', c.scheduler.success.get('image_wallpaper',{}))
            self.assertNotIn('DP-1', Controller(d).scheduler.success.get('image_wallpaper',{}))

    def test_failed_readback_has_no_success_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            c, backend = wallpaper_tests.WallpaperTests().setup_controller(d)
            backend.replace = lambda *args: None
            with self.assertRaises(ValueError):
                c.dispatch('POST','/v1/apply', {'target':'DP-1', 'preview_id':c.image_preview['id'], 'confirmation':'Apply this validated preview'})
            receipt = json.loads((Path(d)/'wallpaper-restore.json').read_text())['DP-1']
            self.assertNotIn('applied_at', receipt)
