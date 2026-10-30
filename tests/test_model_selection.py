import unittest, tempfile, struct, json
from pathlib import Path
from unittest.mock import patch
import weather_controller as wc

class ModelSelection(unittest.TestCase):
    def test_reviewed_headers_and_identifiers(self):
        self.assertTrue(callable(getattr(wc.Controller,'refresh_models',None)), 'model discovery missing')
        from model_catalog import inspect_model, catalog
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.safetensors'
            def write(context):
                h={'model.diffusion_model.input_blocks.0.0.weight':{'shape':[320,4,3,3]},'model.diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight':{'shape':[640,context]},'first_stage_model.decoder.conv_out.weight':{'shape':[3,128,3,3]},'conditioner.embedders.1.model.text_projection':{'shape':[1280,1280]}}
                raw=json.dumps(h).encode();p.write_bytes(struct.pack('<Q',len(raw))+raw)
            write(2048)
            self.assertEqual(inspect_model(p)['architecture'],'sdxl')
            options=catalog({'natvisNaturalVision_v27.safetensors':str(p),'pony_diffusion_xl.safetensors':str(p),'foreign.safetensors':str(p)})
            self.assertEqual([m['id'] for m in options],['natvisNaturalVision_v27.safetensors'])
            write(4096)
            with self.assertRaises(ValueError): inspect_model(p)
    def test_selection_seed_profile_and_busy(self):
        self.assertTrue(callable(getattr(wc.Controller,'refresh_models',None)), 'model discovery missing')
        from comfy_preview import build_workflow
        from model_catalog import PROFILES
        with tempfile.TemporaryDirectory() as d:
            c=wc.Controller(d,checkpoint='old.safetensors')
            c.models=[dict(id='exact.safetensors',**PROFILES['sdxl'])]
            with patch.object(c,'refresh_models',return_value=c.models):
                c.dispatch('PUT','/v1/settings',{'checkpoint':'exact.safetensors','comparison_seed':123})
                self.assertEqual(c.checkpoint,'exact.safetensors')
                c.render_lock.acquire()
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'checkpoint':'exact.safetensors'})
                c.render_lock.release()
                with self.assertRaises(ValueError):c.dispatch('PUT','/v1/settings',{'checkpoint':'foreign'})
                with self.assertRaises(ValueError):c.dispatch('PUT','/v1/settings',{'comparison_seed':-1})
            for kind,profile in PROFILES.items():
                w=build_workflow('exact.safetensors','night','sunset',1080,1920,123,profile=profile)
                self.assertLessEqual(w['4']['inputs']['width']*w['4']['inputs']['height'],profile['max_pixels'])
                self.assertEqual(w['5']['inputs']['seed'],123)
                self.assertEqual(w['5']['inputs']['cfg'],profile['cfg'])
