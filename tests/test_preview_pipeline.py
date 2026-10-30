import io
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from weather_controller import Controller


class Transport:
    def __init__(self): self.calls=[]; self.status='complete'
    def queue(self, workflow): self.calls.append('queue'); return 'ours'
    def inspect(self, job): self.calls.append('inspect'); return self.status
    def cancel_pending(self, job): self.calls.append('cancel:'+job); self.status='unknown'
    def image(self, job):
        self.calls.append('image')
        out=io.BytesIO(); Image.new('RGB',(64,128),'navy').save(out,'PNG'); return out.getvalue()


class PipelineTests(unittest.TestCase):
    def make(self, directory, decisions):
        transport=Transport()
        def guard(): return decisions[0] if len(decisions)==1 else decisions.pop(0)
        c=Controller(directory, checkpoint='approved.safetensors', transport=transport, render_guard=guard, poll_seconds=0.01)
        c.settings['location']={'town':'fixture'}
        c.displays=[{'id':'TEST','width':64,'height':128}]
        c.guard={'decision':'safe','observed_at':time.time()}
        return c,transport

    def finish(self,c):
        c.render_thread.join(3)
        self.assertFalse(c.render_thread.is_alive())

    @patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'moon'})
    def test_controller_async_preview_and_thumbnail(self, _):
        with tempfile.TemporaryDirectory() as d:
            c,t=self.make(d,['safe'])
            result=c.dispatch('POST','/v1/render',{'target':'TEST','force':True})
            self.assertEqual(result['state'],'queued')
            self.finish(c)
            self.assertEqual(c.state,'image_preview_ready')
            status=c.status()
            self.assertTrue(status['image_preview']['thumbnail'].startswith('data:image/png;base64,'))
            self.assertFalse(status['apply_enabled'])
            self.assertEqual(t.calls.count('queue'),1)

    @patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'moon'})
    def test_force_and_midrender_game_never_publish(self, _):
        for decisions, submitted in [(['game_active'],False),(['safe','game_active'],True)]:
            with self.subTest(decisions=decisions), tempfile.TemporaryDirectory() as d:
                c,t=self.make(d,decisions)
                c.dispatch('POST','/v1/render',{'force':True})
                self.finish(c)
                self.assertEqual('queue' in t.calls,submitted)
                self.assertIsNone(c.status()['image_preview'])
                self.assertIn(c.state,('deferred','quarantined'))

    @patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'moon'})
    def test_single_flight_and_pending_cancellation(self, _):
        with tempfile.TemporaryDirectory() as d:
            c,t=self.make(d,['safe','game_active'])
            t.status='pending'
            c.dispatch('POST','/v1/render',{'force':True})
            self.finish(c)
            self.assertEqual(t.calls.count('queue'),1)
            self.assertIn('cancel:ours',t.calls)
            self.assertEqual(c.state,'deferred')
            self.assertNotIn('image',t.calls)
        with tempfile.TemporaryDirectory() as d:
            c,t=self.make(d,['safe'])
            from pathlib import Path
            (Path(d)/'inflight.json').write_text('{"prompt_id":"prior-owned"}')
            c.dispatch('POST','/v1/render',{'force':True}); self.finish(c)
            self.assertEqual(c.state,'failed_unreconciled')
            self.assertEqual(t.calls,[])
            c.dispatch('POST','/v1/render',{'force':True})
            self.assertEqual(t.calls,[])

    @patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'moon'})
    def test_transport_preflight_deferral_releases_lock_without_journal(self, _):
        from comfy_preview import SubmissionDeferred
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            c,t=self.make(d,['safe'])
            t.queue=lambda workflow: (_ for _ in ()).throw(SubmissionDeferred('game_active'))
            c.dispatch('POST','/v1/render',{'force':True}); self.finish(c)
            self.assertEqual(c.state,'deferred')
            self.assertFalse(c.render_lock.locked())
            self.assertFalse((Path(d)/'inflight.json').exists())

    def test_invalid_image_retains_previous_and_quarantine_is_private(self):
        from comfy_preview import PreviewStore
        with tempfile.TemporaryDirectory() as d:
            store=PreviewStore(d)
            out=io.BytesIO(); Image.new('RGB',(64,128)).save(out,'PNG'); raw=out.getvalue()
            original=store.save(raw,(64,128),{})
            for data,size in [(b'not an image',(64,128)),(raw,(128,64)),(raw[:-20],(64,128))]:
                with self.assertRaises(Exception): store.save(data,size,{})
                self.assertEqual(store.latest()['id'],original['id'])
            quarantine=store.save(raw,(64,128),{},quarantined=True)
            self.assertNotEqual(quarantine['id'],store.latest()['id'])

if __name__ == '__main__': unittest.main()
