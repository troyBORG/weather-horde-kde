"""Offline prompt contracts, not pixel-placement or live GPU evidence."""
import unittest
import scene
from test_night_realism import preview

class CompositionTests(unittest.TestCase):
    def test_framing_setting_is_persisted_validated_and_busy_locked(self):
        import tempfile
        from weather_controller import Controller
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d)
            self.assertEqual(c.status().get('framing'), 'auto')
            self.assertTrue(c.status()['capabilities'].get('composition_controls'))
            for value in ('natural','desktop_portrait','auto'):
                c.dispatch('PUT','/v1/settings',{'framing':value})
                self.assertEqual(Controller(d).status()['framing'],value)
            for value in ('bad',None,[],True):
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'framing':value})
            c.render_lock.acquire()
            try:
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'framing':'natural'})
            finally: c.render_lock.release()

    def test_portrait_street_is_widget_aware_without_changing_weather(self):
        self.assertTrue(hasattr(scene, 'compose_for_target'), 'Missing per-target composition')
        base = preview(scene_kind='urban')
        p = scene.compose_for_target(base, 1080, 1920)
        self.assertEqual(p['composition']['profile'], 'desktop_portrait')
        self.assertEqual(p['composition']['horizon_y_fraction'], [.55, .65])
        for text in ('55-65%', 'above the lower third', 'lower 25-30%', 'camera aimed slightly downward', 'no oversized sky', 'soft top corners', 'not an overhead or aerial view'):
            self.assertIn(text, p['positive'])
        self.assertEqual(p['weather_evidence'], base['weather_evidence'])
        self.assertNotIn('composition', base)

    def test_landscape_square_and_nonurban_auto_are_unchanged(self):
        for kind in ('urban', 'rural', 'townpark', 'woodland'):
            base = preview(scene_kind=kind)
            for size in ((1920,1080), (1080,1080), (1080,1920)):
                if kind == 'urban' and size == (1080,1920): continue
                p = scene.compose_for_target(base, *size)
                self.assertEqual(p['positive'], base['positive'])
                self.assertEqual(p['negative'], base['negative'])
                self.assertEqual(p['composition']['profile'], 'natural')
        base = preview(scene_kind='urban')
        self.assertEqual(scene.compose_for_target(base,1080,1920,'natural')['positive'],base['positive'])
        for kind in ('rural', 'townpark', 'woodland'):
            p = scene.compose_for_target(preview(scene_kind=kind),1080,1920,'desktop_portrait')
            self.assertIn('natural horizon', p['positive'])
            self.assertNotIn('town roofs', p['positive'])
        for size in ((0,1920), (True,1920)):
            with self.assertRaises(ValueError): scene.compose_for_target(base,*size)
        with self.assertRaises(ValueError): scene.compose_for_target(base,1080,1920,'bad')

    def test_mixed_render_targets_have_distinct_graphs_and_matching_receipts(self):
        import io, tempfile
        from unittest.mock import patch
        from PIL import Image
        from weather_controller import Controller
        from test_night_realism import LOCATION
        class Transport:
            def __init__(self): self.graphs=[]
            def queue(self, graph): self.graphs.append(graph); return str(len(self.graphs))
            def inspect(self, job): return 'complete'
            def image(self, job):
                graph=self.graphs[int(job)-1]
                dims=graph.get('10',graph['4'])['inputs']
                out=io.BytesIO(); Image.new('RGB',(dims['width'],dims['height']),'navy').save(out,'PNG')
                return out.getvalue()
        base=preview(scene_kind='urban')
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview', return_value=base) as weather:
            transport=Transport()
            c=Controller(d, checkpoint='approved.safetensors',transport=transport, render_guard=lambda:'safe')
            c.settings.update(location=LOCATION, scene_kind='urban', comparison_seed=123)
            c.displays=[{'id':'LEFT','width':1080,'height':1920},{'id':'RIGHT','width':1920,'height':1080}]
            p=c.build_preview({'target':'all'})
            self.assertIn('target_scenes',p, 'Prompt preview must expose per-target framing before graph creation')
            self.assertEqual([x['scene']['composition']['profile'] for x in p['target_scenes']], ['desktop_portrait','natural'])
            c.render_lock.acquire()  # render endpoint normally owns this lock
            c.render_images(c.displays,LOCATION)
            self.assertEqual(c.state,'image_preview_ready',c.last_error)
            self.assertEqual(len(transport.graphs),2)
            self.assertEqual(weather.call_count,2, 'One weather snapshot per batch, not one fetch per monitor')
            for target,graph,planned in zip(c.displays,transport.graphs,p['target_scenes']):
                receipt=c.previews_by_target[target['id']]
                self.assertEqual(graph['2']['inputs']['text'],planned['scene']['positive'])
                self.assertEqual(receipt['scene']['composition'],planned['scene']['composition'])
                self.assertEqual(receipt['positive'],graph['2']['inputs']['text'])
                self.assertEqual(receipt['negative'],graph['3']['inputs']['text'])
                self.assertEqual(graph['5']['inputs']['seed'],123)
                self.assertEqual((receipt['width'],receipt['height']),(target['width'],target['height']))
                if '10' in graph: self.assertEqual(graph['10']['inputs']['crop'],'disabled')
            self.assertEqual(transport.graphs[1]['2']['inputs']['text'],base['positive'])
            self.assertNotEqual(transport.graphs[0]['2']['inputs']['text'],base['positive'])
