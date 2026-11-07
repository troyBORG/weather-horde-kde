import json
import struct
import tempfile
import unittest
from pathlib import Path

import model_catalog as mc


def checkpoint(path, context=2048, metadata=None):
    shapes = {
        'model.diffusion_model.input_blocks.0.0.weight': [320,4,3,3],
        'model.diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight': [640,context],
        'first_stage_model.decoder.conv_out.weight': [3,128,3,3],
        'conditioner.embedders.1.model.text_projection': [1280,1280],
    }
    import math
    header = {}; offset = 0
    for key, shape in shapes.items():
        end = offset + math.prod(shape)*2
        header[key] = dict(shape=shape,dtype='F16',data_offsets=[offset,end]); offset=end
    if metadata is not None: header['__metadata__']=metadata
    raw=json.dumps(header).encode()
    with path.open('wb') as stream:
        stream.write(struct.pack('<Q',len(raw))+raw); stream.truncate(8+len(raw)+offset)
    return header


class DiscoveryTests(unittest.TestCase):
    def test_report_renamed_subdirectory_and_clear_exclusions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); good=root/'renamed.safetensors'; checkpoint(good)
            bad=root/'bad.safetensors'; checkpoint(bad,4096)
            family=root/'family.safetensors'; checkpoint(family,metadata={'modelspec.title':'Pony fine tune'})
            malformed=root/'malformed.safetensors'; malformed.write_bytes(struct.pack('<Q',5)+b'null ')
            result=mc.catalog({'sub/renamed.safetensors':str(good),'bad.safetensors':str(bad),
                               'family.safetensors':str(family),'malformed.safetensors':str(malformed),'pickle.ckpt':str(root/'pickle.ckpt')})
            self.assertEqual([m['id'] for m in result],['sub/renamed.safetensors'])
            reasons={x['id']:x['reason'] for x in result.excluded}
            self.assertIn('conditioning',reasons['bad.safetensors'])
            self.assertIn('family',reasons['family.safetensors'])
            self.assertIn('header',reasons['malformed.safetensors'])
            self.assertIn('pickle',reasons['pickle.ckpt'])

    def test_malformed_shapes_offsets_and_short_headers(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.safetensors'
            for data in [b'',struct.pack('<Q',2**40),struct.pack('<Q',2)+b'[]',struct.pack('<Q',20)+b'{}']:
                p.write_bytes(data)
                with self.assertRaises(ValueError): mc.inspect_model(p)
            h=checkpoint(p)
            h['model.diffusion_model.input_blocks.0.0.weight']['shape']=[True,4,3,3]
            raw=json.dumps(h).encode();p.write_bytes(struct.pack('<Q',len(raw))+raw)
            with self.assertRaises(ValueError): mc.inspect_model(p)

    def test_family_hints_are_explained_not_architecture_claims(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'generic.safetensors';checkpoint(p,metadata={'hash':'abclcm123'})
            result=mc.catalog({'generic.safetensors':str(p),'customPony_v1.safetensors':str(p)})
            self.assertEqual([m['id'] for m in result],['generic.safetensors'])
            self.assertIn('identifier hint',result.excluded[0]['reason'])
            result=mc.catalog({'noobVPencil.safetensors':str(p)})
            self.assertEqual(result,[])
            self.assertIn('family',result.excluded[0]['reason'])

    def test_configured_dirs_refresh_duplicates_and_symlink_boundary(self):
        import os, sys
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);app=root/'app';app.mkdir();(app/'.venv/bin').mkdir(parents=True)
            (app/'.venv/bin/python').symlink_to(sys.executable)
            a=root/'a';b=root/'b';a.mkdir();b.mkdir();(b/'sub').mkdir()
            checkpoint(a/'same.safetensors',4096);checkpoint(b/'same.safetensors')
            checkpoint(b/'sub/renamed.safetensors')
            (a/'outside').symlink_to(root,target_is_directory=True)
            (app/'utils').mkdir();(app/'utils/__init__.py').write_text('')
            (app/'utils/extra_config.py').write_text('def load_extra_path_config(path): pass\n')
            (app/'folder_paths.py').write_text('import pathlib\nroots='+repr([str(a),str(b)])+'\ndef get_folder_paths(kind): return roots\ndef get_filename_list(kind): raise AssertionError("unbounded symlink-following scan forbidden")\ndef get_full_path(kind,name):\n for root in roots:\n  p=pathlib.Path(root)/name\n  if p.is_file(): return str(p)\n')
            with patch.object(mc,'COMFY',app):
                result=mc.discover_models()
                self.assertEqual([m['id'] for m in result],['sub/renamed.safetensors'])
                self.assertTrue(any(e['id']=='same.safetensors' and 'conditioning' in e['reason'] for e in result.excluded))
                self.assertTrue(any('symlink' in e['reason'] for e in result.excluded))
                checkpoint(a/'new.safetensors')
                self.assertEqual([m['id'] for m in mc.discover_models()],['new.safetensors','sub/renamed.safetensors'])

    def test_unavailable_comfy_has_short_actionable_error(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d, patch.object(mc,'COMFY',Path(d)):
            with self.assertRaisesRegex(ValueError,'discovery unavailable'):
                mc.discover_models()

    def test_traversal_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'models';root.mkdir(); outside=Path(d)/'outside.safetensors';checkpoint(outside)
            (root/'escape.safetensors').symlink_to(outside)
            result=mc.catalog({'../outside.safetensors':str(outside),'escape.safetensors':str(root/'escape.safetensors')},roots=[root])
            self.assertEqual(result,[])
            self.assertEqual(len(result.excluded),2)
            self.assertTrue(all('path' in e['reason'].lower() for e in result.excluded))
