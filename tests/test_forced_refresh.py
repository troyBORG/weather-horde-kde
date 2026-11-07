"""Offline consent and policy contracts; never contact owner services."""
import json
import tempfile
import unittest
from weather_controller import Controller

CONFIRM = 'I accept gaming stutter, VR disruption and GPU OOM risk'

class ForceConsentTests(unittest.TestCase):
    def test_migration_and_restart_require_confirmation_without_preferences_changes(self):
        with tempfile.TemporaryDirectory() as root:
            c = Controller(root)
            c.settings.update(automation_enabled=True, interval_minutes=5)
            c.save()
            c = Controller(root)
            self.assertEqual(c.status().get('automation_policy'), 'guarded')
            before = dict(c.settings)
            result = c.dispatch('PUT', '/v1/force-override', {'enabled':True, 'confirmation':CONFIRM})
            self.assertTrue(result['force_override']['active'])
            self.assertEqual(c.settings, before | {'automation_policy':'force'})
            restarted = Controller(root).status()
            self.assertFalse(restarted['force_override']['active'])
            self.assertEqual(restarted['automation_policy'], 'force')
            self.assertEqual(restarted['force_override']['reason'], 'Reconfirm forced mode')
            self.assertTrue(restarted['automation_enabled'])
            self.assertEqual(restarted['interval_minutes'], 5)

    def test_validation_mutual_exclusion_and_idle_admission_are_atomic(self):
        with tempfile.TemporaryDirectory() as root:
            c = Controller(root)
            before = dict(c.settings)
            for body in ({}, {'enabled':1}, {'enabled':True}, {'enabled':True,'confirmation':'yes'},
                         {'enabled':True,'confirmation':CONFIRM,'extra':True}):
                with self.subTest(body=body), self.assertRaises(ValueError):
                    c.dispatch('PUT','/v1/force-override',body)
                self.assertEqual(c.settings,before)
            for value in (None, 'invalid', True):
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/settings',{'automation_policy':value})
            c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})
            with self.assertRaises(ValueError): c.dispatch('PUT','/v1/force-override',{'enabled':True,'confirmation':CONFIRM})
            c.dispatch('PUT','/v1/testing-override',{'enabled':False})
            c.render_lock.acquire()
            try:
                with self.assertRaises(ValueError): c.dispatch('PUT','/v1/force-override',{'enabled':True,'confirmation':CONFIRM})
            finally: c.render_lock.release()
            c.dispatch('PUT','/v1/force-override',{'enabled':True,'confirmation':CONFIRM})
            before = dict(c.settings)
            with self.assertRaises(ValueError): c.dispatch('PUT','/v1/testing-override',{'enabled':True,'confirmation':'I accept stutter and OOM risk'})
            self.assertEqual(c.settings,before)
            c.render_lock.acquire()
            try:
                c.dispatch('PUT','/v1/force-override',{'enabled':False})
                self.assertFalse(c.status()['force_override']['active'])
            finally: c.render_lock.release()


import time, io, threading
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image

@contextmanager
def fixture(reason='game_active', force=True, failure=None, hook=None):
    """Real HTTP transport + image store + WallpaperManager, synthetic backend."""
    from comfy_preview import ComfyTransport
    from wallpaper import WallpaperManager
    from test_wallpaper import Backend
    from model_catalog import PROFILES
    calls, workflow, controller = [], {}, []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, data):
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(data).encode())
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(self.path); workflow.clear(); workflow.update(body['prompt'])
            self.reply({'prompt_id':'fixture-'+str(len(calls))})
        def do_GET(self):
            if self.path == '/queue':
                self.reply({'queue_running':[[0,'foreign',{}, {'client_id':'foreign'}]] if failure=='queue' else [],'queue_pending':[]})
            elif self.path.startswith('/object_info/'):
                self.reply({'CheckpointLoaderSimple':{'input':{'required':{'ckpt_name':[['fixture.safetensors']]}},'output':['MODEL','CLIP','VAE']}})
            elif self.path.startswith('/history/'):
                if hook: hook(controller[0])
                self.reply({self.path.rsplit('/',1)[1]:{'status':{'completed':True,'status_str':'success'},'outputs':{'9':{'images':[{'filename':'fixture.png','type':'output'}]}}}})
            else:
                raw=io.BytesIO(); dims=workflow['4']['inputs']
                Image.new('RGB',(dims['width'],dims['height']),'navy').save(raw,'PNG')
                self.send_response(200); self.send_header('Content-Type','image/png'); self.end_headers(); self.wfile.write(raw.getvalue())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever); worker.start()
    try:
        with tempfile.TemporaryDirectory() as root, patch('comfy_preview.listener_identity',return_value=None if failure=='owner' else (123,1000,1)), patch('weather_controller.weather_preview',return_value={'positive':'CPU FIXTURE','negative':'fixture'}):
            t=ComfyTransport('http://127.0.0.1:'+str(server.server_port))
            c=Controller(root,checkpoint='fixture.safetensors',transport=t,render_guard=lambda:reason,poll_seconds=0)
            controller.append(c)
            t.guard=lambda:(c.job_guard or c.render_guard)()
            c.guard={'decision':reason,'observed_at':0,'total_mib':24576,'free_mib':1}
            c.models=[] if failure=='model' else [dict(id='fixture.safetensors',**PROFILES['sdxl'])]
            c.enforce_models=True; c.refresh_models=lambda:c.models
            c.session_activity.poll=lambda:True
            b=Backend(); c.wallpaper=WallpaperManager(Path(root),b)
            c.displays=[dict(id='DP-1',width=64,height=128,scale=1,x=0,y=0)]
            c.settings.update(location={'town':'fixture'},automation_enabled=True,automation_kind='image_wallpaper')
            if force: c.dispatch('PUT','/v1/force-override',{'enabled':True,'confirmation':CONFIRM})
            yield c,b,calls
    finally: server.shutdown();server.server_close();worker.join()


class ForcePipelineTests(unittest.TestCase):
    def run_job(self,c):
        result=c.dispatch('POST','/v1/render',{'target':'all'},scheduled=True)
        if c.render_thread:
            c.render_thread.join(5)
            self.assertFalse(c.render_thread.is_alive())
        return result

    def test_forced_resource_bypass_reaches_verified_apply_guarded_never_posts(self):
        for reason in ('game_active','vr_active','gpu_busy','unknown','insufficient_vram','vram_unavailable'):
            for force in (False,True):
                with self.subTest(reason=reason,force=force), fixture(reason,force) as (c,b,calls):
                    self.run_job(c)
                    self.assertEqual(calls,['/prompt'] if force else [],c.last_error)
                    self.assertEqual(len(b.writes),1 if force else 0,c.last_error)
                    if force:
                        self.assertEqual(c.state,'wallpapers_applied')
                        self.assertIn(reason,c.image_preview['automation_policy']['reasons'])
                        self.assertTrue(c.wallpaper_action['verified'])
                        job_receipt=json.loads(next((c.root/'job-receipts').glob('*.json')).read_text())
                        self.assertFalse(job_receipt['testing_override']['enabled'])
                        self.assertEqual(job_receipt['automation_policy']['policy'],'force')

    def test_midflight_revocation_lock_topology_and_new_policy_never_release_output(self):
        for change in ('disable','auto_off','token','locked','unknown_session','topology'):
            def hook(c):
                if change=='disable':
                    c.dispatch('PUT','/v1/force-override',{'enabled':False})
                    self.assertEqual(c.settings['automation_policy'],'force')
                    self.assertIn('draining',c.force_status()['reason'])
                elif change=='auto_off': c.dispatch('PUT','/v1/settings',{'automation_enabled':False})
                elif change=='token': c.force_generation += 1
                elif change=='locked': c.session_activity.poll=lambda:False
                elif change=='unknown_session': c.session_activity.poll=lambda:None
                else: c.displays[0]['width']=128
            with self.subTest(change=change), fixture(hook=hook) as (c,b,calls):
                self.run_job(c)
                self.assertEqual(calls,['/prompt'])
                self.assertEqual(b.writes,[],c.last_error)
                self.assertIsNone(c.store.latest())
                self.assertEqual(c.state,'quarantined',c.last_error)
                self.assertNotIn('/interrupt',calls)

    def test_session_changes_during_final_transaction_guard_never_write(self):
        for unlocked in (False, None):
            with self.subTest(unlocked=unlocked), fixture() as (c,b,calls):
                session = [True]
                c.session_activity.poll = lambda: session[0]
                def slow_resources():
                    journal = c.wallpaper.journal
                    if journal.exists() and any(v.get('state') == 'pending' for v in json.loads(journal.read_text()).values()):
                        session[0] = unlocked
                    return 'game_active'
                c.render_guard = slow_resources
                self.run_job(c)
                self.assertEqual(calls, ['/prompt'])
                self.assertEqual(b.writes, [], c.last_error)
                self.assertNotEqual(c.state, 'wallpapers_applied')
                self.assertIs(session[0], unlocked)
                self.assertEqual(json.loads(c.wallpaper.journal.read_text())['DP-1']['state'], 'pending')

    def test_pending_wallpaper_receipt_blocks_before_submission(self):
        from wallpaper import atomic_json
        with fixture() as (c,b,calls):
            atomic_json(c.root/'wallpaper-restore.json',{'DP-1':{'state':'pending'}})
            # Reload real manager from durable journal, not a mock preflight.
            from wallpaper import WallpaperManager
            c.wallpaper=WallpaperManager(c.root,b)
            self.run_job(c)
            self.assertEqual(calls,[])
            self.assertEqual(b.writes,[])

    def test_reconcile_uses_selected_policy_but_retains_hard_gates(self):
        from wallpaper import atomic_json
        for failure in (None, 'model', 'pending', 'plugin', 'inflight'):
            with self.subTest(failure=failure), fixture() as (c,b,calls):
                c.scheduler.permanent_error = 'Retry budget exhausted: GPU OOM fixture'
                if failure == 'model': c.models = []
                if failure == 'pending': atomic_json(c.wallpaper.journal, {'DP-1':{'state':'pending'}})
                if failure == 'plugin': b.value['plugin'] = ''
                if failure == 'inflight': (c.root/'inflight.json').write_text('{}')
                c.guard['observed_at'] = time.time()
                expected = {'model':'unreviewed_model', 'pending':'Unreconciled wallpaper transaction',
                            'plugin':'Original wallpaper plugin unavailable', 'inflight':'outstanding render'}
                if failure:
                    with self.assertRaisesRegex(ValueError, expected[failure]):
                        c.dispatch('POST','/v1/refresh/reconcile',{'confirmation':'Reconcile automatic refresh'})
                    self.assertTrue(c.scheduler.permanent_error)
                else:
                    c.dispatch('POST','/v1/refresh/reconcile',{'confirmation':'Reconcile automatic refresh'})
                    self.assertFalse(c.scheduler.permanent_error)
                self.assertEqual(calls, [])
                self.assertEqual(b.writes, [])
        with fixture(force=False) as (c,b,calls):
            with self.assertRaisesRegex(ValueError, 'insufficient_vram|vram_unavailable'):
                c.dispatch('POST','/v1/refresh/reconcile',{'confirmation':'Reconcile automatic refresh'})

    def test_fixed_cadence_coalesces_while_busy_and_keeps_one_successor(self):
        with fixture() as (c,b,calls):
            c.settings['interval_minutes']=5
            c.next_eligible_at=300
            c.displays.append(dict(id='DP-2',width=128,height=64,scale=1,x=64,y=0))
            requests=[]
            def dispatch(*args,**kwargs):
                requests.append(dict(c.scheduler.active or {}));return {'state':'queued'}
            with patch.object(c,'dispatch',side_effect=dispatch):
                c.tick(299,299); self.assertEqual(requests,[])
                c.tick(300,300); self.assertEqual(len(requests),1)
                self.assertEqual(requests[0]['targets'],['DP-1','DP-2'])
                c.render_lock.acquire()
                for now in (600,900,1200): c.tick(now,now)
                self.assertEqual(len(requests),1)
                active=c.scheduler.active['generation_id']
                c.scheduler.complete('DP-1',active,1201)
                c.scheduler.complete('DP-2',active,1201)
                c.render_lock.release()
                c.tick(1202,1202)
                self.assertEqual(len(requests),2)
                active=c.scheduler.active['generation_id']
                for target in ('DP-1','DP-2'): c.scheduler.complete(target,active,1203)
                for now in range(1204,1499,10): c.tick(now,now)
                c.tick(1499,1499);self.assertEqual(len(requests),2)
                c.tick(1500,1500);self.assertEqual(len(requests),3)
                self.assertEqual(c.next_eligible_at,1800)

    def test_status_distinguishes_cadence_retry_pending_and_blocks(self):
        with fixture() as (c,b,calls), patch('weather_controller.time.time',return_value=300), patch('weather_controller.time.monotonic',return_value=300):
            c.settings['interval_minutes']=5; c.next_eligible_at=300
            with patch.object(c,'dispatch',return_value={'state':'queued'}) as dispatch:
                c.tick(300,300)
                self.assertEqual(c.status()['refresh_timing']['state'], 'rendering')
                self.assertIsNone(c.status()['refresh_timing']['next_attempt_at'])
                c.scheduler.fail('GPU OOM fixture',monotonic_now=300)
                timing=c.status()['refresh_timing']
                self.assertEqual(timing['cadence_due_at'],600)
                self.assertEqual(timing['retry_due_at'],360)
                self.assertEqual(timing['next_attempt_at'],360)
                self.assertEqual(timing['state'],'retry_wait')
                c.tick(359,359);self.assertEqual(dispatch.call_count,1)
                c.tick(360,360);self.assertEqual(dispatch.call_count,2)
                c.scheduler.active=None; c.scheduler.retry_at=0; c.scheduler.retry_reason=''
                c.scheduler.observe_activity(True,True,300)
                self.assertEqual(c.status()['refresh_timing']['state'],'pending')
                self.assertEqual(c.status()['refresh_timing']['next_attempt_at'],300)
                c.scheduler.permanent_error='Retry budget exhausted: GPU OOM fixture'
                timing=c.status()['refresh_timing']
                self.assertEqual(timing['state'],'action_required')
                self.assertIsNone(timing['next_attempt_at'])
                self.assertIsNone(timing['retry_due_at'])
                c.scheduler.permanent_error=''; c.scheduler.pending.clear()
                self.assertEqual(c.status()['refresh_timing']['state'],'cadence_wait')
                self.assertEqual(c.status()['refresh_timing']['next_attempt_at'],600)
                c.scheduler.observe_activity(True,False,300)
                self.assertEqual(c.status()['refresh_timing']['state'],'blocked')
                self.assertIsNone(c.status()['refresh_timing']['next_attempt_at'])
                c.settings['automation_enabled']=False
                self.assertEqual(c.status()['refresh_timing']['state'],'disabled')
                self.assertIsNone(c.status()['refresh_timing']['next_attempt_at'])

    def test_reconfirmation_pauses_tick_and_failed_jobs_use_bounded_backoff(self):
        with fixture() as (c,b,calls):
            c.settings['interval_minutes']=5; c.next_eligible_at=300
            c.force_consent=False
            with patch.object(c,'dispatch',return_value={'state':'queued'}) as dispatch:
                c.tick(300,300); dispatch.assert_not_called()
                c.force_consent=True
                c.tick(301,301);self.assertEqual(dispatch.call_count,1)
                c.scheduler.fail('GPU OOM fixture',monotonic_now=301)
                c.tick(350,350);self.assertEqual(dispatch.call_count,1)
                c.tick(361,361);self.assertEqual(dispatch.call_count,2)
                c.settings['automation_enabled']=False
                c.tick(900,900);self.assertEqual(dispatch.call_count,2)
                self.assertFalse(c.scheduler.pending)

    def test_authenticated_endpoint_rejects_foreign_origin_and_bad_types(self):
        from weather_controller import make_server
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as root:
            c=Controller(root); server=make_server(c,0)
            worker=threading.Thread(target=server.serve_forever);worker.start()
            try:
                for token,origin,body,code in [('',None,{'enabled':True,'confirmation':CONFIRM},401),
                    (c.token,'https://example.com',{'enabled':True,'confirmation':CONFIRM},403),
                    (c.token,None,{'enabled':'true','confirmation':CONFIRM},400)]:
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
                    if origin: headers['Origin']=origin
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(f'http://127.0.0.1:{server.server_port}/v1/force-override',data=json.dumps(body).encode(),method='PUT',headers=headers))
                    self.assertEqual(error.exception.code,code);error.exception.close()
                    self.assertFalse(c.force_status()['active'])
                    self.assertIsNone(c.render_thread)
            finally:server.shutdown();server.server_close();worker.join()

    def test_all_native_targets_and_panorama_apply_receipts(self):
        import copy
        from test_wallpaper import Backend
        from wallpaper import WallpaperManager
        from test_night_realism import LOCATION, preview
        stamp=preview()['observed_at']
        for panorama in (False,True):
            with self.subTest(panorama=panorama), fixture() as (c,b,calls), patch('weather_controller.time.time',return_value=stamp), patch('weather_controller.weather_preview',side_effect=lambda loc,**kw:preview(**{k:v for k,v in kw.items() if k!='fetch'})):
                c.settings.update(location=LOCATION,connected_panorama=panorama,interval_minutes=5)
                c.displays.append(dict(id='DP-2',width=128,height=64,scale=1,x=64,y=0))
                backends={}
                for i,target in enumerate(c.displays):
                    backend=Backend();backend.value.update(desktop=12+i,screen=i,geometry=[target['x'],0,target['width'],target['height']]);backends[target['id']]=backend
                class MultiBackend:
                    def snapshot(self,target):return backends[target['id']].snapshot(target)
                    def replace(self,target,expected,replacement):return backends[target['id']].replace(target,expected,replacement)
                c.wallpaper=WallpaperManager(c.root,MultiBackend())
                c.next_eligible_at=stamp
                c.tick(stamp,100)
                c.render_thread.join(5);self.assertFalse(c.render_thread.is_alive())
                self.assertEqual(c.state,'wallpapers_applied',c.last_error)
                self.assertEqual(len(calls),1 if panorama else 2)
                self.assertEqual(set(c.scheduler.success['image_wallpaper']),{'DP-1','DP-2'})
                self.assertFalse(c.scheduler.active)
                for target in c.displays:
                    record=c.previews_by_target[target['id']]
                    self.assertEqual((record['width'],record['height']),(target['width'],target['height']))
                    self.assertEqual(len(backends[target['id']].writes),1)
                    self.assertEqual(bool(record.get('panorama')),panorama)

    def test_startup_resource_override_keeps_post_start_owner_gate_and_slow_revocation(self):
        with fixture() as (c,b,calls):
            policy,receipt=c.forced_policy(scheduled=True)
            c.startup_guard=lambda:'vram_unavailable'
            with patch.object(c.transport,'owned_gpu_pid',return_value=None):
                self.assertEqual(policy.startup(),'safe')
                self.assertEqual(policy(),'unverified_comfy_ownership')
            def revoke():
                c.dispatch('PUT','/v1/force-override',{'enabled':False})
                return 'unknown'
            c.startup_guard=revoke
            self.assertEqual(policy.startup(),'force_consent_revoked')
            self.assertEqual(calls,[])

    def test_game_begins_midflight_guarded_quarantines_force_applies(self):
        for forced in (False,True):
            def hook(c):c.render_guard=lambda:'game_active'
            with self.subTest(forced=forced), fixture(reason='safe',force=forced,hook=hook) as (c,b,calls):
                c.guard.update(observed_at=time.time(),free_mib=24000)
                self.run_job(c)
                self.assertEqual(calls,['/prompt'])
                self.assertEqual(len(b.writes),1 if forced else 0)
                if not forced:self.assertEqual(c.state,'quarantined')

    def test_force_retains_owner_queue_and_compatible_model_checks(self):
        for failure in ('owner','queue','model'):
            with self.subTest(failure=failure), fixture(failure=failure) as (c,b,calls):
                self.run_job(c)
                self.assertEqual(calls,[])
                self.assertEqual(b.writes,[])
