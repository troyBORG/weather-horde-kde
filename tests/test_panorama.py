"""Synthetic pixels, not GPU/owner-session acceptance."""
import io
import tempfile
import unittest
from PIL import Image


class PanoramaController(unittest.TestCase):
    def test_one_master_all_crops_before_apply_and_settings(self):
        from unittest.mock import patch
        from weather_controller import Controller
        from test_night_realism import LOCATION, preview
        class Transport:
            def __init__(self): self.graphs = []
            def queue(self, graph): self.graphs.append(graph); return 'fixture'
            def inspect(self, job): return 'complete'
            def image(self, job):
                stream = io.BytesIO(); Image.new('RGB',(1024,512),'navy').save(stream,'PNG')
                return stream.getvalue()
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.time.time', return_value=preview()['observed_at']), patch('weather_controller.weather_preview', side_effect=lambda loc, **kw: preview(**{k:v for k,v in kw.items() if k != 'fetch'})):
            transport = Transport()
            c = Controller(d, checkpoint='fixture.safetensors', transport=transport, render_guard=lambda:'safe')
            c.displays = [dict(id='A',x=0,y=0,width=512,height=512,scale=1), dict(id='B',x=512,y=0,width=512,height=512,scale=1)]
            c.settings['location'] = LOCATION
            self.assertFalse(c.status().get('connected_panorama', False))
            c.dispatch('PUT','/v1/settings',dict(connected_panorama=True, scene_overrides={'B':'river'}))
            self.assertTrue(Controller(d).status()['connected_panorama'])
            self.assertEqual(c.target_displays({'target':'A'}), c.displays)
            applied=[]
            class Wallpaper:
                def preflight(self, target): pass
                def apply(self, target, identifier, guard):
                    self_test.assertEqual(set(c.previews_by_target), {'A','B'})
                    self_test.assertEqual(identifier, c.previews_by_target[target['id']]['id'])
                    applied.append(target['id']); return {'verified':True,'state':'applied'}
            self_test = self
            c.wallpaper = Wallpaper()
            c.render_lock.acquire(); c.render_images(c.displays, LOCATION, auto_apply=True)
            self.assertEqual(c.state, 'wallpapers_applied', c.last_error)
            self.assertEqual(len(transport.graphs), 1)
            self.assertEqual(applied, ['A','B'])
            self.assertNotEqual(c.previews_by_target['A']['id'], c.previews_by_target['B']['id'])
            for record in c.previews_by_target.values():
                self.assertEqual(record['scene']['scene_selection']['resolved'], 'rural')
                self.assertEqual(record['panorama']['layout']['size'], [1024,512])
            self.assertEqual(c.settings['scene_overrides'], {'B':'river'})
            restored=Controller(d,checkpoint='fixture.safetensors',transport=transport,render_guard=lambda:'safe')
            restored.settings['scene_kind']='random'; restored.displays=c.displays
            def choose(kinds):
                self.assertNotIn('rural',kinds)
                return kinds[0]
            with patch('weather_controller.secrets.choice',side_effect=choose):
                restored.target_scene_previews(LOCATION,restored.displays,generation=True)
            c.displays[1]['y'] = 64
            with self.assertRaisesRegex(ValueError, 'layout changed'):
                c.dispatch('POST','/v1/apply',dict(target='A',preview_id=c.previews_by_target['A']['id'],confirmation='Apply this validated preview'))
            with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'connected_panorama':'yes'})


class PanoramaSafety(unittest.TestCase):
    def test_connected_scheduler_preflights_even_fresh_other_output(self):
        from unittest.mock import Mock
        from weather_controller import Controller
        import time
        from test_night_realism import LOCATION
        for selected in ('A','all'):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as d:
                c=Controller(d,checkpoint='fixture.safetensors',transport=Mock(),render_guard=lambda:'safe')
                c.settings.update(connected_panorama=True,automation_target=selected,automation_enabled=True,automation_kind='image_wallpaper',catch_up_refresh=True,location=LOCATION)
                c.displays=[dict(id=name,x=x,y=0,width=512,height=512,scale=1) for name,x in [('A',0),('B',512)]]
                now=time.time()
                c.guard={'decision':'safe','observed_at':now}
                c.session_activity=Mock(); c.session_activity.poll.return_value=True
                c.scheduler.success['image_wallpaper']={'B':now}
                calls=[]
                def preflight(display):
                    calls.append(display['id'])
                    if display['id']=='B': raise ValueError('pending B transaction')
                c.wallpaper=Mock(); c.wallpaper.preflight.side_effect=preflight
                c.dispatch=Mock(return_value={'state':'queued'})
                c.tick(now=now,monotonic_now=10)
                self.assertEqual(calls,['A','B'])
                c.dispatch.assert_not_called()
                self.assertIn('pending B',c.last_error)

    def test_direct_auto_preflights_before_startup_or_submission(self):
        from unittest.mock import Mock
        from weather_controller import Controller
        from test_night_realism import LOCATION
        with tempfile.TemporaryDirectory() as d:
            transport=Mock()
            c=Controller(d,checkpoint='fixture.safetensors',transport=transport,render_guard=lambda:'safe')
            c.settings['connected_panorama']=True
            c.displays=[dict(id='A',x=0,y=0,width=512,height=512,scale=1)]
            c.wallpaper=Mock(); c.wallpaper.preflight.side_effect=ValueError('pending transaction')
            c.comfy_service=Mock()
            c.render_lock.acquire(); c.render_images(c.displays,LOCATION,auto_apply=True)
            self.assertIn('pending transaction',c.last_error)
            c.comfy_service.ensure_ready.assert_not_called()
            transport.queue.assert_not_called()

    def test_late_second_crop_guard_quarantines_entire_batch(self):
        from unittest.mock import patch
        from weather_controller import Controller
        from test_night_realism import LOCATION, preview
        from pathlib import Path
        import json
        class Transport:
            def queue(self, graph): return 'fixture'
            def inspect(self, job): return 'complete'
            def image(self, job):
                stream=io.BytesIO(); Image.new('RGB',(1024,512)).save(stream,'PNG'); return stream.getvalue()
        for unsafe in ('paused_game','active_client_counters_unavailable','layout_changed'):
            with self.subTest(unsafe=unsafe), tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview', side_effect=lambda loc, **kw: preview()):
                c=Controller(d,checkpoint='fixture.safetensors',transport=Transport(),render_guard=lambda:'safe')
                c.settings['connected_panorama']=True
                c.displays=[dict(id=name,x=x,y=0,width=512,height=512,scale=1) for name,x in [('A',0),('B',512)]]
                original=c.store.save
                count=[]
                def save(*args, **kwargs):
                    count.append(1)
                    if len(count)==2:
                        if unsafe == 'layout_changed': c.displays[1]['y'] = 64
                        else: c.render_guard=lambda:unsafe
                    return original(*args,**kwargs)
                c.store.save=save
                from unittest.mock import Mock
                c.wallpaper=Mock()
                # Inject the observation through the exact guard used by the batch.
                c.render_lock.acquire(); c.render_images(c.displays,LOCATION,policy=(lambda:c.render_guard(),{}),auto_apply=True)
                self.assertEqual(c.state,'quarantined',c.last_error)
                self.assertIn(unsafe,c.last_error)
                self.assertEqual(c.previews_by_target,{})
                self.assertIsNone(c.store.latest())
                records=[json.loads(p.read_text()) for p in Path(d,'renders').glob('*/metadata.json')]
                self.assertEqual(len(records),2)
                self.assertTrue(all(r['quarantined'] for r in records))

    def test_unsafe_admission_submits_nothing(self):
        from unittest.mock import patch
        from weather_controller import Controller
        from test_night_realism import LOCATION, preview
        class Transport:
            def queue(self, graph): raise AssertionError('must not submit')
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview', side_effect=lambda loc, **kw: preview()):
            c=Controller(d,checkpoint='fixture.safetensors',transport=Transport(),render_guard=lambda:'unknown')
            c.settings['connected_panorama']=True
            c.displays=[dict(id='A',x=0,y=0,width=512,height=512,scale=1)]
            c.render_lock.acquire(); c.render_images(c.displays,LOCATION)
            self.assertEqual(c.state,'deferred',c.last_error)
            self.assertEqual(c.previews_by_target,{})


class PanoramaGeometry(unittest.TestCase):
    def test_geometry_validation_and_bounded_master(self):
        from panorama import plan_layout, crop_master
        base=dict(id='A',x=0,y=0,width=1440,height=2560,scale=1)
        for field,value in [('x',None),('y',True),('scale',float('nan')),('scale',0),('width',0)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan_layout([dict(base,**{field:value})])
        with self.assertRaises(ValueError): plan_layout([base,base])
        plan=plan_layout([base,dict(id='B',x=1440,y=560,width=2560,height=1440,scale=1)])
        self.assertEqual(plan['logical_bounds'],[0,0,4000,2560])
        self.assertLessEqual(plan['size'][0]*plan['size'][1],9000000)
        self.assertGreater(plan['outputs'][1]['box'][1],0)
        with self.assertRaises(ValueError): crop_master(b'not an image',plan)

    def test_rotation_is_applied_once_by_live_parser(self):
        from displays import parse_outputs
        from panorama import plan_layout
        payload={'outputs':[dict(name='P',connected=True,enabled=True,currentModeId='1',modes=[dict(id='1',size=dict(width=1920,height=1080))],rotation=2,scale=1.5,pos=dict(x=-720,y=100))]}
        outputs=parse_outputs(payload)
        plan=plan_layout(outputs)
        self.assertEqual(plan['logical_bounds'],[-720,100,720,1280])
        self.assertEqual((plan['outputs'][0]['width'],plan['outputs'][0]['height']),(1080,1920))

    def test_offset_scaled_native_crops(self):
        import panorama
        targets = [dict(id='portrait', x=-64, y=-32, width=64, height=128, scale=1),
                   dict(id='landscape', x=0, y=0, width=128, height=64, scale=2)]
        plan = panorama.plan_layout(targets)
        self.assertEqual(plan['logical_bounds'], [-64, -32, 128, 128])
        self.assertEqual(plan['density'], 2)
        self.assertEqual(plan['size'], [256, 256])
        image = Image.new('RGB', tuple(plan['size']))
        for y in range(image.height):
            for x in range(image.width): image.putpixel((x,y), (x,y,0))
        raw = io.BytesIO(); image.save(raw, 'PNG')
        crops = panorama.crop_master(raw.getvalue(), plan)
        with Image.open(io.BytesIO(crops['landscape'])) as right:
            self.assertEqual(right.size, (128,64))
            self.assertEqual(right.getpixel((0,0)), (128,64,0))
            self.assertEqual(right.getpixel((127,63)), (255,127,0))
        with Image.open(io.BytesIO(crops['portrait'])) as left:
            self.assertEqual(left.size, (64,128))
            self.assertLess(left.getpixel((0,0))[0], 3)
            self.assertGreater(left.getpixel((63,127))[1], 252)
