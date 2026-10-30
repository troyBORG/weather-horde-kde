"""Cold manual override uses frozen activity consent, never skips hard gates."""
import tempfile, time, unittest
from unittest.mock import patch
from weather_controller import Controller
from test_preview_pipeline import Transport

class ColdOverrideTests(unittest.TestCase):
    def run_case(self, free=24000, enabled=True, identity=True, expire=False):
        with tempfile.TemporaryDirectory() as td:
            t=Transport(); started=[]
            t.listener=None
            t.owned_gpu_pid=lambda:123 if started and identity else None
            t.request=lambda path: {'system':{}}
            queue=t.queue
            def checked_queue(workflow):
                self.assertEqual(t.owned_gpu_pid(),123)
                return queue(workflow)
            t.queue=checked_queue
            c=Controller(td,checkpoint='approved',transport=t,managed_comfy=True,render_guard=lambda:c.guard['decision'],poll_seconds=0)
            c.comfy_service.startup_seconds=.01
            c.displays=[{'id':'DP-2','width':64,'height':128}]
            c.settings['location']={'town':'fixture'}
            c.guard={'decision':'unknown','reason':'unrecognized_gpu_client','free_mib':free,'observed_at':time.time()}
            if enabled: c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})
            def start(*args):
                started.append(args);t.listener=(123,1000,42)
                if expire: c.override_generation += 1  # explicit OFF revokes the frozen job
            def unit(): return {'LoadState':'loaded','ActiveState':'active' if started else 'inactive','MainPID':'123' if started else '0'}
            with patch('weather_controller.collect',return_value=(c.guard,None)), patch('weather_controller.weather_preview',return_value={'positive':'fixture','negative':'fixture'}), patch('comfy_service.port_occupied',return_value=False), patch.object(c.comfy_service,'unit',side_effect=unit), patch.object(c.comfy_service,'command',side_effect=start):
                result=c.dispatch('POST','/v1/render',{'target':'DP-2','force':True})
                if c.render_thread:
                    c.render_thread.join(3)
                    self.assertFalse(c.render_thread.is_alive())
                return result,c.state,started,t.calls

    def test_authorized_cold_unknown_starts_then_verifies_before_queue(self):
        result,state,starts,calls=self.run_case()
        self.assertEqual(result['state'],'queued')
        self.assertEqual(state,'image_preview_ready')
        self.assertEqual(starts,[('start','--no-block','weather-horde-comfy.service')])
        self.assertEqual(calls.count('queue'),1)

    def test_no_override_or_unknown_low_vram_never_starts(self):
        for kwargs in ({'enabled':False},{'free':None},{'free':100}):
            with self.subTest(kwargs=kwargs):
                result,state,starts,calls=self.run_case(**kwargs)
                self.assertEqual(result['state'],'deferred')
                self.assertEqual(starts,[]);self.assertEqual(calls,[])

    def test_failed_identity_or_expired_consent_never_submits(self):
        for kwargs in ({'identity':False},{'expire':True}):
            with self.subTest(kwargs=kwargs):
                result,state,starts,calls=self.run_case(**kwargs)
                self.assertEqual(len(starts),1)
                self.assertNotIn('queue',calls)
