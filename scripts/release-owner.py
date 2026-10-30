#!/usr/bin/env python3
"""Owner-only 0.1.10 rollout + optional single LEFT preview; never apply/restore.
Run in troyborg's KDE terminal. No override, downloads, batch or foreign Comfy.
"""
import argparse, hashlib, json, os, pwd, stat, subprocess, sys, time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from weather_controller import SOURCE_REVISION, SERVICE_VERSION
from scene import PROMPT_VERSION


def left_target(displays):
    if not displays: raise RuntimeError('No owner live displays')
    left=[d for d in displays if d['x']==min(x['x'] for x in displays) and d['height']>d['width'] and d['id']=='DP-2']
    if len(left)!=1: raise RuntimeError('Require uniquely leftmost portrait DP-2; no fallback to right/all')
    return left[0]


def check_status(status):
    if (status.get('automation_enabled') is not False or status.get('testing_override',{}).get('active') is not False or
        status.get('prompt_version')!=PROMPT_VERSION or status.get('service_version')!=SERVICE_VERSION or
        status.get('source_revision')!=SOURCE_REVISION):
        raise RuntimeError('Loaded revision or Auto OFF / testing override OFF not verified')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy',action='store_true')
    parser.add_argument('--render-left',action='store_true')
    parser.add_argument('--reload-shell',action='store_true')
    args=parser.parse_args()
    if pwd.getpwuid(os.getuid()).pw_name!='troyborg': raise RuntimeError('Run in troyborg KDE terminal; SSH jorden cannot authenticate/reload/render')
    from displays import discover
    from wallpaper import PlasmaBackend, atomic_json
    displays,error=discover()
    if error: raise RuntimeError(error)
    target=left_target(displays)
    # Preflight all source/package prerequisites before any owner service mutation.
    for path in [ROOT/'artifacts/org.troyborg.weatherhorde.plasmoid', ROOT/'artifacts/package-receipt.json',
                 ROOT/'astronomy_vendor.py',ROOT/'model_catalog.py',ROOT/'scripts/rollout-owner.py']:
        if not os.access(path,os.R_OK): raise RuntimeError('Not readable: '+str(path))
    if args.reload_shell and not args.deploy: raise RuntimeError('--reload-shell requires --deploy')
    if args.deploy:
        command=[sys.executable,str(ROOT/'scripts/rollout-owner.py'),'--manual-wallpapers']
        if args.reload_shell:command.append('--reload-shell')
        subprocess.run(command,check=True)
    state=Path.home()/'.local/state/weather-horde-kde'
    tokenfile=state/'token'
    for directory in tokenfile.parents:
        meta=directory.lstat()
        if stat.S_ISLNK(meta.st_mode) or meta.st_uid not in (0,os.getuid()) or meta.st_mode&0o022:
            raise RuntimeError('Unsafe token ancestor: '+str(directory))
    fd=os.open(tokenfile,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        meta=os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.getuid() or stat.S_IMODE(meta.st_mode)!=0o600 or meta.st_nlink!=1:
            raise RuntimeError('Unsafe token metadata')
        token=stream.read(4097).strip()
    if not 32<=len(token)<=4096: raise RuntimeError('Invalid authentication material')
    opener=build_opener(ProxyHandler({}))
    def api(path='/v1/status',body=None):
        req=Request('http://127.0.0.1:8734'+path, data=None if body is None else json.dumps(body).encode(),
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with opener.open(req,timeout=45) as response:return json.load(response)
    status=api();check_status(status)
    print('Authenticated:',status['service_version'],status['prompt_version'],status['source_revision'])
    if not args.render_left:
        print('No render requested. Auto OFF and testing override OFF verified.');return
    if status.get('observation',{}).get('active'): raise RuntimeError('Manual observation active; revert in widget before automatic-weather acceptance render')
    backend=PlasmaBackend();before={d['id']:backend.snapshot(d) for d in displays}
    # Current fresh owner GPU/game/VR policy is checked by the controller, including
    # stopped-service startup. Never substitute SSH GPU memory for owner guard.
    status=api('/v1/models/refresh',{});check_status(status)
    result=api('/v1/render',{'target':target['id'],'force':True})
    if result.get('state')!='queued': raise RuntimeError('Render deferred; no accepted GPU job: '+json.dumps(result))
    deadline=time.monotonic()+720
    while time.monotonic()<deadline:
        time.sleep(2); status=api();check_status(status)
        if status['state'] not in ('queued','rendering','rendering_guard_blocked','checking_weather'):break
    if status['state']!='image_preview_ready': raise RuntimeError('No validated sample: '+status['state']+' '+status.get('last_error',''))
    image=status['image_preview']
    if image.get('targets')!=[target['id']]: raise RuntimeError('Unexpected rendered target')
    path=state/'renders'/image['id']/'image.png'
    from PIL import Image
    with Image.open(path) as decoded:
        decoded.load()
        if decoded.size!=(target['width'],target['height']):raise RuntimeError('Native image size mismatch')
    after={d['id']:backend.snapshot(d) for d in displays}
    if after!=before: raise RuntimeError('A wallpaper changed externally; do not restore or overwrite it')
    receipt={'service_version':SERVICE_VERSION,'source_revision':SOURCE_REVISION,'prompt_version':PROMPT_VERSION,
             'target':target['id'],'image':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'automation_enabled':False,'testing_override':False,'wallpapers_unchanged':True,
             'visual_compliance':'NOT YET REVIEWED — inspect actual generated image; prompt tests are not image-quality proof',
             'image_metadata':image}
    atomic_json(state/'release-0.1.10-preview-receipt.json',receipt)
    print(json.dumps(receipt,indent=2))
    print('Actual image ready for visual inspection; no wallpaper was applied.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Release stopped:',type(exc).__name__,str(exc),file=sys.stderr);sys.exit(1)
