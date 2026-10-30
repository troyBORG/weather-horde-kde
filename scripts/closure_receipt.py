"""Read-only live receipt plus isolated CPU/Qt tests; never submit Comfy work."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from comfy_preview import ComfyTransport, build_workflow
from safety import collect

root=Path(__file__).resolve().parents[1]
os.chdir(root)
def run(*args):
    p=subprocess.run(args,capture_output=True,text=True)
    return {'exit_code':p.returncode,'output':p.stdout+p.stderr}

before=run('ps','-p','137121,112161','-o','pid=,uid=,lstart=,comm=')
index_before=hashlib.sha256((root/'.git/index').read_bytes()).hexdigest()
tests=run('python3','-m','unittest','discover','-s','tests','-v')
(root/'artifacts/closure-tests.log').write_text(tests['output'])
if tests['exit_code']: raise RuntimeError(tests['output'])
count=int(re.search(r'Ran (\d+) tests',tests['output']).group(1))
package=run('python3','scripts/package.py')
if package['exit_code']: raise RuntimeError(package['output'])
t=ComfyTransport()
t.validate_upscaler(build_workflow('read-only-contract-check','NOT SUBMITTED','NOT SUBMITTED',3440,1440,1))
guard,_=collect(transport=t)
after=run('ps','-p','137121,112161','-o','pid=,uid=,lstart=,comm=')
index_after=hashlib.sha256((root/'.git/index').read_bytes()).hexdigest()
receipt={'timestamp':time.time(),'tests_passed':count,'test_log':'artifacts/closure-tests.log',
    'real_plasma_root_loaded': 'PLASMA_PACKAGE_ROOT_PASS' in tests['output'],
    'qml_http_pass':'QML_HTTP_INTEGRATION_PASS' in tests['output'],
    'root_warning_absent':'not the root QML item' not in tests['output'],
    'live_upscale_contract_read_only':'passed','live_guard':guard,
    'live_processes_before':before,'live_processes_after':after,'live_processes_unchanged':before==after,
    'existing_service':run('systemctl','--user','is-active','weather-horde-preview.service'),
    'index_sha256':index_after,'index_unchanged':index_before==index_after=='bd81cc9407827c48f7b2d4b5dd593ed5474e702932b6e55969fb5b7e2811cb1f',
    'graphical_owner':run('ps','-C','plasmashell','-o','uid=,pid='),
    'owner_package_dir_writable':os.access('/home/troyborg/.local/share/plasma/plasmoids',os.W_OK),
    'live_package_installed':Path('/home/troyborg/.local/share/plasma/plasmoids/org.troyborg.weatherhorde').exists(),
    'package':json.loads((root/'artifacts/package-receipt.json').read_text()),
    'git_diff_check':run('git','diff','--check'),'git_cached_check':run('git','diff','--cached','--check'),
    'gpu_renders_performed':False,'wallpaper_changes':False,'existing_services_restarted':False,
    'deployment':'source/staged package only; existing live controller remains old prompt-only code'}
assert receipt['live_processes_unchanged'] and receipt['index_unchanged']
assert receipt['existing_service']['output'].strip()=='active'
assert not receipt['git_diff_check']['exit_code'] and not receipt['git_cached_check']['exit_code']
(root/'artifacts/closure-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
