import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

class AutoPairingInstallTests(unittest.TestCase):
    def load(self):
        path=Path('scripts/install-auto-pairing.py')
        self.assertTrue(path.exists(),'Missing owner-safe one-command installer')
        spec=importlib.util.spec_from_file_location('auto_install',path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def test_non_owner_cannot_install_or_reload(self):
        module=self.load()
        with patch.dict('os.environ', {'WEATHER_HORDE_OWNER':'fixture-owner'}), patch.object(module.pwd,'getpwnam') as owner, patch.object(module.subprocess,'run') as run:
            owner.return_value.pw_uid=-1
            with self.assertRaisesRegex(RuntimeError,'owner'): module.install(reload=True)
            run.assert_not_called()
    def test_verify_release_without_install(self):
        self.load()
        result=subprocess.run(['python','scripts/install-auto-pairing.py','--verify-only'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Release verified',result.stdout)
