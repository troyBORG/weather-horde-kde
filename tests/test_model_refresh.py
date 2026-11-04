import copy
import tempfile
import unittest
from unittest.mock import Mock, patch
import weather_controller as wc
from model_catalog import Catalog, PROFILES


class ModelRefreshTests(unittest.TestCase):
    def test_explicit_get_refresh_preserves_all_preferences_and_does_not_generate(self):
        with tempfile.TemporaryDirectory() as d:
            c=wc.Controller(d,checkpoint='saved.safetensors')
            c.transport=Mock(); c.comfy_service=Mock()
            c.models=[dict(id='old.safetensors',**PROFILES['sdxl'])]
            c.save(); before=(c.root/'settings.json').read_bytes(); settings=copy.deepcopy(c.settings)
            result=Catalog();result.append(dict(id='sub/new.safetensors',**PROFILES['sdxl']))
            result.excluded=[dict(id='other.safetensors',reason='Unsupported architecture')]
            with patch('model_catalog.discover_models',return_value=result):
                status=c.dispatch('GET','/v1/models/refresh',{})
            self.assertEqual(status['models'],result)
            self.assertEqual(status['model_exclusions'],result.excluded)
            self.assertEqual(c.checkpoint,'saved.safetensors')
            self.assertEqual(settings,c.settings);self.assertEqual(before,(c.root/'settings.json').read_bytes())
            self.assertEqual(c.transport.mock_calls,[]);c.comfy_service.ensure_ready.assert_not_called()

    def test_missing_local_or_live_model_blocks_worker_without_submission(self):
        import time
        from comfy_preview import SubmissionDeferred
        for local_missing in (True,False):
            with self.subTest(local_missing=local_missing), tempfile.TemporaryDirectory() as d:
                c=wc.Controller(d,checkpoint='saved.safetensors',transport=Mock(),render_guard=lambda:'safe')
                c.enforce_models=True;c.guard={'decision':'safe','total_mib':24576,'free_mib':24000,'observed_at':time.time()}
                c.settings['location']={'town':'fixture'};c.displays=[{'id':'TEST','width':64,'height':128}]
                c.models=[dict(id=c.checkpoint,**PROFILES['sdxl'])]
                c.transport.validate_checkpoint.side_effect=SubmissionDeferred('Missing from live loader')
                with patch('model_catalog.discover_models',return_value=[] if local_missing else c.models):
                    response=c.dispatch('POST','/v1/render',{'target':'TEST','force':True})
                    self.assertEqual(response['state'],'queued')
                    c.render_thread.join(3)
                self.assertEqual(c.state,'deferred');c.transport.queue.assert_not_called()
                self.assertFalse((c.root/'inflight.json').exists())
                if local_missing:c.transport.validate_checkpoint.assert_not_called()
                else:c.transport.validate_checkpoint.assert_called_once_with('saved.safetensors')

    def test_saved_missing_model_never_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            c=wc.Controller(d,checkpoint='default');c.settings['checkpoint']='missing.safetensors'
            with patch('model_catalog.discover_models',return_value=[]):c.enable_reviewed_models()
            self.assertEqual(c.checkpoint,'missing.safetensors');self.assertEqual(c.model_gate(),'unreviewed_model')

    def test_selection_checks_live_loader_and_failure_clears_stale_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            c=wc.Controller(d,checkpoint='saved');c.enforce_models=True;c.transport=Mock()
            result=[dict(id='sub/new.safetensors',**PROFILES['sdxl'])]
            c.transport.validate_checkpoint.side_effect=ValueError('Missing from live loader')
            with patch('model_catalog.discover_models',return_value=result):
                with self.assertRaises(ValueError):c.dispatch('PUT','/v1/settings',{'checkpoint':'sub/new.safetensors'})
            self.assertEqual(c.checkpoint,'saved')
            c.transport.validate_checkpoint.assert_called_once_with('sub/new.safetensors')
            with patch('model_catalog.discover_models',side_effect=ValueError('bad config')):
                with self.assertRaises(ValueError):c.refresh_models()
            self.assertEqual(c.models,[])
