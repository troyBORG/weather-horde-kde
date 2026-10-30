import subprocess, unittest
from unittest.mock import patch
from types import SimpleNamespace
from wallpaper import PlasmaBackend
import os

class WallpaperErrorTests(unittest.TestCase):
    def test_qdbus_permission_error_is_actionable_without_script_or_paths(self):
        error=subprocess.CalledProcessError(1,['qdbus6','PRIVATE_SCRIPT'],stderr='Permission denied /home/example/private\nBacktrace private details')
        with patch('wallpaper.discover',return_value=([{'id':'DP-2'}],'')), patch('wallpaper.subprocess.run',side_effect=[SimpleNamespace(stdout=str(os.getuid())),error]):
            with self.assertRaisesRegex(ValueError,'Plasma scripting failed.*Permission denied') as caught:
                PlasmaBackend().evaluate('PRIVATE_SCRIPT')
            self.assertNotIn('PRIVATE_SCRIPT',str(caught.exception))
            self.assertNotIn('/home/',str(caught.exception))
            self.assertNotIn('Backtrace',str(caught.exception))
