import importlib.util, unittest
from pathlib import Path
from unittest.mock import patch

class RolloutTests(unittest.TestCase):
    def module(self):
        p=Path('scripts/rollout-owner.py')
        self.assertTrue(p.exists(),'single-owner guarded rollout helper missing')
        spec=importlib.util.spec_from_file_location('rollout',p)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_refuses_cross_uid_before_any_action(self):
        m=self.module()
        with patch.object(m.os,'getuid',return_value=1001), patch.dict('os.environ', {'WEATHER_HORDE_OWNER':'fixture-owner'}), patch.object(m.pwd,'getpwnam') as user, patch.object(m.subprocess,'run') as run:
            user.return_value.pw_uid=-1
            with self.assertRaisesRegex(RuntimeError,'owner'): m.require_owner()
            run.assert_not_called()
    def test_idle_preflight_rejects_busy_and_uncertain_states(self):
        m=self.module()
        good={'state':'idle','automation_enabled':False}
        m.require_idle(good,{'queue_running':[],'queue_pending':[]},False)
        for state in ('queued','rendering','rendering_guard_blocked','failed_unreconciled'):
            with self.assertRaises(RuntimeError): m.require_idle(good|{'state':state},{'queue_running':[],'queue_pending':[]},False)
        with self.assertRaises(RuntimeError): m.require_idle(good,{'queue_running':[[1]],'queue_pending':[]},False)
        with self.assertRaises(RuntimeError): m.require_idle(good,{'queue_running':[],'queue_pending':[]},True)
