import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('persistent',ROOT/'scripts/install-controller-service.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class StartupTests(unittest.TestCase):
    def test_login_deadline_uses_saved_interval_without_changing_settings(self):
        from weather_controller import Controller
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'settings.json'
            raw = json.dumps({'automation_enabled':True,'automation_kind':'image_wallpaper','interval_minutes':30,'scene_kind':'woodland'})
            p.write_text(raw)
            before=time.time()
            c=Controller(d)
            self.assertGreaterEqual(c.next_eligible_at, before+1800)
            self.assertLess(c.next_eligible_at, before+1802)
            self.assertEqual(p.read_text(),raw)

    def test_catchup_opt_in_preserves_exact_prior_auto_and_scope(self):
        original={'automation_enabled':False,'automation_kind':'image_preview','automation_target':'DP-3','interval_minutes':120,'location':{'town':'fixture'}}
        result=m.requested_settings(json.dumps(original),False,enable_catchup=True)
        self.assertEqual(result,original|{'catch_up_refresh':True})

    def test_saved_off_stays_off_and_explicit_restore_changes_only_consent(self):
        original={'automation_enabled':False,'automation_kind':'prompt_preview','automation_target':'DP-2',
                  'interval_minutes':60,'checkpoint':'saved.safetensors','location':{'zip':'52742'},'scene_kind':'random'}
        raw=json.dumps(original)
        self.assertEqual(m.requested_settings(raw,False),original)
        restored=m.requested_settings(raw,True)
        self.assertEqual({k:v for k,v in restored.items() if k not in m.AUTO_KEYS},
                         {k:v for k,v in original.items() if k not in m.AUTO_KEYS})
        self.assertEqual([restored[k] for k in m.AUTO_KEYS],[True,'image_wallpaper','all',30])
        with self.assertRaises(ValueError): m.requested_settings('{}',False)
        with self.assertRaises(ValueError): m.requested_settings(json.dumps(original|{'location':None}),True)

    def test_unit_real_systemd_syntax_and_literal_arguments(self):
        args=argparse.Namespace(preview_checkpoint='fallback.safetensors',comfy_idle_seconds=600,manual_wallpapers=True,managed_comfy=True)
        argv=m.command(args,{'checkpoint':'saved $MODEL %name "test".safetensors'},Path('/tmp/state'))
        text=m.render_unit(argv)
        for value in ('WantedBy=graphical-session.target','PartOf=graphical-session.target','Requisite=graphical-session.target',
                      'RestartSec=15','StartLimitBurst=3','--managed-comfy','--manual-wallpapers','$$MODEL','%%name','600'):
            self.assertIn(value,text)
        for value in ('--automation-off','testing-override','systemd-run','WantedBy=default.target'):
            self.assertNotIn(value,text)
        with tempfile.TemporaryDirectory() as d:
            unit=Path(d)/m.UNIT;unit.write_text(text)
            result=subprocess.run(['systemd-analyze','--user','verify',str(unit)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            wants=Path(d)/'graphical-session.target.wants';wants.mkdir()
            (wants/m.UNIT).symlink_to(unit)
            graph=subprocess.run(['systemd-analyze','--user','verify','graphical-session.target'],
                env=os.environ|{'SYSTEMD_UNIT_PATH':d+':/usr/lib/systemd/user'},capture_output=True,text=True)
            self.assertEqual(graph.returncode,0,graph.stderr)
        with self.assertRaises(ValueError): m.quote('bad\narg')

    def test_lingering_controller_process_is_refused_even_without_unit(self):
        self.assertTrue(hasattr(m,'controller_running'),'Missing non-unit process exclusion')
        with tempfile.TemporaryDirectory() as d:
            proc=Path(d);p=proc/'123';p.mkdir()
            (p/'cmdline').write_bytes(b'/usr/bin/python3\0/some/path/weather_controller.py\0')
            self.assertTrue(m.controller_running(proc))
            (p/'cmdline').write_bytes(b'/usr/bin/python3\0unrelated.py\0')
            self.assertFalse(m.controller_running(proc))

    def test_transient_collection_is_waited_and_live_or_stuck_refused(self):
        gone={'ActiveState':'inactive','MainPID':'0','Transient':'no','LoadState':'not-found'}
        transient=gone|{'Transient':'yes'}
        with tempfile.TemporaryDirectory() as d, patch.object(Path,'home',return_value=Path(d)), patch.object(m.socket,'socket'), patch.object(m.time,'sleep') as sleep:
            with patch.object(m,'props',side_effect=[transient,transient,gone]):
                self.assertEqual(m.require_stopped(),gone)
                self.assertEqual(sleep.call_count,2)
            with patch.object(m,'props',return_value=transient):
                with self.assertRaisesRegex(RuntimeError,'not collected'): m.require_stopped()
            for bad in (gone|{'ActiveState':v} for v in (None,'unknown','checking_weather','activating')):
                with patch.object(m,'props',return_value=bad), self.assertRaises(RuntimeError): m.require_stopped()
            with patch.object(m,'props',return_value=gone|{'DropInPaths':'unreviewed.conf'}), self.assertRaises(RuntimeError): m.require_stopped()
            with patch.object(m,'props',return_value=gone), patch.object(m,'controller_running',return_value=True), self.assertRaises(RuntimeError): m.require_stopped()
            with patch.object(m,'props',return_value=gone|{'ActiveState':'active','MainPID':'123'}):
                with self.assertRaisesRegex(RuntimeError,'active/transitioning'): m.require_stopped()

    def test_authenticated_http_receipt_rejects_stale_revision_or_changed_auto(self):
        from weather_controller import Controller, make_server, SOURCE_REVISION
        import threading
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d)
            server=make_server(c,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            original_request=m.Request
            def request(url,**kw): return original_request(url.replace(':8734',':'+str(server.server_port)),**kw)
            try:
                with patch.object(m,'Request',side_effect=request): status=m.api(c.token)
                self.assertEqual(status['source_revision'],SOURCE_REVISION)
                self.assertNotIn(c.token,json.dumps(status))
                argv=['python','controller','--preview-checkpoint','saved','--manual-wallpapers','--managed-comfy']
                expected={'automation_enabled':False,'automation_kind':'image_wallpaper','automation_target':'all','interval_minutes':30}
                ready=status|expected|{'render_enabled':True,'apply_enabled':True,'checkpoint':'saved','comfy_service':{'managed':True},'displays':[{'id':'DP-2'}],'next_eligible_at':time.time()+1800}
                m.verify_status(ready,expected,argv,SOURCE_REVISION)
                for bad in ({'source_revision':'old'},{'automation_enabled':True},{'testing_override':{'active':True}},{'displays':[]},{'checkpoint':'wrong'},{'next_eligible_at':0}):
                    with self.assertRaises(RuntimeError): m.verify_status(ready|bad,expected,argv,SOURCE_REVISION)
            finally: server.shutdown();server.server_close();thread.join()

    def test_owner_install_preserves_saved_off(self):
        self._fixture_install(False)

    def test_owner_install_preserves_saved_on(self):
        self._fixture_install(True)

    def test_failed_reload_rolls_back_without_start_or_config_loss(self):
        self._fixture_install(True, fail_reload=True)

    def test_catchup_installer_preserves_auto_on_and_off_and_rolls_back(self):
        for enabled in (False, True): self._fixture_install(enabled, enable_catchup=True)
        self._fixture_install(True, fail_reload=True, enable_catchup=True)

    def _fixture_install(self, enabled, fail_reload=False, enable_catchup=False):
        # Real filesystem writes/locks, actual systemd verifier and authenticated
        # validation logic; user manager and display edges are fixtures, no GPU.
        from weather_controller import SOURCE_REVISION
        with tempfile.TemporaryDirectory(dir=Path.home()) as d:
            home=Path(d);state=home/'.local/state/weather-horde-kde';state.mkdir(parents=True,mode=0o700)
            dest=home/'.config/systemd/user'/m.UNIT;dest.parent.mkdir(parents=True)
            raw=json.dumps({'automation_enabled':enabled,'automation_kind':'image_wallpaper','automation_target':'all','interval_minutes':30,'checkpoint':'saved.safetensors','scene_kind':'woodland'}).encode()
            for name,data in [('settings.json',raw),('token',b'x'*40)]:
                (state/name).write_bytes(data);(state/name).chmod(0o600)
            calls=[];active=False
            def properties():
                return {'LoadState':'loaded' if dest.exists() else 'not-found','ActiveState':'active' if active else 'inactive','MainPID':'9' if active else '0','Transient':'no','FragmentPath':str(dest) if dest.exists() else ''}
            link=dest.parent/'graphical-session.target.wants'/m.UNIT
            original_unit=b'[Service]\nExecStart=/usr/bin/true\n[Install]\nWantedBy=graphical-session.target\n'
            if fail_reload:
                dest.write_bytes(original_unit)
                link.parent.mkdir();link.symlink_to(dest)
            def ctl(*args,check=True):
                nonlocal active
                calls.append(args);out=''
                if args[0]=='daemon-reload' and fail_reload and calls.count(args)==1:
                    raise subprocess.CalledProcessError(1,args)
                if args[0]=='is-active': out='active\n'
                elif args[0]=='is-enabled': out='enabled\n' if link.exists() else ('disabled\n' if dest.exists() else 'not-found\n')
                elif args[0]=='show': out='loaded\n'
                elif args[0]=='enable':
                    link.parent.mkdir(exist_ok=True)
                    if not link.exists(): link.symlink_to(dest)
                elif args[0]=='disable':
                    if link.is_symlink(): link.unlink()
                elif args[0]=='start': active=True
                return subprocess.CompletedProcess(args,0,out,'')
            settings=json.loads(raw)
            if enable_catchup: settings['catch_up_refresh']=True
            ready=settings|{'source_revision':SOURCE_REVISION,'service_version':'test','render_enabled':True,'apply_enabled':True,'displays':[{'id':'DP-2'}],'testing_override':{'active':False},'comfy_service':{'managed':True},'next_eligible_at':time.time()+1800,'guard':{'decision':'unknown'}}
            # Only fixture ownership mapping; production wrong-owner CLI is
            # separately exercised without this patch and must refuse.
            import types
            with contextlib.ExitStack() as stack:
                for obj,name,value in [(Path,'home',lambda:home),(m,'ctl',ctl),(m,'props',properties),
                    (m,'api',lambda token:ready),(m,'require_configured_owner',lambda:None),
                    (m.pwd,'getpwnam',lambda name:types.SimpleNamespace(pw_uid=ROOT.parent.parent.stat().st_uid)),
                    (m.socket,'socket',unittest.mock.MagicMock())]: stack.enter_context(patch.object(obj,name,value))
                stack.enter_context(patch.dict(os.environ,{'WAYLAND_DISPLAY':'fixture','XDG_RUNTIME_DIR':'/run/user/'+str(os.getuid())}))
                stack.enter_context(patch('displays.discover',return_value=([{'id':'DP-2'}],None)))
                stack.enter_context(patch.object(sys_module(),'argv',['installer','--manual-wallpapers','--managed-comfy']+(['--enable-catch-up-refresh'] if enable_catchup else [])))
                output=io.StringIO()
                if fail_reload:
                    with contextlib.redirect_stdout(output), self.assertRaises(subprocess.CalledProcessError): m.main()
                    self.assertEqual(dest.read_bytes(),original_unit)
                    self.assertTrue(link.exists())
                    self.assertEqual((state/'settings.json').read_bytes(),raw)
                    self.assertFalse(any(c[0] in ('start','stop','restart') for c in calls))
                    return
                with contextlib.redirect_stdout(output): m.main()
                expected_raw=json.dumps(settings,indent=2).encode() if enable_catchup else raw
                self.assertEqual((state/'settings.json').read_bytes(),expected_raw)
                self.assertTrue(link.is_symlink());self.assertEqual(link.resolve(),dest)
                self.assertNotIn('x'*40,output.getvalue())
                self.assertTrue(active)
                self.assertFalse(any('stop' in c or 'restart' in c for c in calls))
                backups=list(state.glob('controller-install-*'));self.assertEqual(len(backups),1)
                receipt=json.loads((backups[0]/'receipt.json').read_text())
                self.assertEqual(receipt['automation_enabled'],enabled)
                launch=json.loads((backups[0]/'launch.json').read_text())
                self.assertEqual(launch['argv'],['/usr/bin/python3',str(ROOT/'weather_controller.py'),'--state-dir',str(state),'--preview-checkpoint','saved.safetensors','--comfy-idle-seconds','300','--manual-wallpapers','--managed-comfy'])
                for forbidden in ('systemd-run','stop','restart','--automation-off','--reload-shell'):
                    self.assertFalse(any(forbidden in c for c in calls))
                self.assertEqual([c[0] for c in calls if c[0] in ('daemon-reload','enable','import-environment','start')],['daemon-reload','enable','import-environment','start'])
                active=False
                with contextlib.redirect_stdout(output): m.restore_backup(backups[0],dest,state)
                self.assertFalse(dest.exists());self.assertFalse(link.exists())
                self.assertEqual((state/'settings.json').read_bytes(),raw)

def sys_module():
    import sys
    return sys

if __name__=='__main__': unittest.main()
