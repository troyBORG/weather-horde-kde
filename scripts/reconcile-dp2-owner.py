#!/usr/bin/env python3
"""Read-only sanitized DP-2 transaction diagnostic. No token reads or wallpaper writes.
--reconcile only edits a semantically matching pending receipt, with controller stopped.
"""
import argparse, hashlib, json, os, pwd, socket, stat, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SAFE_KEYS=set('desktop activity screen geometry plugin image fill settings group values FillMode Image General'.split())
SAFE_VALUES={'General','org.kde.image','org.kde.slideshow'}

def fingerprint(value):
    return 'sha256:'+hashlib.sha256(str(value).encode()).hexdigest()[:16]

def sanitize(value):
    if isinstance(value,dict): return {k if k in SAFE_KEYS else fingerprint(k):sanitize(v) for k,v in value.items()}
    if isinstance(value,list): return [sanitize(v) for v in value]
    if isinstance(value,str): return value if value in SAFE_VALUES or value in tuple(str(i) for i in range(7)) else fingerprint(value)
    return value

def differences(a,b,path=''):
    if type(a)!=type(b): return [path or '/']
    if isinstance(a,dict):
        out=[]
        for k in sorted(set(a)|set(b)):
            p=path+'/'+(k if k in SAFE_KEYS else fingerprint(k))
            out.extend([p] if k not in a or k not in b else differences(a[k],b[k],p))
        return out
    if isinstance(a,list):
        if len(a)!=len(b): return [path+'/length']
        return [p for i,(x,y) in enumerate(zip(a,b)) for p in differences(x,y,path+'/'+str(i))]
    return [] if a==b else [path or '/']

def require_owner():
    if pwd.getpwuid(os.getuid()).pw_name!='troyborg':
        raise RuntimeError('Run in the troyborg KDE owner terminal; no cross-user access')

def require_stopped():
    try:
        with socket.create_connection(('127.0.0.1',8734),timeout=2): pass
    except ConnectionRefusedError: pass
    else: raise RuntimeError('Stop the owner controller before explicit reconciliation')
    result=subprocess.run(['systemctl','--user','show','weather-horde-kde.service','--property=LoadState,ActiveState'],capture_output=True,text=True,timeout=10)
    properties=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    absent=properties=={'LoadState':'not-found','ActiveState':'inactive'}
    if (result.returncode!=0 and not (result.returncode==1 and absent)) or properties.get('ActiveState') not in ('inactive','failed'):
        raise RuntimeError('Owner controller service must be verifiably stopped')
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal(): continue
        try:
            if process.stat().st_uid!=os.getuid(): continue
            args=(process/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError,PermissionError): continue
        if any(Path(os.fsdecode(a)).name=='weather_controller.py' for a in args if a):
            raise RuntimeError('A controller process is still running; refusing receipt edit')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group()
    actions.add_argument('--reconcile',action='store_true')
    actions.add_argument('--accept-current',action='store_true',help='Explicitly retire stale DP-2 receipt without restoring wallpaper; controller must be stopped')
    args=parser.parse_args();require_owner()
    from displays import discover
    from wallpaper import WallpaperManager, PlasmaBackend, canonical_snapshot
    root=Path.home()/'.local/state/weather-horde-kde'
    # Private receipt only, never token; refuse unsafe links/ownership before reading.
    path=root/'wallpaper-restore.json'
    for ancestor in path.parents:
        st=ancestor.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid not in (0,os.getuid()) or st.st_mode & 0o022:
            raise RuntimeError('Unsafe receipt ancestor; no permissions changed')
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600 or st.st_nlink!=1:
        raise RuntimeError('Unsafe receipt metadata; unchanged')
    displays,error=discover()
    targets=[d for d in displays if d['id']=='DP-2']
    if error or len(targets)!=1: raise RuntimeError('Unique live DP-2 unavailable')
    manager=WallpaperManager(root,PlasmaBackend())
    receipt=path.read_bytes()
    report=manager.reconcile_pending(targets[0])
    out={k:report[k] for k in ('target','state','match','identity_geometry_match','verified')}
    for side in ('before','after','current'): out[side]=sanitize(report[side])
    out['difference_paths']={side:differences(report[side],report['current']) for side in ('before','after')}
    out['semantic_difference_paths']={side:differences(canonical_snapshot(report[side]),canonical_snapshot(report['current'])) for side in ('before','after')}
    print(json.dumps(out,indent=2),flush=True)
    if args.reconcile or args.accept_current:
        from receipt_lock import state_lock
        require_stopped()
        with state_lock(root,exclusive=True):
            require_stopped()
            if (root/'inflight.json').exists():
                raise RuntimeError('Unresolved controller job; receipt retained')
            if args.accept_current:
                result=manager.accept_current(targets[0],report['current'],receipt,confirmed=True)
            else:
                result=manager.reconcile_pending(targets[0],commit=True)
            print(json.dumps({k:result[k] for k in ('target','state','verified')}))
            if args.accept_current: print('Private full journal and current snapshot archived: '+result['archive'])
    else: print('Read-only: no journal, wallpaper, GPU, service, or permission changes.')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        # Do not echo arbitrary exception values, config, private paths or commands.
        print('DP-2 helper refused: '+type(exc).__name__+'. Receipt retained; check owner/session, pending receipt, matching activity/geometry and stopped controller for explicit actions.',file=sys.stderr)
        sys.exit(1)
