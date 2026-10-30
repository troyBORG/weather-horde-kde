#!/usr/bin/env python3
"""Install on-demand Comfy user unit and reload the verified owner controller.
Never starts/stops Comfy, renders or changes wallpapers. Plasma reload is opt-in.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UNIT = 'weather-horde-comfy.service'


def require_owner():
    if pwd.getpwuid(os.getuid()).pw_name != 'troyborg' or os.getuid() == 0:
        raise RuntimeError("Run as troyborg in the KDE terminal, never root or jorden")


def private(directory):
    if directory.is_symlink(): raise RuntimeError('Refusing symlink: '+str(directory))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    meta = directory.stat()
    if meta.st_uid != os.getuid() or stat.S_IMODE(meta.st_mode) != 0o700:
        raise RuntimeError('Expected owner-private 0700 directory: '+str(directory))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--idle-seconds', type=int, default=300)
    parser.add_argument('--reload-shell', action='store_true', help='Explicit Plasma UI reload for updated widget')
    parser.add_argument('--manual-wallpapers', action='store_true', help='Enable explicit selected-monitor Apply/Restore, never automatic')
    args = parser.parse_args()
    require_owner()
    if not 30 <= args.idle_seconds <= 86400: raise RuntimeError('Idle timeout must be 30..86400 seconds')
    os.umask(0o077)
    # Read-only owner controller/queue preflight BEFORE any unit installation.
    subprocess.run([sys.executable, str(ROOT/'scripts/rollout-owner.py'), '--check-only'], check=True)
    # This reviewed checkout is staged by the authorized SSH developer jorden.
    # It is not an untrusted plugin path; permit that explicit owner, never
    # group/world-writable sources or arbitrary third-party owners.
    trusted_source_uids = (0, os.getuid(), pwd.getpwnam('jorden').pw_uid)
    for path in [ROOT, *ROOT.parents]:
        meta = path.lstat()
        if stat.S_ISLNK(meta.st_mode) or meta.st_mode & 0o022 or meta.st_uid not in trusted_source_uids:
            raise RuntimeError('Unsafe source ancestor; no permissions changed: '+str(path))
    source = ROOT/'systemd'/UNIT
    subprocess.run(['systemd-analyze','--user','verify',str(source)], check=True)
    state = Path.home()/'.local/state/weather-horde-comfy'
    for directory in [state]+[state/name for name in ('output','input','user','scratch','cache','log')]: private(directory)
    backup = Path(tempfile.mkdtemp(prefix='service-install-', dir=state))
    destination = Path.home()/'.config/systemd/user'/UNIT
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in [destination.parent,*destination.parent.parents]:
        meta=directory.lstat()
        if stat.S_ISLNK(meta.st_mode) or meta.st_mode & 0o022 or meta.st_uid not in (0,os.getuid()):
            raise RuntimeError('Unsafe unit ancestor; permissions not changed')
    if destination.is_symlink(): raise RuntimeError('Refusing symlink unit')
    if destination.exists(): shutil.copy2(destination,backup/UNIT)
    # Existing source/backups and controller settings/token are kept by rollout.
    shutil.copy2(source,backup/'new-unit.service')
    temporary = destination.with_suffix('.service.new')
    with temporary.open('x') as f:
        f.write(source.read_text()); f.flush(); os.fsync(f.fileno())
    temporary.replace(destination)
    if destination.read_bytes()!=source.read_bytes(): raise RuntimeError('Unit readback mismatch')
    subprocess.run(['systemctl','--user','daemon-reload'], check=True)
    load = subprocess.run(['systemctl','--user','show',UNIT,'--property=LoadState','--value'],
                          check=True,capture_output=True,text=True).stdout.strip()
    if load != 'loaded': raise RuntimeError('Installed unit not loaded; backup: '+str(backup))
    # No enable command: neither GPU nor controller is newly login-enabled.
    rollout = [sys.executable,str(ROOT/'scripts/rollout-owner.py'),'--service-lifecycle',
               '--comfy-idle-seconds',str(args.idle_seconds)]
    if args.reload_shell: rollout.append('--reload-shell')
    if args.manual_wallpapers: rollout.append('--manual-wallpapers')
    subprocess.run(rollout, check=True)
    receipt = {'unit':str(destination),'backup':str(backup),'load_state':load,
               'boot_enable_requested':False,'comfy_start_requested':False,
               'gpu_submitted':False,'wallpaper_changed':False,
               'readiness':'Controller revision authenticated by rollout; Comfy health checked on first eligible request'}
    (backup/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))
    print('Installed. Close this terminal. Generate now will start Comfy only when eligible; existing manual Comfy stays external.')

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('Service install stopped safely: '+str(exc),file=sys.stderr)
        sys.exit(1)
