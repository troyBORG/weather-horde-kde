#!/usr/bin/env python3
"""Owner-only sanitized runtime receipt; --deploy performs one checked 0.1.8 rollout.
Never renders, applies, enables automation/override, or restarts Plasma.
"""
import argparse, json, os, pwd, re, stat, subprocess, sys
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from portable_paths import require_owner as require_configured_owner


def require_owner():
    require_configured_owner()


def safe_text(value):
    text=str(value)
    if text.startswith('Command '): return 'Subprocess failed; inspect owner journal for the exact operation'
    text=re.sub(r'(?i)(bearer\s+|token[=: ]+)[^\s,]+',r'\1[redacted]',text)
    text=re.sub(r'file://\S+|/(?:home|mnt)/[^\s\"\']+', '[path]',text)
    return text[:400]


def sanitized_status(status):
    out={k:status.get(k) for k in ('service_version','source_revision','state','capabilities','render_enabled','apply_enabled','automation_enabled')}
    out['last_error']=safe_text(status.get('last_error',''))
    for key,fields in {
        'guard':('decision','reason','free_mib','observed_at'),
        'comfy_service':('state','reason','managed','owned'),
        'render_request':('state','reason'),
        'wallpaper_action':('state','target','verified','reason'),
        'testing_override':('active','remaining_seconds'),
    }.items():
        source=status.get(key) or {}
        out[key]={k:safe_text(source[k]) if isinstance(source[k],str) else source[k] for k in fields if k in source}
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy',action='store_true')
    args=parser.parse_args();require_owner()
    from displays import discover
    from wallpaper import PlasmaBackend
    path=Path.home()/'.local/state/weather-horde-kde/token'
    for directory in path.parents:
        st=directory.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid not in (0,os.getuid()) or st.st_mode & 0o022:
            raise RuntimeError('Unsafe token ancestor; no permission changes attempted')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        st=os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600 or st.st_nlink!=1:
            raise RuntimeError('Unsafe token metadata')
        token=stream.read(4097).strip()
    if not 32<=len(token)<=4096: raise RuntimeError('Invalid local authentication material')
    request=Request('http://127.0.0.1:8734/v1/status',headers={'Authorization':'Bearer '+token})
    with build_opener(ProxyHandler({})).open(request,timeout=15) as response: status=json.load(response)
    print('Authenticated runtime:',json.dumps(sanitized_status(status)),flush=True)
    for unit in ('weather-horde-kde.service','weather-horde-comfy.service'):
        result=subprocess.run(['systemctl','--user','show',unit,'--property=LoadState,ActiveState,SubState,MainPID,Result'],capture_output=True,text=True,timeout=10)
        print(unit, 'exit='+str(result.returncode),safe_text(result.stdout))
        result=subprocess.run(['journalctl','--user','-u',unit,'-n','25','--no-pager','-o','json'],capture_output=True,text=True,timeout=10)
        print('journal',unit,'exit='+str(result.returncode))
        for line in result.stdout.splitlines():
            try: message=json.loads(line).get('MESSAGE','')
            except ValueError: continue
            print(safe_text(str(message).replace(token,'[redacted]')))
    displays,error=discover()
    print('Display discovery:',safe_text(error))
    backend=PlasmaBackend()
    for display in displays:
        # Read-only mapping; no Image/SlidePaths or private wallpaper config output.
        try:
            snapshot=backend.snapshot(display)
            print('Plasma mapping:',json.dumps({'target':display['id'],**{k:snapshot[k] for k in ('desktop','screen','geometry','plugin')}}))
        except Exception as exc: print('Plasma mapping failed:',display['id'],type(exc).__name__,safe_text(exc))
    if args.deploy:
        sys.stdout.flush()
        subprocess.run([sys.executable,str(ROOT/'scripts/rollout-owner.py'),'--service-lifecycle','--manual-wallpapers'],check=True)
    else: print('Diagnostic only: no GPU, wallpaper, service or permission changes.')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Owner repair stopped:',type(exc).__name__,safe_text(exc),file=sys.stderr);sys.exit(1)
