"""Real subprocess orchestration with explicit fixture-only system boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
import importlib.util, json, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('guided',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class IO:
    def __init__(self): self.events=[]
    def capture(self): self.events.append('capture');return {'automation_enabled':False,'location':{'name':'fixture'},'interval_minutes':30}
    def backup(self,s): self.events.append('backup')
    def wait_idle(self): self.events.append('idle')
    def auto_off(self,s): self.events.append('off')
    def stop(self): self.events.append('stop')
    def wait_port(self): self.events.append('port')
    def install(self): self.events.append('install')
    def start(self): self.events.append('start')
    def verify(self,s): self.events.append('verify')
    def restore(self,s): self.events.append('restore');assert s['automation_enabled'] is False
io=IO()
try: m.update(io)
finally: print(json.dumps(io.events))
'''

class GuidedUpdateTests(unittest.TestCase):
    def run_fixture(self, harness=HARNESS):
        return subprocess.run([sys.executable,'-B','-c',harness,str(ROOT/'scripts/guided-update-owner.py')],capture_output=True,text=True,timeout=15)

    def scenario(self, name):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'tests/guided_fixture.py'),str(ROOT/'scripts/guided-update-owner.py'),name],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_owner_success_preserves_exact_preferences_and_bytes(self):
        result=self.scenario('success')
        self.assertTrue(result['success'],result)
        self.assertTrue(result['bytes_preserved'])
        self.assertFalse(result['settings']['automation_enabled'])
        self.assertEqual(result['backups'],1)
        self.assertLess(result['events'].index('api-off'),result['events'].index('ctl:stop'))

    def test_display_discovery_readiness_retries_without_reinstall(self):
        result=self.scenario('display-readiness')
        self.assertTrue(result['success'],result)
        self.assertGreaterEqual(result['events'].count('startup-status'),3)
        self.assertEqual(result['events'].count('install'),1)
        self.assertTrue(result['bytes_preserved'])

    def test_persistent_missing_displays_times_out_without_restart_or_restore(self):
        result=self.scenario('display-missing')
        self.assertFalse(result['success'])
        self.assertIn('error:TimeoutError',result['events'])
        self.assertEqual(result['events'].count('ctl:start'),1)
        self.assertFalse(result['bytes_preserved'])
        self.assertFalse(result['settings']['automation_enabled'])

    def test_override_and_managed_mismatches_fail_without_retry(self):
        for scenario in ('override-active','override-missing','managed-mismatch'):
            with self.subTest(scenario=scenario):
                result=self.scenario(scenario)
                self.assertFalse(result['success'])
                self.assertEqual(result['events'].count('startup-status'),1)
                self.assertIn('error:RuntimeError',result['events'])
                self.assertFalse(result['bytes_preserved'])

    def test_busy_timeout_never_disables_or_stops(self):
        result=self.scenario('timeout')
        self.assertFalse(result['success'])
        self.assertNotIn('api-off',result['events'])
        self.assertNotIn('ctl:stop',result['events'])

    def test_pending_apply_timeout_never_stops(self):
        result=self.scenario('pending')
        self.assertFalse(result['success'])
        self.assertNotIn('ctl:stop',result['events'])

    def test_port_time_wait_retries_without_repeated_stop(self):
        result=self.scenario('port-retry')
        self.assertTrue(result['success'])
        self.assertEqual(result['events'].count('port-check'),3)
        self.assertEqual(result['events'].count('ctl:stop'),1)

    def test_foreign_listener_rejects_install_and_start(self):
        result=self.scenario('foreign')
        self.assertFalse(result['success'])
        self.assertNotIn('install',result['events'])
        self.assertNotIn('ctl:start',result['events'])

    def test_auth_failure_no_backup_or_mutation(self):
        result=self.scenario('auth-failure')
        self.assertFalse(result['success'])
        self.assertEqual(result['backups'],0)
        self.assertNotIn('api-off',result['events'])

    def test_legacy_entry_on_refused_without_restoration(self):
        result=self.scenario('auto-on')
        self.assertFalse(result['success'])
        self.assertTrue(result['settings']['automation_enabled'])
        self.assertNotIn('api-off',result['events'])

    def test_installer_rollback_stays_stopped(self):
        result=self.scenario('rollback')
        self.assertFalse(result['success'])
        self.assertIn('installer-rollback',result['events'])
        self.assertNotIn('ctl:start',result['events'])
        self.assertFalse(result['settings']['automation_enabled'])

    def test_verify_failure_does_not_restore_original_bytes(self):
        result=self.scenario('verify-failure')
        self.assertFalse(result['success'])
        self.assertFalse(result['bytes_preserved'])
        self.assertFalse(result['settings']['automation_enabled'])
        self.assertEqual(result['events'].count('ctl:stop'),1)

    def test_bootstrap_exposes_guided_preflight_and_update(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/owner-bootstrap.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertIn('--guided',result.stdout)
        self.assertIn('--preflight',result.stdout)

    def test_delivery_generator_includes_short_guided_wrapper(self):
        text=(ROOT/'scripts/make-owner-delivery.py').read_text()
        self.assertIn("output/'deploy.sh'",text)
        self.assertIn('--guided',text)

    def test_update_lock_does_not_conflict_with_controller_lifetime_lock(self):
        code = r'''
from receipt_lock import state_lock
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    with state_lock(Path(tmp),exclusive=False):
        with m.update_lock(Path(tmp)):
            try:
                with m.update_lock(Path(tmp)): pass
            except BlockingIOError: pass
            else: raise AssertionError('duplicate update admitted')
'''
        prefix=HARNESS.split('class IO:')[0]
        result=self.run_fixture(prefix+code)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_concurrent_preferences_refused_before_stop(self):
        result=self.scenario('concurrent-preferences')
        self.assertFalse(result['success'])
        self.assertNotIn('ctl:stop',result['events'])
        self.assertEqual(result['settings']['interval_minutes'],60)

    def test_enablement_change_refused_before_install(self):
        result=self.scenario('enablement-change')
        self.assertFalse(result['success'])
        self.assertNotIn('install',result['events'])
        self.assertNotIn('ctl:start',result['events'])

    def test_success_preserves_entry_off_and_orders_verification(self):
        result=self.run_fixture()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),['capture','backup','idle','off','idle','stop','port','install','start','verify','restore'])
