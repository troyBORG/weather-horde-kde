import time
import unittest
import safety


class MemoryPolicyTests(unittest.TestCase):
    def test_shared_model_activity_and_override_gates(self):
        import tempfile
        from weather_controller import Controller
        from model_catalog import PROFILES
        from types import SimpleNamespace
        for total in (8192, 16384, 24576, 49152):
            for free, expected in ((total/5, 'safe'), (total/5-1, 'insufficient_vram'), (total, 'safe')):
                evidence = dict(total_mib=total, free_mib=free, observed_at=time.time())
                self.assertEqual(safety.vram_eligibility(evidence), expected)
                sample = dict(evidence, complete=True, age=0, processes=['kwin_wayland'], utilization=[0,0], sample_gap=10)
                self.assertEqual(safety.assess(sample)[0], expected)
                with tempfile.TemporaryDirectory() as d:
                    c = Controller(d, checkpoint='fixture', transport=SimpleNamespace(owned_gpu_pid=lambda:123), render_guard=lambda:'game_active')
                    c.guard = evidence
                    for profile in PROFILES.values():
                        c.models = [dict(profile, id='fixture')]
                        self.assertEqual(c.model_gate(), expected)
                    c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})
                    self.assertEqual(c.manual_policy()[0](), expected)

    def test_owned_job_and_panorama_capture_first_breach(self):
        import tempfile, io, json
        from pathlib import Path
        from unittest.mock import patch
        from PIL import Image
        from weather_controller import Controller
        from model_catalog import PROFILES
        from test_night_realism import LOCATION, preview
        for panorama in (False, True):
            for breach in (False, True):
                with self.subTest(panorama=panorama, breach=breach), tempfile.TemporaryDirectory() as d:
                    class Transport:
                        def queue(self, graph): return 'fixture'
                        def inspect(self, job): return 'complete'
                        def image(self, job):
                            c.guard['free_mib'] = 4000 if breach else 11264
                            stream=io.BytesIO(); Image.new('RGB',(1024 if panorama else 512,512)).save(stream,'PNG'); return stream.getvalue()
                    c=Controller(d,checkpoint='fixture',transport=Transport(),render_guard=lambda:'safe')
                    c.models=[dict(PROFILES['sdxl'],id='fixture')]
                    c.guard=dict(decision='safe',total_mib=24576,free_mib=11264,observed_at=time.time(),secret='not in receipt')
                    c.settings['connected_panorama']=panorama
                    c.displays=[dict(id=name,x=x,y=0,width=512,height=512,scale=1) for name,x in [('A',0),('B',512)]]
                    with patch('weather_controller.weather_preview',side_effect=lambda loc,**kw:preview()):
                        c.render_lock.acquire(); c.render_images(c.displays,LOCATION)
                    self.assertEqual(c.state,'quarantined' if breach else 'image_preview_ready',c.last_error)
                    if breach:
                        self.assertEqual(c.quarantine['stage'],'image_validation')
                        self.assertEqual(c.quarantine['memory']['free_mib'],4000)
                        self.assertEqual(c.quarantine['memory']['required_free_mib'],4915.2)
                        receipt=json.loads(next(Path(d,'job-receipts').glob('*.json')).read_text())
                        self.assertEqual(receipt['quarantine'],c.quarantine)
                        self.assertNotIn('secret',json.dumps(receipt['quarantine']))
                        self.assertIsNone(c.store.latest())
                    else: self.assertIsNone(c.quarantine)

    def test_owned_utilization_keeps_memory_gate_without_self_blocking(self):
        sample=dict(processes=['kwin_wayland'],complete=True,age=0,sample_gap=10,
                    utilization=[90,95],total_mib=24576,free_mib=11264,
                    gpu_clients=['kwin_wayland','python'],gpu_pids=[10,20],
                    owned_pid=20,owned_active=True,previous_owned_pid=20,previous_owned_active=True,
                    client_sm={10:1,20:94},previous_client_sm={10:1,20:89})
        self.assertEqual(safety.assess(sample),('safe','checks_passed'))
        self.assertEqual(safety.assess(sample | {'free_mib':4915}),('insufficient_vram','vram_reserve'))

    def test_status_has_bounded_memory_sample(self):
        import tempfile
        from weather_controller import Controller
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d)
            c.guard=dict(total_mib=24576,free_mib=11264,observed_at=time.time(),decision='safe',secret='no')
            memory=c.status()['memory']
            self.assertEqual(memory['used_mib'],13312)
            self.assertEqual(memory['required_free_mib'],4915.2)
            self.assertNotIn('secret',memory)
            c.guard['observed_at']=0
            self.assertEqual(c.status()['memory']['decision'],'vram_unavailable')

    def test_invalid_missing_and_stale_fail_closed(self):
        good = dict(total_mib=24576, free_mib=11264, observed_at=time.time())
        for key in ('total_mib','free_mib'):
            for value in (None, True, '24576', float('nan'), float('inf'), -1, 10**400):
                self.assertEqual(safety.vram_eligibility(dict(good, **{key:value})), 'vram_unavailable')
            sample = good.copy(); del sample[key]
            self.assertEqual(safety.vram_eligibility(sample), 'vram_unavailable')
        for change in ({'total_mib':0}, {'free_mib':24577}, {'observed_at':0}, {'observed_at':float('nan')}, {'observed_at':True}):
            self.assertEqual(safety.vram_eligibility(good | change), 'vram_unavailable')

    def test_thirteen_gib_used_on_twenty_four_gib_is_admitted(self):
        evidence = dict(total_mib=24576, free_mib=11264, observed_at=time.time())
        self.assertEqual(safety.vram_eligibility(evidence), 'safe')
        evidence['free_mib'] = 4915.2
        self.assertEqual(safety.vram_eligibility(evidence), 'safe')
        evidence['free_mib'] = 4915.19
        self.assertEqual(safety.vram_eligibility(evidence), 'insufficient_vram')
