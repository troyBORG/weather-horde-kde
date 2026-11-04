"""Fixture driver invoked by test_guided_update; never a production manager."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    source, scenario = sys.argv[1:]
    spec=importlib.util.spec_from_file_location('guided',source)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);state=root/'state';state.mkdir(mode=0o700)
        settings={'automation_enabled':False,'automation_kind':'image_wallpaper','automation_target':'all','interval_minutes':30,'location':{'fixture':'private'},'scene_overrides':{'portrait':'rural'},'holiday_preview_date':'2030-01-02'}
        if scenario=='auto-on': settings['automation_enabled']=True
        raw=(json.dumps(settings,indent=3)+'\n').encode()
        (state/'settings.json').write_bytes(raw);(state/'token').write_text('fixture-token')
        for p in state.iterdir():p.chmod(0o600)
        if scenario=='pending':
            (state/'wallpaper-restore.json').write_text(json.dumps({'fixture':{'state':'pending'}}))
            (state/'wallpaper-restore.json').chmod(0o600)
        events=[];started=False
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                if scenario=='auth-failure':self.send_error(401);return
                assert self.headers['Authorization']=='Bearer fixture-token'
                value=json.loads((state/'settings.json').read_bytes())
                value.update(source_revision='new' if started else 'old',state='rendering' if scenario=='timeout' else 'idle',render_enabled=True,apply_enabled=True,capabilities={'model_selection':True},testing_override={'active':False},comfy_service={'managed':True},displays=[{'id':'fixture'}])
                if started and scenario=='verify-failure':value['source_revision']='wrong'
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
            def do_PUT(self):
                events.append('api-off')
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert body=={'automation_enabled':False}
                data=json.loads((state/'settings.json').read_bytes());data.update(body)
                (state/'settings.json').write_text(json.dumps(data))
                self.do_GET()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        class Helper:
            UNIT='fixture.service'
            @staticmethod
            def private_read(p):return p.read_bytes()
            @staticmethod
            def atomic(p,b):p.write_bytes(b);p.chmod(0o600)
            @staticmethod
            def ctl(*args,**kwargs):
                nonlocal started
                # Execute a real child, but never systemctl or the owner manager.
                subprocess.run([sys.executable,'-c','pass'],check=True)
                events.append('ctl:'+args[0])
                if args[0]=='start':started=True
            @staticmethod
            def props():return {'ActiveState':'active' if started else 'inactive','MainPID':'1' if started else '0'}
        class Deployment:
            helper=Helper();old_root=root/'old'
            def __init__(self):self.state=state;self.saved={'settings':raw,'unit':b'old-unit','enabled':'disabled'};self.destination=root/'unit';self.destination.write_bytes(b'old-unit')
            def capture(self):
                self.saved['settings']=(state/'settings.json').read_bytes()
                return self.saved
            def enablement(self):return 'enabled' if scenario=='enablement-change' and 'port-check' in events else 'disabled'
            def require_stopped(self):
                assert not started
            def backup(self,saved):events.append('installer-backup')
            def install(self,saved):
                events.append('install');self.destination.write_bytes(b'new-unit')
                if scenario=='rollback':raise RuntimeError('fixture install readback failed')
            def verify(self,saved):assert self.destination.read_bytes()==b'new-unit'
            def rollback(self,saved):
                events.append('installer-rollback');self.destination.write_bytes(saved['unit'])
                assert self.destination.read_bytes()==b'old-unit'
        deployment=Deployment()
        class Fixture(m.OwnerUpdate):
            def identity(self):
                events.append('identity')
                if scenario=='concurrent-preferences' and events.count('identity')==2:
                    data=json.loads((state/'settings.json').read_bytes());data['interval_minutes']=60
                    (state/'settings.json').write_text(json.dumps(data))
            def port_state(self):
                events.append('port-check')
                if scenario=='foreign':raise RuntimeError('Foreign listener')
                return not (scenario=='port-retry' and events.count('port-check')<3)
            def expected_revision(self):return 'new'
        io=Fixture(deployment,timeout=.07,poll=.01)
        io.base='http://127.0.0.1:'+str(server.server_port)
        try:
            m.update(io);success=True
        except Exception as error:
            success=False;events.append('error:'+type(error).__name__)
        server.shutdown()
        print(json.dumps({'success':success,'events':events,'settings':json.loads((state/'settings.json').read_bytes()),'bytes_preserved':(state/'settings.json').read_bytes()==raw,'backups':len(list(state.glob('guided-update-*')))}))

if __name__=='__main__':main()
