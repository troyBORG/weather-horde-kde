"""Owner launcher regressions; no owner bus, GPU or live services used."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('connect_owner', Path('scripts/connect-owner.py'))
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class LaunchReached(Exception):
    pass


class OwnerConnectionTests(unittest.TestCase):
    def test_default_connection_does_not_require_comfy_or_enable_rendering(self):
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            if command[0] == 'systemctl':
                return subprocess.CompletedProcess(command, 3, stdout='inactive\n')
            raise LaunchReached()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(owner, 'require_configured_owner'), \
             patch.object(owner, 'discover', return_value=([{'id':'TEST','width':1920,'height':1080,'scale':1}], '')), \
             patch.object(owner, 'ComfyTransport', side_effect=AssertionError('Pairing must not depend on ComfyUI')), \
             patch.object(owner.Path, 'home', return_value=Path(tmp)), \
             patch.object(owner.socket, 'socket'), \
             patch.object(owner.subprocess, 'run', side_effect=run), \
             patch.dict(owner.os.environ, {'WEATHER_HORDE_COMFY_ROOT':'', 'XDG_DATA_HOME':tmp}), \
             patch.object(owner.sys, 'argv', ['connect-owner.py']):
            with self.assertRaises(LaunchReached):
                owner.main()
        self.assertIn('--setenv=WEATHER_HORDE_COMFY_ROOT='+str(Path(tmp)/'ComfyUI'), commands[-1])
        self.assertNotIn('--preview-checkpoint', commands[-1])
        self.assertIn('--automation-off', commands[-1])

    def test_active_owner_service_repairs_pairing_without_restart(self):
        self.active_owner_service(manual=False)

    def test_manual_pairing_is_explicit_clipboard_fallback(self):
        self.active_owner_service(manual=True)

    def active_owner_service(self, manual=False):
        import io
        import json
        from unittest.mock import MagicMock
        status = {'displays':[{'id':'TEST'}], 'preview_only':True, 'render_enabled':True,
                  'apply_enabled':False, 'automation_enabled':False, 'guard':{'decision':'unknown'}}
        opener = MagicMock()
        opener.open.side_effect = lambda *a, **kw: io.StringIO(json.dumps(status))
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            if command[0] == 'systemctl':
                return subprocess.CompletedProcess(command, 0, stdout='active\n')
            if command[0] == 'wl-copy':
                self.assertEqual(kwargs['input'], b'x'*40)
                return subprocess.CompletedProcess(command, 0)
            self.fail('Existing service must not be restarted')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'.local/state/weather-horde-kde'
            root.mkdir(parents=True, mode=0o700)
            (root/'token').write_text('x'*40)
            (root/'token').chmod(0o600)
            with patch.object(owner, 'require_configured_owner'), \
                 patch.object(owner, 'discover', return_value=([{'id':'TEST','width':1920,'height':1080,'scale':1}], '')), \
                 patch.object(owner.Path, 'home', return_value=Path(tmp)), \
                 patch.object(owner, 'build_opener', return_value=opener), \
                 patch.object(owner.subprocess, 'run', side_effect=run), \
                 patch.object(owner.sys, 'argv', ['connect-owner.py'] + (['--manual-pairing'] if manual else [])):
                owner.main()
            receipt = json.loads((root/'connection-receipt.json').read_text())
            self.assertFalse(receipt['service_started'])
            self.assertTrue(receipt['authenticated_status']['render_enabled'])
            self.assertEqual(len([c for c in commands if c[0]=='wl-copy']), 1 if manual else 0)

    def test_non_owner_refused_before_discovery(self):
        with patch.dict('os.environ', {'WEATHER_HORDE_OWNER':'fixture-owner'}), \
             patch.object(owner.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=-1)), \
             patch.object(owner, 'discover') as discover, \
             patch.object(owner.sys, 'argv', ['connect-owner.py']):
            with self.assertRaisesRegex(RuntimeError, 'graphical terminal'):
                owner.main()
            discover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
