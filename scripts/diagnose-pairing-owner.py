#!/usr/bin/env python3
"""Read-only pairing metadata; never opens or prints a token or calls services."""
import os
from pathlib import Path
import pwd
import stat
import json

def main():
    if pwd.getpwuid(os.getuid()).pw_name != 'troyborg':
        raise SystemExit('Run only in the troyborg owner terminal; no token will be read.')
    state=Path(os.environ.get('XDG_STATE_HOME') or str(Path.home()/'.local/state'))
    print('Owner terminal XDG_STATE_HOME:', str(state))
    print('Metadata only; no token contents or service requests.')
    paths=list(reversed(state.parents))+[state,state/'weather-horde-kde',state/'weather-horde-kde/token']
    for path in paths:
        try:
            s=path.lstat()
            print(json.dumps({'path':str(path),'uid':s.st_uid,'mode':oct(stat.S_IMODE(s.st_mode)), 'links':s.st_nlink,'symlink':stat.S_ISLNK(s.st_mode)}))
            if stat.S_ISLNK(s.st_mode):
                print('Stopped: symlink traversal rejected.'); break
        except OSError as exc:
            print(str(path),type(exc).__name__); break
    # Read only the owner's shell environment; never use its bus or dump values.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal(): continue
        try:
            if proc.stat().st_uid!=os.getuid() or (proc/'comm').read_text().strip()!='plasmashell': continue
            env=dict(row.split(b'=',1) for row in (proc/'environ').read_bytes().split(b'\0') if b'=' in row)
            print('Plasma PID',proc.name,'HOME',env.get(b'HOME',b'').decode(),'XDG_STATE_HOME',env.get(b'XDG_STATE_HOME',b'(unset)').decode())
        except OSError: continue

if __name__=='__main__': main()
