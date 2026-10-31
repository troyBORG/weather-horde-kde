import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

class LifecycleTests(unittest.TestCase):
    def test_guard_precedes_actual_systemctl_subprocess(self):
        import comfy_service
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root/'systemctl'
            exe.write_text('#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\np=Path(__file__).with_name("calls")\nwith p.open("a") as f: f.write(" ".join(sys.argv[1:])+"\\n")\nprint("ActiveState=inactive\\nMainPID=0\\nLoadState=loaded")\n')
            exe.chmod(0o700)
            manager = comfy_service.ComfyService(object(), systemctl=str(exe))
            with self.assertRaisesRegex(ValueError, 'game_active'):
                manager.ensure_ready(lambda: 'game_active')
            self.assertFalse((root/'calls').exists())

    def test_start_command_failure_is_failed_not_starting(self):
        from comfy_service import ComfyService
        from unittest.mock import Mock
        import subprocess
        transport=Mock(); transport.owned_gpu_pid.return_value=None
        m=ComfyService(transport)
        with patch.object(m,'unit',return_value={'LoadState':'loaded','ActiveState':'inactive'}), patch('comfy_service.port_occupied',return_value=False), patch.object(m,'command',side_effect=subprocess.CalledProcessError(1,'systemctl')):
            with self.assertRaisesRegex(ValueError,'start failed'): m.ensure_ready(lambda:'safe')
        self.assertEqual(m.state,'failed')

    def test_timeout_and_auth_failure_never_stop_or_submit(self):
        from comfy_service import ComfyService
        from unittest.mock import Mock
        from urllib.error import HTTPError
        for error in (OSError('offline'), HTTPError('http://127.0.0.1',401,'Unauthorized',{},None)):
            transport=Mock(); transport.owned_gpu_pid.return_value=None
            transport.request.side_effect=error
            m=ComfyService(transport,startup_seconds=.01)
            with patch.object(m,'unit',return_value={'LoadState':'loaded','ActiveState':'inactive','MainPID':'0'}), patch('comfy_service.port_occupied',return_value=False), patch.object(m,'command') as command:
                with self.assertRaisesRegex(ValueError,'authentication' if isinstance(error,HTTPError) else 'timeout'):
                    m.ensure_ready(lambda:'safe')
                self.assertEqual(m.state,'failed')
                command.assert_called_once_with('start','--no-block','weather-horde-comfy.service')
                transport.queue.assert_not_called()

    def test_external_listener_status_is_observed_without_stop_ownership(self):
        from comfy_service import ComfyService
        from unittest.mock import Mock
        transport=Mock(); transport.owned_gpu_pid.return_value=123
        transport.request.return_value={'queue_running':[], 'queue_pending':[]}
        m=ComfyService(transport)
        with patch.object(m,'command') as command:
            m.maintain()
            self.assertEqual(m.state,'ready')
            self.assertFalse(m.status()['owned'])
            transport.owned_gpu_pid.return_value=None
            with patch('comfy_service.port_occupied',return_value=False): m.maintain()
            self.assertEqual(m.state,'stopped')
            command.assert_not_called()

    def test_changed_pid_birth_prevents_stop(self):
        from comfy_service import ComfyService
        from unittest.mock import Mock
        import time
        transport=Mock(); transport.owned_gpu_pid.return_value=123; transport.listener=(123,1000,99)
        m=ComfyService(transport,idle_seconds=30); m.owned_identity=(123,1000,42); m.last_used=time.monotonic()-100
        with patch.object(m,'unit',return_value={'ActiveState':'active','MainPID':'123'}), patch.object(m,'command') as command:
            m.maintain(); command.assert_not_called()
        self.assertEqual(m.state,'busy')

class ControllerLifecycleTests(unittest.TestCase):
    def test_opt_in_status_and_offline_prestart_guard(self):
        from weather_controller import Controller
        with tempfile.TemporaryDirectory() as td:
            c = Controller(td, checkpoint='test', managed_comfy=True)
            self.assertEqual(c.status()['comfy_service']['state'], 'stopped')
            with patch('weather_controller.collect', return_value=({'decision':'game_active','observed_at':__import__('time').time(),'free_mib':24000}, None)) as collect:
                self.assertEqual(c.startup_guard(), 'game_active')
                self.assertIsNone(collect.call_args.args[1])

    def test_deferred_generate_has_persistent_reason_and_no_prompt_id(self):
        from weather_controller import Controller
        with tempfile.TemporaryDirectory() as td:
            c=Controller(td)
            c.guard={'decision':'game_active','reason':'game_process_detected','observed_at':__import__('time').time()}
            result=c.dispatch('POST','/v1/render',{'target':'all','force':True})
            self.assertEqual(result['state'],'deferred')
            self.assertEqual(c.status()['render_request']['reason'],'game_active')
            self.assertIsNone(c.status()['render_request']['prompt_id'])

    def test_verified_apply_status_does_not_claim_wallpaper_untouched(self):
        from weather_controller import Controller
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as td:
            c=Controller(td,render_guard=lambda:'safe')
            c.displays=[{'id':'DP-2'}]
            c.wallpaper=Mock(); c.wallpaper.available.return_value=[]
            c.wallpaper.apply.return_value={'state':'applied','target':'DP-2','preview_id':'a'*32,'verified':True}
            c.dispatch('POST','/v1/apply',{'target':'DP-2','preview_id':'a'*32,'confirmation':'Apply this validated preview'})
            self.assertEqual(c.status()['wallpaper_action']['state'],'applied')
            text=Path('plasma-widget/org.troyborg.weatherhorde/contents/ui/main.qml').read_text()
            self.assertIn('status.wallpaper_action',text)
            self.assertIn('Applied and read back on',text)

    def test_quarantine_retains_original_reason_when_current_guard_is_safe(self):
        from test_preview_pipeline import PipelineTests
        import time
        with tempfile.TemporaryDirectory() as td, patch('weather_controller.weather_preview',return_value={'positive':'test','negative':'test'}):
            fixture=PipelineTests()
            c,t=fixture.make(td,['safe','game_active','safe'])
            c.dispatch('POST','/v1/render',{'force':True})
            fixture.finish(c)
            c.guard={'decision':'safe','observed_at':time.time()}
            self.assertEqual(c.status()['quarantine']['decision'],'game_active')
            self.assertIsInstance(c.status()['quarantine']['at'],float)
            self.assertIsNone(c.status()['image_preview'])
            self.assertIn('game_active',c.status()['render_request']['reason'])

    def test_saved_image_apply_does_not_start_comfy_or_require_render_vram(self):
        from weather_controller import Controller
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as td:
            c=Controller(td,checkpoint='test',managed_comfy=True)
            c.displays=[{'id':'DP-2'}]
            c.wallpaper=Mock(); c.wallpaper.available.return_value=[]
            c.wallpaper.apply.return_value={'state':'applied','target':'DP-2','preview_id':'a'*32,'verified':True}
            with patch('weather_controller.collect',return_value=({'decision':'insufficient_vram','observed_at':__import__('time').time()},None)), patch.object(c.comfy_service,'ensure_ready') as start:
                result=c.dispatch('POST','/v1/apply',{'target':'DP-2','preview_id':'a'*32,'confirmation':'Apply this validated preview'})
                self.assertTrue(result['verified']); start.assert_not_called()
            for decision in ('game_active','vr_active','unknown','gpu_busy'):
                with patch('weather_controller.collect',return_value=({'decision':decision,'observed_at':__import__('time').time()},None)):
                    result=c.dispatch('POST','/v1/apply',{'target':'DP-2','preview_id':'a'*32,'confirmation':'Apply this validated preview'})
                    self.assertTrue(result['verified'])

    def test_lifecycle_ui_has_immediate_feedback(self):
        text=Path('plasma-widget/org.troyborg.weatherhorde/contents/ui/main.qml').read_text()
        self.assertIn('Checking eligibility — no Comfy job submitted yet', text)
        self.assertIn('status.render_request', text)
        self.assertIn('status.comfy_service', text)

class HttpLifecycleTests(unittest.TestCase):
    def test_real_subprocess_and_http_start_idle_stop(self):
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from comfy_preview import ComfyTransport
        from comfy_service import ComfyService
        queue = {'queue_running':[], 'queue_pending':[]}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                payload = queue if self.path == '/queue' else {'system':{}}
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(payload).encode())
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                exe = root/'systemctl'
                exe.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
root=Path(__file__).parent
with (root/'calls').open('a') as f: f.write(' '.join(sys.argv[1:])+'\\n')
state=root/'active'
if 'start' in sys.argv: state.touch()
if 'stop' in sys.argv: state.unlink(missing_ok=True)
print('LoadState=loaded\\nActiveState='+('active' if state.exists() else 'inactive')+'\\nMainPID='+('123' if state.exists() else '0'))
''')
                exe.chmod(0o700)
                transport = ComfyTransport('http://127.0.0.1:'+str(server.server_port))
                manager = ComfyService(transport, idle_seconds=30, startup_seconds=1, systemctl=str(exe))
                def identity(port): return (123, os.getuid(), 42) if (root/'active').exists() else None
                with patch('comfy_preview.listener_identity', side_effect=identity), patch('comfy_service.port_occupied',return_value=False):
                    manager.ensure_ready(lambda:'safe')
                    self.assertEqual(manager.state, 'ready')
                    manager.last_used = time.monotonic()-60
                    queue['queue_pending'] = [[0,'foreign',{}, {'client_id':'foreign'}]]
                    manager.maintain()
                    self.assertEqual(manager.state, 'busy')
                    self.assertTrue((root/'active').exists())
                    queue['queue_pending'] = []
                    manager.last_used = time.monotonic()-60
                    manager.maintain(inflight=True)
                    self.assertTrue((root/'active').exists())
                    manager.last_used = time.monotonic()-60
                    manager.maintain()
                    self.assertEqual(manager.state, 'stopping')
                    manager.maintain()
                    self.assertEqual(manager.state, 'stopped')
                    self.assertIn('--user start --no-block weather-horde-comfy.service', (root/'calls').read_text())
                    # A manually started server is usable but never stop-owned.
                    (root/'active').touch()
                    external = ComfyService(transport, idle_seconds=30, systemctl=str(exe))
                    external.ensure_ready(lambda:'safe')
                    external.last_used = time.monotonic()-60
                    external.maintain()
                    self.assertFalse(external.status()['owned'])
                    self.assertTrue((root/'active').exists())
        finally:
            server.shutdown(); server.server_close()

class InstallerTests(unittest.TestCase):
    def test_installer_writes_verified_unit_without_start_or_enable(self):
        import importlib.util
        from types import SimpleNamespace
        spec=importlib.util.spec_from_file_location('install_service','scripts/install-comfy-service.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        mask=os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory(dir=Path.home()) as td:
                home=Path(td)
                source=home/'repo';(source/'systemd').mkdir(parents=True)
                (source/'systemd/weather-horde-comfy.service').write_bytes(Path('systemd/weather-horde-comfy.service').read_bytes())
                token=home/'token';token.write_text('fixture-preserve')
                def run(command, **kwargs): return SimpleNamespace(stdout='loaded\n' if 'show' in command else '',returncode=0)
                with patch.object(module,'ROOT',source), patch.object(module,'require_owner'), patch.object(module.Path,'home',return_value=home), patch.object(module.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid())), patch.object(module.subprocess,'run',side_effect=run) as commands, patch.object(module.sys,'argv',['installer']):
                    expected_unit = module.render_unit()
                    module.main()
                unit=home/'.config/systemd/user/weather-horde-comfy.service'
                self.assertEqual(unit.read_text(), expected_unit)
                self.assertEqual(token.read_text(),'fixture-preserve')
                for call in commands.call_args_list:
                    self.assertNotIn('enable',call.args[0]);self.assertNotIn('start',call.args[0]);self.assertNotIn('--reload-shell',call.args[0])
                self.assertTrue(list((home/'.local/state/weather-horde-comfy').glob('service-install-*/receipt.json')))
        finally: os.umask(mask)

    def test_unit_and_owner_only_installer(self):
        import importlib.util
        unit = Path('systemd/weather-horde-comfy.service')
        self.assertTrue(unit.exists(), 'On-demand user unit missing')
        text = unit.read_text()
        self.assertNotIn('WantedBy=', text)
        self.assertIn('ReadOnlyPaths=@COMFY_READONLY@', text)
        self.assertIn('UMask=0077', text)
        spec=importlib.util.spec_from_file_location('install_service', 'scripts/install-comfy-service.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with patch.dict('os.environ', {'WEATHER_HORDE_OWNER':'fixture-owner'}), patch.object(module.pwd,'getpwnam') as user, patch.object(module.subprocess,'run') as run:
            user.return_value.pw_uid=-1
            with self.assertRaisesRegex(RuntimeError,'owner'): module.require_owner()
            run.assert_not_called()

if __name__ == '__main__': unittest.main()
