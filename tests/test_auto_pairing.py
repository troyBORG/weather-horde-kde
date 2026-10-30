"""Build and exercise the limited local native token reader, never owner secrets."""
from pathlib import Path
import subprocess
import unittest

class AutoPairingNativeTests(unittest.TestCase):
    def test_native_private_file_boundary(self):
        self.assertTrue(Path('native-pairing/CMakeLists.txt').exists(), 'Automatic local pairing reader is missing')
        build=Path('artifacts/native-pairing').resolve()
        subprocess.run(['cmake','-S','native-pairing','-B',str(build)],check=True,capture_output=True)
        subprocess.run(['cmake','--build',str(build)],check=True,capture_output=True)
        p=subprocess.run([str(build/'pairing-test')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertIn('PRIVATE_TOKEN_BOUNDARY_PASS',p.stdout)
