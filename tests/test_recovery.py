"""Recovery diagnosis is read-only; consent remains explicit and per process."""
import tempfile
import unittest
from pathlib import Path
from weather_controller import Controller

CONFIRM = 'I accept gaming stutter, VR disruption and GPU OOM risk'

class RecoveryTests(unittest.TestCase):
    def test_restart_diagnosis_separates_consent_from_safe_guard_and_history(self):
        with tempfile.TemporaryDirectory() as root:
            c = Controller(root)
            c.settings.update(automation_enabled=True, automation_policy='force')
            c.save()
            c = Controller(root)
            c.last_error = 'No Comfy job submitted: force_consent_revoked'
            before = (Path(root)/'settings.json').read_bytes()
            report = c.status().get('recovery', {})
            self.assertEqual(report.get('consent_required'), True)
            self.assertEqual(report['previous_error'], c.last_error)
            self.assertIn('restart', report['explanation'])
            self.assertFalse(c.force_consent)
            self.assertEqual((Path(root)/'settings.json').read_bytes(), before)
            frozen, _ = c.forced_policy()
            c.dispatch('PUT', '/v1/force-override', {'enabled':True,'confirmation':CONFIRM})
            self.assertEqual(frozen(), 'force_consent_revoked')
            report = c.status()['recovery']
            self.assertFalse(report['consent_required'])
            self.assertEqual(report['previous_error'], c.last_error)
            self.assertTrue(c.settings['automation_enabled'])
            self.assertIsNone(c.render_thread)

class ManualRecoveryTests(unittest.TestCase):
    def test_manual_override_keeps_hard_gates_and_frozen_revocation(self):
        import time
        from test_forced_refresh import fixture
        for failure in ('memory', 'expired', 'revoked', 'owner', 'scheduled'):
            with self.subTest(failure=failure), fixture(reason='safe', force=False,
                    failure='owner' if failure == 'owner' else None) as (c, backend, calls):
                c.settings['automation_policy'] = 'force'
                c.guard.update(total_mib=24576, free_mib=20000, observed_at=time.time())
                c.dispatch('PUT', '/v1/testing-override',
                           {'enabled':True, 'confirmation':'I accept stutter and OOM risk'})
                policy, receipt = c.manual_policy()
                if failure == 'memory': c.guard['free_mib'] = 1
                if failure == 'expired': c.override_deadline = time.monotonic()-1
                if failure == 'revoked':
                    c.dispatch('PUT', '/v1/testing-override', {'enabled':False})
                    c.dispatch('PUT', '/v1/testing-override',
                               {'enabled':True, 'confirmation':'I accept stutter and OOM risk'})
                    self.assertEqual(policy(), 'testing_override_expired')
                    continue
                result = c.dispatch('POST', '/v1/render', {'target':'all'}, scheduled=failure == 'scheduled')
                if c.render_thread: c.render_thread.join(5)
                self.assertEqual(calls, [], result)
                self.assertEqual(backend.writes, [])
                self.assertFalse(c.force_status()['active'])

    def test_testing_override_manual_preview_is_not_revoked_scheduled_force(self):
        from test_forced_refresh import fixture
        with fixture(reason='safe', force=False) as (c, backend, calls):
            c.settings['automation_policy'] = 'force'  # saved preference after restart
            import time
            c.guard.update(total_mib=24576, free_mib=20000, observed_at=time.time())
            c.dispatch('PUT', '/v1/testing-override',
                       {'enabled':True, 'confirmation':'I accept stutter and OOM risk'})
            result = c.dispatch('POST', '/v1/render', {'target':'all'})
            if c.render_thread: c.render_thread.join(5)
            self.assertEqual(calls, ['/prompt'], result)
            self.assertEqual(backend.writes, [])
            self.assertFalse(c.force_status()['active'])
            self.assertFalse(c.settings['automation_enabled'])
            self.assertTrue(c.image_preview['testing_override']['enabled'])

if __name__ == '__main__': unittest.main()
