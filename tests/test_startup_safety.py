"""Exercise the real CLI with persisted automation, without GPU submissions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request, build_opener, ProxyHandler


class StartupSafetyTests(unittest.TestCase):
    def test_automation_off_overrides_persisted_setting_before_serving(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'settings.json').write_text(json.dumps({'automation_enabled': True}))
            process = subprocess.Popen([sys.executable, 'weather_controller.py', '--state-dir', tmp,
                                        '--port', '0', '--automation-off'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith('Preview-only controller on 127.0.0.1:'), line)
                base = 'http://' + line.split(' on ')[1]
                token = (root/'token').read_text().strip()
                req = Request(base+'/v1/status', headers={'Authorization':'Bearer '+token})
                with build_opener(ProxyHandler({})).open(req, timeout=5) as response:
                    status = json.load(response)
                self.assertFalse(status['automation_enabled'])
                self.assertFalse(status['render_enabled'])
                self.assertFalse(status['apply_enabled'])
                self.assertFalse(json.loads((root/'settings.json').read_text())['automation_enabled'])
            finally:
                process.terminate()
                process.communicate(timeout=15)


if __name__ == '__main__':
    unittest.main()
