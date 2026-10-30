"""Isolated real CLI smoke: ephemeral HTTP, no GPU configuration or wallpaper adapter."""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='weather-horde-smoke-') as tmp:
    root=Path(tmp)
    process=subprocess.Popen([sys.executable,str(ROOT/'weather_controller.py'),'--port','0','--state-dir',str(root),'--automation-off'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        line=process.stdout.readline().strip()
        port=int(line.rsplit(':',1)[1])
        token=(root/'token').read_text().strip()
        opener=build_opener(ProxyHandler({}))
        def request(path,method='GET',body=None,authenticated=True):
            headers={'Content-Type':'application/json'}
            if authenticated: headers['Authorization']='Bearer '+token
            req=Request(f'http://127.0.0.1:{port}'+path,method=method,headers=headers,data=None if body is None else json.dumps(body).encode())
            with opener.open(req,timeout=10) as r:return json.load(r)
        status=request('/v1/status')
        assert status['service_version']=='0.1.6'
        assert not status['automation_enabled'] and not status['apply_enabled'] and not status['render_enabled']
        assert not status['testing_override']['active']
        for path,method,body,auth,expected in [('/v1/status','GET',None,False,401),('/v1/apply','POST',{},False,401),('/v1/testing-override','PUT',{'enabled':True},True,400),('/v1/apply','POST',{'target':'all'},True,400)]:
            try: request(path,method,body,auth);raise AssertionError('Unexpected accepted request')
            except HTTPError as e: assert e.code==expected; e.close()
        receipt={'isolated_real_cli':True,'service_version':status['service_version'],'source_revision':status['source_revision'],
            'capabilities':status['capabilities'],'auth_rejections_verified':True,'unconfirmed_override_rejected':True,
            'unconfigured_apply_rejected':True,'automation_enabled':False,'override_enabled':False,'gpu_submitted':False,'wallpaper_changed':False}
        (ROOT/'artifacts/cli-smoke-0.1.6.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt,indent=2))
    finally:
        process.terminate();process.wait(timeout=20)
        process.stdout.close();process.stderr.close()
