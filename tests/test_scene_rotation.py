import tempfile, unittest
from unittest.mock import patch
from weather_controller import Controller
from test_night_realism import LOCATION, preview

class SceneRotation(unittest.TestCase):
    def test_settings_inherit_validate_and_persist(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d); c.displays=[{'id':'LEFT','width':512,'height':512}]
            c.dispatch('PUT','/v1/settings',{'scene_kind':'random','scene_overrides':{'LEFT':'river'}})
            self.assertEqual(Controller(d).status()['scene_overrides'],{'LEFT':'river'})
            self.assertTrue(c.status()['capabilities']['scene_rotation'])
            for value in ([], {'LEFT':'bad'}, {'UNKNOWN':'rural'}, {'LEFT':None}):
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'scene_overrides':value})
            c.render_lock.acquire()
            with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'scene_overrides':{}})
            c.render_lock.release()
            c.dispatch('PUT','/v1/settings',{'scene_overrides':{}})
            self.assertEqual(c.status()['scene_overrides'],{})

    def test_cycle_random_receipts_and_equal_size_overrides(self):
        import io
        from PIL import Image
        class Transport:
            def __init__(self): self.graphs=[]
            def queue(self, graph): self.graphs.append(graph); return str(len(self.graphs))
            def inspect(self, job): return 'complete'
            def image(self, job):
                out=io.BytesIO(); Image.new('RGB',(512,512),'navy').save(out,'PNG'); return out.getvalue()
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview', side_effect=lambda loc, **kw: preview(scene_kind=kw['scene_kind'])):
            t=Transport(); c=Controller(d,checkpoint='fixture.safetensors',transport=t,render_guard=lambda:'safe')
            c.settings.update(location=LOCATION,scene_kind='random',scene_overrides={'RIGHT':'river'})
            c.displays=[{'id':x,'width':512,'height':512} for x in ('LEFT','RIGHT')]
            previous=None
            for cycle in range(4):
                c.render_lock.acquire(); c.render_images(c.displays,LOCATION)
                self.assertEqual(c.state,'image_preview_ready',c.last_error)
                actual=c.previews_by_target['LEFT']['scene']['weather_evidence']['scene_kind']
                self.assertNotEqual(actual,'random'); self.assertNotEqual(actual,previous)
                self.assertEqual(c.previews_by_target['RIGHT']['scene']['weather_evidence']['scene_kind'],'river')
                self.assertEqual(c.previews_by_target['LEFT']['scene']['scene_selection']['requested'],'random')
                for _ in range(3): c.status()
                planned=c.build_preview({'target':'all'})
                for entry in planned['target_scenes']:
                    record=c.previews_by_target[entry['target']['id']]
                    self.assertEqual(entry['scene']['weather_evidence']['scene_kind'],record['scene']['weather_evidence']['scene_kind'])
                    self.assertEqual(record['positive'],record['scene']['positive'])
                previous=actual
            # A controller reload keeps the last rendered scene for no-repeat selection.
            restored=Controller(d,checkpoint='fixture.safetensors',transport=t,render_guard=lambda:'safe')
            restored.settings.update(c.settings); restored.displays=c.displays
            restored.render_lock.acquire(); restored.render_images(restored.displays,LOCATION)
            self.assertNotEqual(restored.previews_by_target['LEFT']['scene']['weather_evidence']['scene_kind'],previous)

    def test_shared_weather_and_read_only_random_preview(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d);c.settings.update(location=LOCATION,scene_kind='random',scene_overrides={'RIGHT':'river'})
            c.displays=[{'id':x,'width':512,'height':512} for x in ('LEFT','RIGHT')]
            data={'current':{'time':time.time(),'temperature_2m':50,'weather_code':3,'is_day':1}}
            with patch('weather_controller.fetch_json',return_value=data) as fetch, patch('weather_controller.secrets.choice',side_effect=AssertionError('read must not rotate')):
                planned=c.build_preview({'target':'all'})
                self.assertEqual(fetch.call_count,1)
                self.assertTrue(planned['target_scenes'][0]['scene']['scene_selection']['provisional'])
                self.assertEqual(planned['target_scenes'][1]['scene']['scene_selection']['resolved'],'river')
                for _ in range(5): c.status()

    def test_river_scene_has_coherent_anchor(self):
        p=preview(scene_kind='river')
        self.assertIn('river',p['positive'])
        self.assertEqual(p['weather_evidence']['scene_kind'],'river')

if __name__=='__main__': unittest.main()
