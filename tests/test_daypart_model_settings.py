import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from weather_controller import Controller


class SettingsTests(unittest.TestCase):
    def test_malformed_saved_policy_refuses_startup(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d); c.settings['model_policy']={'mode':'all'}; c.save()
            with self.assertRaises(ValueError): Controller(d)


    def test_invalid_policy_and_failed_persistence_are_transactional(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d, checkpoint='manual'); c.save()
            before=copy.deepcopy(c.settings)
            disk=(Path(d)/'settings.json').read_bytes()
            for payload in (None, [], {'mode':'random'}, {'version':True}, {'day':'A'}, {'night':['']}, {'day':[7]}, {'mapping':{'night':'other'}}, {'mapping':{'dawn':'day'}}, {'extra':1}):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    c.dispatch('PUT','/v1/settings',{'model_policy':payload})
                self.assertEqual(c.settings,before)
            with patch.object(Path,'replace',side_effect=OSError('fixture disk failure')):
                with self.assertRaises(OSError):
                    c.dispatch('PUT','/v1/settings',{'model_policy':{'day':['A']},'interval_minutes':30})
            self.assertEqual(c.settings,before)
            self.assertEqual((Path(d)/'settings.json').read_bytes(),disk)
            self.assertEqual(c.checkpoint,'manual')


    def test_migration_partial_edits_and_restart_preserve_preferences(self):
        with tempfile.TemporaryDirectory() as d:
            c = Controller(d, checkpoint='manual')
            c.settings.update(automation_enabled=True, interval_minutes=30, checkpoint='manual')
            c.save()
            c = Controller(d, checkpoint='manual')
            self.assertEqual(c.settings.get('model_policy', {}).get('mode'), 'single')
            before = copy.deepcopy(c.settings)
            c.dispatch('PUT','/v1/settings',{'model_policy':{'day':['A','B','C'],'night':['B','C']}})
            c.dispatch('PUT','/v1/settings',{'model_policy':{'mode':'lighting'}})
            fresh = Controller(d, checkpoint='manual')
            self.assertEqual(fresh.settings['model_policy']['day'], ['A','B','C'])
            self.assertEqual(fresh.settings['model_policy']['night'], ['B','C'])
            self.assertEqual(fresh.settings['model_policy']['mode'], 'lighting')
            for k,v in before.items():
                if k != 'model_policy': self.assertEqual(fresh.settings[k],v)
            self.assertEqual(c.checkpoint,'manual')
            self.assertIsNone(c.render_thread)
