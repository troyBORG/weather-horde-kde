#!/usr/bin/env python3
"""Owner Comfy handoff. Default read-only; --start explicitly starts, never stops.
Run in the configured owner's KDE terminal. No render submission or controller changes.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import sys
from urllib.request import build_opener, ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portable_paths import comfy_root, require_owner as require_configured_owner
ROOT=comfy_root()

def require_launch(uid, owner_uid, listeners):
    if uid != owner_uid:
        raise RuntimeError("Run in the configured owner's KDE graphical terminal.")
    if listeners:
        raise RuntimeError('8188 is occupied (listener UID/inode: '+repr(listeners)+'). No process was stopped. Arrange a separately authorized idle-only stop of the verified listener; never sudo/kill an unverified listener.')

def listeners():
    found=[]
    for file in ('/proc/net/tcp','/proc/net/tcp6'):
        for line in Path(file).read_text().splitlines()[1:]:
            row=line.split()
            if row[1].split(':')[-1]=='1FFC' and row[3]=='0A':
                found.append((int(row[7]),row[9]))
    return found

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',action='store_true',help='Explicit start only after old Comfy is separately stopped; stays in foreground')
    args=parser.parse_args()
    owner=require_configured_owner()
    if os.getuid()!=owner.pw_uid:
        raise RuntimeError("Run in the configured owner's KDE graphical terminal.")
    paths=[ROOT/'main.py',ROOT/'.venv/bin/python',ROOT/'extra_model_paths.yaml']
    for path in paths:
        if not os.access(path,os.R_OK | (os.X_OK if path.is_dir() or path.name=='python' else 0)):
            raise RuntimeError('Not accessible: '+str(path))
    print('Shared interpreter, main.py and model configuration are accessible. No permissions changed.')
    rows=listeners()
    if rows:
        # GET only; no interrupts, queue deletes, or prompt submissions.
        opener=build_opener(ProxyHandler({}))
        try:
            with opener.open('http://127.0.0.1:8188/queue',timeout=5) as response:
                q=json.load(response)
            if not isinstance(q['queue_running'],list) or not isinstance(q['queue_pending'],list):
                raise ValueError('Invalid queue')
            print('Current queue counts: running='+str(len(q['queue_running']))+', pending='+str(len(q['queue_pending'])))
            if q['queue_running'] or q['queue_pending']:
                raise RuntimeError('Comfy is busy. Leave it running; no migration.')
        except (OSError,ValueError,KeyError) as exc:
            raise RuntimeError('Occupied port is not a verified idle Comfy queue; refusing: '+str(exc))
    require_launch(os.getuid(),owner.pw_uid,rows)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',8188))
    print('Port available. Existing shared temp is NOT used. Shared model library remains untouched.')
    if not args.start:
        print('Read-only preflight complete. --start is a separate explicit action; no service started.')
        return
    # Recheck immediately before creating owner-local state. Comfy itself must
    # successfully bind; a race cannot cause us to stop another process.
    require_launch(os.getuid(),owner.pw_uid,listeners())
    os.umask(0o077)
    state=Path(owner.pw_dir)/'.local/state/weather-horde-comfy'
    for directory in [state]+[state/n for n in ('output','input','user','scratch','cache')]:
        if directory.is_symlink(): raise RuntimeError('Refusing symlink: '+str(directory))
        directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
            raise RuntimeError('Owner-local directory must already be private 0700: '+str(directory))
    command=[str(ROOT/'.venv/bin/python'),str(ROOT/'main.py'),'--listen','127.0.0.1','--port','8188',
             '--disable-auto-launch','--disable-all-custom-nodes',
             '--output-directory',str(state/'output'),'--input-directory',str(state/'input'),
             '--user-directory',str(state/'user'),'--temp-directory',str(state/'scratch')]
    env=os.environ.copy(); env.update(PYTHONDONTWRITEBYTECODE='1',XDG_CACHE_HOME=str(state/'cache'))
    os.chdir(ROOT)
    print('Starting owner Comfy; no queued render. For terminal-independent operation use scripts/install-comfy-service.py.',flush=True)
    os.execve(command[0],command,env)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Handoff stopped: '+str(exc),file=sys.stderr)
        sys.exit(1)
