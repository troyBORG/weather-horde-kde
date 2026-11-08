import io
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from weather_controller import Controller
from model_catalog import PROFILES
from test_night_realism import preview, LOCATION


class Transport:
    def __init__(self): self.graphs=[]; self.live=['day','night']; self.on_queue=lambda:None
    def validate_checkpoint(self, identifier):
        from comfy_preview import SubmissionDeferred
        if identifier not in self.live: raise SubmissionDeferred('Checkpoint missing')
    def checkpoint_names(self): return self.live
    def queue(self, graph):
        self.graphs.append(graph); self.on_queue(); return str(len(self.graphs))
    def inspect(self, job): return 'complete'
    def image(self, job):
        graph=self.graphs[int(job)-1]; dims=graph.get('10',graph['4'])['inputs']
        out=io.BytesIO(); Image.new('RGB',(dims['width'],dims['height']),'navy').save(out,'PNG'); return out.getvalue()


class BatchTests(unittest.TestCase):
    def controller(self, d):
        t=Transport(); c=Controller(d,checkpoint='manual',transport=t,render_guard=lambda:'safe')
        c.settings.update(location=LOCATION,comparison_seed=123)
        c.settings['model_policy'].update(mode='lighting',day=['day'],night=['night'])
        c.models=[dict(id='day',**PROFILES['sd15']),dict(id='night',**PROFILES['sdxl'])]
        c.displays=[{'id':'LEFT','width':64,'height':128},{'id':'RIGHT','width':128,'height':64}]
        c.guard={'decision':'safe','total_mib':24576,'free_mib':24000,'observed_at':time.time()}
        return c,t

    def test_retry_context_survives_restart_without_stealing_coalesced_work(self):
        with tempfile.TemporaryDirectory() as d:
            c,t=self.controller(d); c.settings.update(automation_kind='image_preview', automation_enabled=True, catch_up_refresh=True); c.save()
            s=c.scheduler; s.configure(True,'image_preview',['LEFT','RIGHT'],1800)
            s.request('interval',['LEFT','RIGHT']); s.observe_activity(True,True,0)
            a=s.next_action(0,0); s.active['model_batch']={'selection':{'checkpoint':'night'}}
            s.complete('LEFT',a['generation_id'],1)
            s.fail('fixture',monotonic_now=1); c.save_refresh()
            restarted=Controller(d,checkpoint='manual',transport=t,render_guard=lambda:'safe')
            restarted.displays=c.displays; restarted.guard=c.guard
            with patch.object(restarted.session_activity,'poll',return_value=False):
                restarted.catchup_tick(time.time(),100)
            self.assertIsNotNone(restarted.scheduler.retry_batch)
            self.assertEqual(restarted.scheduler.retry_batch['generation_id'],a['generation_id'])
            s.request('interval',['LEFT']); s.observe_activity(True,True,61)
            retry=s.next_action(2,61)
            self.assertEqual(retry['targets'],['RIGHT'])
            s.complete('RIGHT',retry['generation_id'],2)
            new=s.next_action(3,61)
            self.assertEqual(new['targets'],['LEFT']); self.assertNotEqual(new['generation_id'],a['generation_id'])

    def test_partial_retry_keeps_checkpoint_and_scene_across_boundary(self):
        base=preview(); base['weather_evidence']['daypart']='night'
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview',return_value=base) as weather:
            c,t=self.controller(d); c.enforce_models=True
            c.settings['automation_kind']='image_preview'
            s=c.scheduler; s.configure(True,'image_preview',['LEFT','RIGHT'],1800)
            s.request('interval',['LEFT','RIGHT']); s.observe_activity(True,True,0)
            first=s.next_action(time.time(),0)
            t.on_queue=lambda:t.live.clear()
            with patch.object(c,'refresh_models',return_value=c.models):
                c.render_lock.acquire(); c.render_images(c.displays,LOCATION,refresh_id=first['generation_id'])
            self.assertEqual(len(t.graphs),1)
            self.assertEqual(sorted(s.pending),['RIGHT'])
            base['weather_evidence']['daypart']='daytime'; t.live=['day','night']; t.on_queue=lambda:None
            s.observe_activity(True,True,s.retry_at)
            second=s.next_action(time.time(),s.retry_at)
            self.assertEqual(second['generation_id'],first['generation_id'])
            with patch.object(c,'refresh_models',return_value=c.models):
                c.render_lock.acquire(); c.render_images([c.displays[1]],LOCATION,refresh_id=second['generation_id'])
            self.assertEqual(c.state,'image_preview_ready',c.last_error)
            self.assertEqual([g['1']['inputs']['ckpt_name'] for g in t.graphs],['night','night'])
            self.assertEqual(weather.call_count,1)
            self.assertEqual(c.previews_by_target['RIGHT']['scene']['model_selection']['daypart'],'night')

    def test_live_intersection_empty_pool_and_disappearing_model_defer(self):
        base=preview(); base['weather_evidence']['daypart']='night'
        for live, saved in [(['night'],['gone','night']), (['day'],['night']), (['day','night'],[])]:
            with self.subTest(live=live,saved=saved), tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview',return_value=base):
                c,t=self.controller(d); c.enforce_models=True; t.live=live
                c.settings['model_policy']['night']=saved
                with patch.object(c,'refresh_models',return_value=c.models):
                    result=c.dispatch('POST','/v1/render',{'target':'all'})
                    self.assertEqual(result['state'],'queued')
                    c.render_thread.join(5)
                if 'night' in live and saved:
                    self.assertEqual(c.state,'image_preview_ready',c.last_error)
                else:
                    self.assertEqual(c.state,'deferred',c.last_error)
                    self.assertIn('pool',c.last_error); self.assertFalse(t.graphs)
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview',return_value=base):
            c,t=self.controller(d); c.enforce_models=True
            t.on_queue=lambda:t.live.clear()
            with patch.object(c,'refresh_models',return_value=c.models):
                c.render_lock.acquire(); c.render_images(c.displays,LOCATION)
            self.assertEqual(len(t.graphs),1)
            self.assertEqual(c.state,'deferred',c.last_error)

    def test_both_graphs_and_receipts_use_frozen_pool_not_manual(self):
        base=preview(); base['weather_evidence']['daypart']='night'
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.weather_preview',return_value=base):
            c,t=self.controller(d)
            t.on_queue=lambda:c.settings['model_policy'].update(night=['day'])
            c.render_lock.acquire(); c.render_images(c.displays,LOCATION)
            self.assertEqual(c.state,'image_preview_ready',c.last_error)
            self.assertEqual(len(t.graphs),2)
            self.assertEqual([g['1']['inputs']['ckpt_name'] for g in t.graphs],['night','night'])
            self.assertEqual(c.checkpoint,'manual')
            for r in c.previews_by_target.values():
                self.assertEqual(r['scene']['model_selection']['pool'],'night')
                self.assertEqual(r['scene']['model_selection']['daypart'],'night')
                self.assertEqual(r['scene']['checkpoint'],'night')
                self.assertEqual(r['scene']['inference_profile']['architecture'],'sdxl')
