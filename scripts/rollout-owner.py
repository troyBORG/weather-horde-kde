#!/usr/bin/env python3
"""Owner-only rollout, diagnostics and optional controlled end-to-end exercise.
Default: no GPU job, no wallpaper write, automation OFF, override OFF.
No privilege escalation, foreign bus access, or permission repair.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from displays import discover
from safety import collect
from comfy_preview import ComfyTransport
from wallpaper import PlasmaBackend, atomic_json
from weather_controller import SOURCE_REVISION
UNIT='weather-horde-kde.service'
PACKAGE='org.troyborg.weatherhorde'


def require_owner():
    if pwd.getpwuid(os.getuid()).pw_name!='troyborg':
        raise RuntimeError('Run in the troyborg KDE owner terminal; SSH jorden cannot restart or authenticate this service')
    displays,error=discover()
    if error or not displays: raise RuntimeError('Owner graphical environment required: '+error)
    return displays


def require_idle(status, queue, journal):
    if journal or status.get('state') in ('queued','rendering','rendering_guard_blocked','failed_unreconciled'):
        raise RuntimeError('Controller job is active/unreconciled; no deployment')
    if queue.get('queue_running')!=[] or queue.get('queue_pending')!=[]:
        raise RuntimeError('Comfy queue is not verifiably idle; no deployment')


def idle_queue(transport):
    """Absent listener is stopped, never an authentication failure or idle guess."""
    from pathlib import Path
    occupied = any(row.split()[1].split(':')[-1] == '1FFC' and row.split()[3] == '0A'
                   for file in ('/proc/net/tcp', '/proc/net/tcp6')
                   for row in Path(file).read_text().splitlines()[1:])
    if not occupied: return {'queue_running':[], 'queue_pending':[]}
    try:
        result = transport.request('/queue')
    except HTTPError as exc:
        raise RuntimeError('Comfy authentication rejected' if exc.code in (401,403) else 'Comfy HTTP readiness failed') from exc
    except (OSError, ValueError) as exc:
        raise RuntimeError('Comfy listener occupied but unhealthy; no deployment') from exc
    if transport.owned_gpu_pid() is None: raise RuntimeError('Comfy listener is not verified same-owner/idle')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--service-lifecycle',action='store_true', help='Enable on-demand service management; preserve existing wallpaper capability')
    parser.add_argument('--comfy-idle-seconds',type=int,default=300)
    parser.add_argument('--manual-wallpapers',action='store_true')
    parser.add_argument('--reload-shell',action='store_true',help='Explicit Plasma UI-only restart after readback; never KWin/session')
    parser.add_argument('--exercise-target',help='Explicit connector: submit ONE guarded native preview then apply/read back; no override')
    args=parser.parse_args()
    displays=require_owner()
    if not 30 <= args.comfy_idle_seconds <= 86400: raise RuntimeError('Invalid idle timeout')
    if args.service_lifecycle and args.exercise_target: raise RuntimeError('Service installation never exercises GPU/wallpaper')
    if args.exercise_target and not args.manual_wallpapers: raise RuntimeError('Exercise requires --manual-wallpapers')
    if args.exercise_target:
        left=[d for d in displays if d['height']>d['width'] and d.get('x')==min(x['x'] for x in displays)]
        if len(left)!=1 or left[0]['id']!=args.exercise_target:
            raise RuntimeError('Live test authorized ONLY for the uniquely leftmost portrait output; no right/all-monitor test')
    state=Path.home()/'.local/state/weather-horde-kde'
    token_file=state/'token'
    for directory in [state,*state.parents]:
        metadata=directory.lstat()
        if stat.S_ISLNK(metadata.st_mode) or metadata.st_mode & 0o022 or metadata.st_uid not in (0,os.getuid()):
            raise RuntimeError('Unsafe pairing ancestor: '+str(directory)+'; permissions were not modified')
    metadata=token_file.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode)!=0o600 or metadata.st_uid!=os.getuid() or metadata.st_nlink!=1:
        raise RuntimeError('Private token ownership/mode invalid')
    token=token_file.read_text().strip() # owner context only, never printed or argv
    opener=build_opener(ProxyHandler({}))
    def api(path='/v1/status',body=None,method='GET'):
        req=Request('http://127.0.0.1:8734'+path,method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with opener.open(req,timeout=45) as response: return json.load(response)
    transport=ComfyTransport()
    status=api()
    require_idle(status,idle_queue(transport),(state/'inflight.json').exists())
    # Stopped Comfy is valid for lifecycle installation; no GPU start here.
    print('Authenticated live service:',status.get('service_version','legacy (no handshake)'),'; capabilities:',status.get('capabilities',{}))
    print('Live guard:',json.dumps(status.get('guard',{})))
    print('Native monitors:',json.dumps(displays))
    # Real owner-context diagnostics, not a cross-UID approximation.
    first,prior=collect(None,transport);time.sleep(10)
    guard,_=collect(prior,transport)
    print('Fresh owner diagnostic:',json.dumps(guard))
    if args.check_only: return
    if args.reload_shell and guard['decision'] in ('game_active','vr_active'):
        raise RuntimeError('Game/VR detected; defer Plasma UI reload')
    spec=importlib.util.spec_from_file_location('installer',ROOT/'scripts/install-auto-pairing.py')
    installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
    installer.verify_release()
    # Exact owner controller identity before any service mutation.
    def service_pid():
        return int(subprocess.run(['systemctl','--user','show',UNIT,'--property=MainPID','--value'],check=True,capture_output=True,text=True).stdout.strip())
    transient=subprocess.run(['systemctl','--user','show',UNIT,'--property=Transient','--value'],check=True,capture_output=True,text=True).stdout.strip()
    if transient!='yes': raise RuntimeError('Expected a transient owner service; refusing to replace a static/unknown unit')
    pid=service_pid()
    process=Path('/proc')/str(pid)
    if pid<=0 or process.stat().st_uid!=os.getuid(): raise RuntimeError('Controller unit owner mismatch')
    command=[os.fsdecode(x) for x in (process/'cmdline').read_bytes().split(b'\0') if x]
    if len(command)<2 or Path(command[1]).resolve()!=ROOT/'weather_controller.py': raise RuntimeError('Refusing to replace an unrelated service')
    allowed={'--state-dir','--preview-checkpoint','--port','--automation-off','--manual-wallpapers','--managed-comfy','--comfy-idle-seconds'}
    if any(x.startswith('--') and x not in allowed for x in command[2:]): raise RuntimeError('Unknown service flags; manual review required')
    checkpoint=command[command.index('--preview-checkpoint')+1] if '--preview-checkpoint' in command else None
    if args.service_lifecycle:
        if not checkpoint: raise RuntimeError('Existing controller must have an explicit preview checkpoint')
        args.manual_wallpapers = args.manual_wallpapers or '--manual-wallpapers' in command
    backend=PlasmaBackend()
    snapshots={d['id']:backend.snapshot(d) for d in displays}
    backups=state/'rollout-backups';backups.mkdir(exist_ok=True,mode=0o700)
    backup=Path(tempfile.mkdtemp(prefix='rollout-',dir=backups))
    installed=Path.home()/'.local/share/plasma/plasmoids'/PACKAGE
    if installed.exists(): shutil.copytree(installed,backup/'installed-package')
    if (state/'settings.json').exists(): shutil.copy2(state/'settings.json',backup/'settings.json')
    atomic_json(backup/'before.json',{'service_command':command,'service_pid':pid,'wallpapers':snapshots,
        'token_uid':metadata.st_uid,'token_mode':'0600','live_service_version':status.get('service_version','legacy'),
        'note':'Old in-memory Python code cannot be recovered from disk; rollback uses validated current source in preview-only mode.'})
    # Save exact staged source too; never overwrite the secret token during rollback.
    shutil.copytree(ROOT,backup/'source',ignore=shutil.ignore_patterns('.git','artifacts','__pycache__','*.so'))
    rollback='''#!/usr/bin/env python3
# Emergency UI rollback only. Run as owner after checking Comfy queue is idle.
# Does not touch wallpapers or token, restart a controller, or enable automation.
import pathlib, shutil, subprocess
here=pathlib.Path(__file__).resolve().parent
source=here/'installed-package'
if not source.is_dir(): raise SystemExit('No previous package backup')
dest=pathlib.Path.home()/'.local/share/plasma/plasmoids/org.troyborg.weatherhorde'
shutil.copytree(source,dest,dirs_exist_ok=True)
for p in source.rglob('*'):
    if p.is_file(): assert p.read_bytes()==(dest/p.relative_to(source)).read_bytes()
subprocess.run(['systemctl','--user','restart','plasma-plasmashell.service'],check=True)
print('Previous package restored. Token/settings/wallpaper not changed.')
'''
    (backup/'rollback-ui.py').write_text(rollback)
    print('Backup and rollback:',backup)
    api('/v1/settings',{'automation_enabled':False},'PUT')
    status=api()
    if status['automation_enabled']: raise RuntimeError('Could not pause automation')
    require_idle(status,idle_queue(transport),(state/'inflight.json').exists())
    if service_pid()!=pid: raise RuntimeError('Controller changed during preflight')
    installer.install(False)
    require_idle(api(),idle_queue(transport),(state/'inflight.json').exists())
    subprocess.run(['systemctl','--user','stop',UNIT],check=True)
    # Transient unit goes away with --collect; wait boundedly rather than racing.
    for _ in range(30):
        load=subprocess.run(['systemctl','--user','show',UNIT,'--property=LoadState','--value'],capture_output=True,text=True).stdout.strip()
        if load=='not-found': break
        time.sleep(.2)
    launch=['systemd-run','--user','--collect','--unit=weather-horde-kde',
        '--property=Type=exec','--property=Restart=on-failure','--property=UMask=0077',
        '--property=NoNewPrivileges=yes','--property=PartOf=graphical-session.target','--working-directory='+str(ROOT)]
    for key in ('XDG_RUNTIME_DIR','XDG_SESSION_TYPE','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','XDG_CURRENT_DESKTOP'):
        if key in os.environ: launch.append('--setenv='+key+'='+os.environ[key])
    launch+=['/usr/bin/python3',str(ROOT/'weather_controller.py'),'--state-dir',str(state),'--automation-off']
    if checkpoint: launch+=['--preview-checkpoint',checkpoint]
    if args.service_lifecycle or '--managed-comfy' in command:
        launch+=['--managed-comfy','--comfy-idle-seconds',str(args.comfy_idle_seconds)]
    if args.manual_wallpapers: launch+=['--manual-wallpapers']
    subprocess.run(launch,check=True)
    status=None
    for _ in range(30):
        try:
            status=api()
            if status.get('source_revision')==SOURCE_REVISION and status.get('displays'): break
        except (OSError,ValueError): pass
        time.sleep(1)
    if (not status or status.get('source_revision')!=SOURCE_REVISION or not status.get('displays')
            or status.get('capabilities',{}).get('manual_apply') != args.manual_wallpapers
            or status.get('render_enabled') != bool(checkpoint)
            or status.get('automation_enabled') or status.get('testing_override',{}).get('active')
            or (args.service_lifecycle and not status.get('comfy_service',{}).get('managed'))):
        raise RuntimeError('New service revision/safety readback failed; no GPU or wallpaper action attempted')
    if token_file.read_text().strip()!=token or stat.S_IMODE(token_file.stat().st_mode)!=0o600:
        raise RuntimeError('Token unexpectedly changed')
    if args.reload_shell:
        # No stable code-reload API exists: reloadConfig does not invalidate QML.
        # A UI-only shell restart is explicit; KWin and applications are untouched.
        subprocess.run(['systemctl','--user','restart','plasma-plasmashell.service'],check=True)
        subprocess.run(['systemctl','--user','is-active','--quiet','plasma-plasmashell.service'],check=True)
    receipt={'service_version':status['service_version'],'source_revision':status['source_revision'],
        'capabilities':status['capabilities'],'guard':status['guard'],'automation_enabled':False,
        'override_active':False,'gpu_submitted':False,'wallpaper_changed':False,'backup':str(backup)}
    atomic_json(backup/'after.json',receipt)
    if args.exercise_target:
        for _ in range(4):
            status=api()
            if status.get('guard',{}).get('decision')=='safe': break
            time.sleep(10)
        if status.get('guard',{}).get('decision')!='safe': raise RuntimeError('Exercise deferred by guard; rollout succeeded; no GPU work submitted')
        result=api('/v1/render',{'target':args.exercise_target,'force':True},'POST')
        if result.get('state')!='queued': raise RuntimeError('Exercise deferred: '+json.dumps(result))
        receipt['gpu_submitted']=True;atomic_json(backup/'after.json',receipt)
        for _ in range(330):
            time.sleep(2);status=api()
            if status['state'] not in ('queued','rendering','rendering_guard_blocked','checking_weather'): break
        if status['state']!='image_preview_ready': raise RuntimeError('No validated preview: '+status['state']+' '+status.get('last_error',''))
        image=status['image_preview']
        result=api('/v1/apply',{'target':args.exercise_target,'preview_id':image['id'],'confirmation':'Apply this validated preview'},'POST')
        if result.get('state')!='applied' or not result.get('verified'): raise RuntimeError('Apply not verified')
        final_snapshots={d['id']:backend.snapshot(d) for d in displays}
        for connector,before in snapshots.items():
            if connector!=args.exercise_target and final_snapshots[connector]!=before:
                raise RuntimeError('Unselected monitor changed since preflight; inspect receipt; never overwrite slideshow')
        receipt['unselected_monitors_unchanged']=True
        receipt['wallpapers_after']=final_snapshots
        receipt.update(wallpaper_changed=True,target=args.exercise_target,preview_id=image['id'],image_sha256=image['sha256'],apply=result)
        atomic_json(backup/'after.json',receipt)
        shot=backup/'both-monitors-after.png'
        subprocess.run(['spectacle','--background','--nonotify','--fullscreen','--output',str(shot)],check=True,timeout=30)
        from PIL import Image
        with Image.open(shot) as image: image.verify()
        receipt['screenshot']=str(shot);atomic_json(backup/'after.json',receipt)
    print(json.dumps(receipt,indent=2))
    print('Verified receipt:',backup/'after.json')
    print('If UI still old, use --reload-shell or log out/in; Pair never reloads controller code.')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Rollout stopped safely: '+str(exc),file=sys.stderr);sys.exit(1)
