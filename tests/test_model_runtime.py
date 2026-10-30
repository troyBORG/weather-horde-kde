import unittest, tempfile, time
from unittest.mock import patch
from weather_controller import Controller
from model_catalog import PROFILES

class ModelRuntime(unittest.TestCase):
    def test_production_catalog_persistence_and_admission(self):
        self.assertTrue(hasattr(Controller,'enable_reviewed_models'),'production model gate missing')
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d,checkpoint='old');c.settings['checkpoint']='saved.safetensors';c.save()
            c=Controller(d,checkpoint='old')
            models=[dict(id='saved.safetensors',**PROFILES['sdxl'])]
            with patch('model_catalog.discover_models',return_value=models):c.enable_reviewed_models()
            self.assertEqual(c.checkpoint,'saved.safetensors')
            c.guard={'decision':'safe','free_mib':5000,'observed_at':time.time()}
            c.displays=[{'id':'DP-2','width':1080,'height':1920}]
            r=c.dispatch('POST','/v1/render',{'target':'DP-2'})
            self.assertEqual(r['state'],'deferred');self.assertIn('vram',r['reason'])
            c.checkpoint='not-reviewed'
            r=c.dispatch('POST','/v1/render',{'target':'DP-2'})
            self.assertEqual(r['state'],'deferred');self.assertIn('model',r['reason'])
