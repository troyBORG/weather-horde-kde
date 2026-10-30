import importlib.util, json, unittest
from unittest.mock import patch
class OwnerHelperTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('dp2helper','scripts/reconcile-dp2-owner.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_sanitized_snapshots_and_difference_paths(self):
        m=self.load()
        a={'image':'file:///private.png','activity':'private-id','settings':[{'group':['General'],'values':{'FillMode':'1','Secret':'private-token'}}]}
        b={'image':'file:///private.png','activity':'private-id','settings':[{'group':['General'],'values':{'FillMode':1,'Secret':'private-token'}}]}
        text=json.dumps(m.sanitize(a));self.assertNotIn('private',text)
        self.assertEqual(m.differences(a,b),['/settings/0/values/FillMode'])
    def test_wrong_owner_stops(self):
        m=self.load()
        with patch.object(m.pwd,'getpwuid') as user:
            user.return_value.pw_name='jorden'
            with self.assertRaisesRegex(RuntimeError,'owner'): m.require_owner()
    def test_live_listener_refuses_reconcile(self):
        m=self.load()
        with patch.object(m.socket,'create_connection'):
            with self.assertRaisesRegex(RuntimeError,'controller'): m.require_stopped()
