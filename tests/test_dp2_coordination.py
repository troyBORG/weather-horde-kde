import importlib.util, subprocess, sys, tempfile, unittest
from pathlib import Path

class CoordinationTests(unittest.TestCase):
    def test_controller_start_and_retirement_exclude_each_other(self):
        from receipt_lock import state_lock
        with tempfile.TemporaryDirectory() as d:
            command=[sys.executable,'-c','from receipt_lock import state_lock; import sys;\nwith state_lock(sys.argv[1],exclusive=bool(int(sys.argv[2]))): pass',d]
            for exclusive in (True,False):
                with state_lock(Path(d),exclusive=exclusive):
                    result=subprocess.run(command+[str(int(not exclusive))],capture_output=True)
                    self.assertNotEqual(result.returncode,0)
                self.assertEqual(subprocess.run(command+['1'],capture_output=True).returncode,0)
    def test_helper_accept_current_is_explicit_and_lock_is_used(self):
        source=Path('scripts/reconcile-dp2-owner.py').read_text()
        self.assertIn("'--accept-current'",source)
        self.assertIn('with state_lock(root,exclusive=True)',source)
        source=Path('weather_controller.py').read_text()
        self.assertIn('with state_lock(args.state_dir,exclusive=False)',source)

    def test_real_controller_start_cannot_pass_retirement_lock(self):
        from receipt_lock import state_lock
        with tempfile.TemporaryDirectory() as d:
            with state_lock(Path(d),exclusive=True):
                result=subprocess.run([sys.executable,'weather_controller.py','--state-dir',d,'--automation-off'],capture_output=True,text=True,timeout=20)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('BlockingIOError',result.stderr)
            self.assertFalse((Path(d)/'token').exists())

    def test_collected_transient_unit_counts_as_stopped(self):
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('helper','scripts/reconcile-dp2-owner.py')
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        response=subprocess.CompletedProcess([],1,'LoadState=not-found\nActiveState=inactive\n','')
        with patch.object(helper.socket,'create_connection',side_effect=ConnectionRefusedError), patch.object(helper.subprocess,'run',return_value=response), patch.object(helper.Path,'iterdir',return_value=[]):
            helper.require_stopped()

if __name__=='__main__': unittest.main()
