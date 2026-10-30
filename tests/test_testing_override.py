import tempfile, time, unittest
from unittest.mock import patch
from weather_controller import Controller

class OverrideTests(unittest.TestCase):
    def enable(self, c):
        return c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})

    def test_manual_policy_hard_gates_and_frozen_expiry(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.time.monotonic',return_value=100) as clock:
            t=SimpleNamespace(owned_gpu_pid=lambda:123)
            c=Controller(d,transport=t,render_guard=lambda:c.guard['decision'])
            c.guard={'decision':'game_active','free_mib':16000,'observed_at':time.time()}
            normal, receipt=c.manual_policy()
            self.assertEqual(normal(),'game_active')
            self.enable(c)
            guard,receipt=c.manual_policy()
            for reason in ('game_active','vr_active','gpu_busy','unknown','safe'):
                c.guard['decision']=reason
                self.assertEqual(guard(),'safe')
            self.assertTrue(receipt['used'])
            self.assertIn('game_active',receipt['reasons'])
            for free in (0,11263,None,float('nan'),float('inf'),True):
                c.guard['free_mib']=free
                self.assertNotEqual(guard(),'safe')
            c.guard['free_mib']=11264
            t.owned_gpu_pid=lambda:None
            self.assertNotEqual(guard(),'safe')
            t.owned_gpu_pid=lambda:123
            c.guard['decision']='insufficient_vram'
            self.assertNotEqual(guard(),'safe')
            c.guard['decision']='game_active'
            clock.return_value=700
            self.assertEqual(guard(),'testing_override_expired')
            self.enable(c)
            self.assertEqual(guard(),'testing_override_expired')
            guard,_=c.manual_policy()
            c.dispatch('PUT','/v1/testing-override',{'enabled':False})
            self.assertEqual(guard(),'testing_override_expired')

    @patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'moon'})
    def test_pipeline_override_receipt_and_expiry_boundaries(self, _):
        from test_preview_pipeline import Transport
        from pathlib import Path
        import json
        for phase in ('none','weather','queue','inspect','image','publication'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as d, patch('weather_controller.time.monotonic',return_value=100) as clock:
                t=Transport(); t.owned_gpu_pid=lambda:123
                c=Controller(d,checkpoint='approved',transport=t,render_guard=lambda:'game_active',poll_seconds=0)
                c.guard={'decision':'game_active','free_mib':16000,'observed_at':time.time()}
                c.displays=[{'id':'TEST','width':64,'height':128}]
                c.settings['location']={'town':'fixture'}
                self.enable(c)
                if phase in ('queue','inspect','image'):
                    original=getattr(t,phase)
                    def expire(*args, original=original):
                        value=original(*args); clock.return_value=701; return value
                    setattr(t,phase,expire)
                if phase=='weather':
                    def weather(loc, **kwargs): clock.return_value=701; return {'positive':'test','negative':'moon'}
                    _.side_effect=weather
                else: _.side_effect=None
                if phase=='publication':
                    original=c.store.save
                    def save(*args,**kwargs): clock.return_value=701; return original(*args,**kwargs)
                    c.store.save=save
                result=c.dispatch('POST','/v1/render',{'force':True})
                self.assertEqual(result['state'],'queued')
                c.render_thread.join(3)
                self.assertFalse(c.render_thread.is_alive())
                if phase=='none':
                    self.assertEqual(c.state,'image_preview_ready')
                    receipt=c.image_preview['testing_override']
                    self.assertTrue(receipt['used']); self.assertIn('game_active',receipt['reasons'])
                else:
                    self.assertIn(c.state,('quarantined','deferred'))
                    self.assertIsNone(c.image_preview)
                    self.assertIsNone(c.store.latest())
                self.assertFalse(c.render_lock.locked())
                receipts=list((Path(d)/'job-receipts').glob('*.json'))
                self.assertEqual(len(receipts),1)
                self.assertTrue(json.loads(receipts[0].read_text())['testing_override']['enabled'])
                self.assertNotIn('interrupt',t.calls)
                self.assertFalse(c.status()['apply_enabled'])

    def test_transport_cannot_submit_to_unverified_listener_even_safe_guard(self):
        from comfy_preview import ComfyTransport, SubmissionDeferred
        t=ComfyTransport(guard=lambda:'safe')
        with patch('comfy_preview.listener_identity',return_value=None), patch.object(t,'request',return_value={'queue_running':[],'queue_pending':[]}) as request:
            with self.assertRaises(SubmissionDeferred): t.queue({})
            self.assertFalse(any(call.args[0]=='/prompt' for call in request.call_args_list))

    def test_late_publication_guard_quarantines_after_disk_write(self):
        from comfy_preview import PreviewStore
        from test_preview_pipeline import Transport
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            original=Path.rename
            allowed=[True]
            def rename(path,target):
                result=original(path,target); allowed[0]=False; return result
            with patch.object(Path,'rename',rename):
                result=PreviewStore(d).save(Transport().image('ours'),(64,128),{},guard=lambda:'safe' if allowed[0] else 'testing_override_expired')
            self.assertTrue(result['quarantined'])
            self.assertIsNone(PreviewStore(d).latest())

    def test_expiry_during_listener_verification_prevents_post(self):
        from comfy_preview import ComfyTransport, SubmissionDeferred
        allowed=[True]
        def identity(port): allowed[0]=False; return (123,1000,1)
        t=ComfyTransport(guard=lambda:'safe' if allowed[0] else 'testing_override_expired')
        with patch('comfy_preview.listener_identity',side_effect=identity), patch.object(t,'request',return_value={'queue_running':[],'queue_pending':[]}) as request:
            with self.assertRaises(SubmissionDeferred): t.queue({})
            self.assertFalse(any(call.args[0]=='/prompt' for call in request.call_args_list))

    def test_override_auth_and_singleflight_scheduler_locks(self):
        import json, threading
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from weather_controller import make_server
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d)
            server=make_server(c,0)
            worker=threading.Thread(target=server.serve_forever); worker.start()
            base='http://127.0.0.1:'+str(server.server_port)
            body=json.dumps({'enabled':True,'confirmation':'I accept stutter and OOM risk'}).encode()
            try:
                for token,origin,code in [('',None,401),(c.token,'https://example.com',403)]:
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+token}
                    if origin: headers['Origin']=origin
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(base+'/v1/testing-override',data=body,method='PUT',headers=headers))
                    self.assertEqual(error.exception.code,code); error.exception.close()
                    self.assertFalse(c.override_status()['active'])
                self.enable(c)
                c.render_lock.acquire()
                with self.assertRaises(ValueError): self.enable(c)
                c.guard={'decision':'safe','observed_at':time.time()}
                with patch.object(c,'manual_policy',return_value=(lambda:'safe',{'enabled':False})), patch('threading.Thread') as thread:
                    c.checkpoint='fixture'; c.displays=[{'id':'TEST'}]; c.settings['location']={'town':'fixture'}
                    self.assertIn('already in flight',c.dispatch('POST','/v1/render',{})['reason'])
                    thread.assert_not_called()
                with patch.object(c,'build_preview') as build:
                    c.settings['automation_enabled']=True # even accidental internal enable cannot schedule
                    c.tick(c.next_eligible_at+1)
                    build.assert_not_called()
                self.assertEqual(c.dispatch('POST','/v1/restore',{})['state'],'blocked_preview_only')
                c.render_lock.release()
            finally: server.shutdown(); server.server_close(); worker.join()

    def test_unknown_activity_has_specific_evidence_reason(self):
        import safety
        self.assertTrue(hasattr(safety,'assess'), 'need diagnostic policy, not guessed pmon reason')
        good={'complete':True,'age':0,'processes':['kwin_wayland'],'gpu_clients':[],
              'utilization':[1,1],'sample_gap':10,'free_mib':16000}
        for change,reason in [({'sample_gap':0},'sampling_window'),({'sample_gap':31},'sampling_window'),
             ({'complete':False},'graphical_owner_visibility'),({'gpu_clients':['spectacle']},'unrecognized_gpu_client'),
             ({'utilization':[None,None]},'utilization_unavailable'),({'free_mib':None},'vram_unavailable')]:
            with self.subTest(reason=reason):
                self.assertEqual(safety.assess(good|change),('unknown',reason))
        self.assertEqual(safety.assess(good),('safe','checks_passed'))

    def test_session_confirmation_ttl_and_automation(self):
        with tempfile.TemporaryDirectory() as d, patch('weather_controller.time.monotonic', return_value=100) as clock:
            c=Controller(d)
            self.assertFalse(c.status().get('testing_override', {}).get('active', False))
            with self.assertRaises(ValueError): c.dispatch('PUT','/v1/testing-override',{'enabled':True})
            c.settings['automation_enabled']=True
            status=c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})
            self.assertTrue(status['testing_override']['active'])
            self.assertEqual(status['testing_override']['remaining_seconds'],600)
            self.assertFalse(status['automation_enabled'])
            with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'automation_enabled':True})
            self.assertFalse(Controller(d).status()['testing_override']['active'])
            clock.return_value=700
            self.assertFalse(c.status()['testing_override']['active'])
            self.assertFalse(c.status()['automation_enabled'])
