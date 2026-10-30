"""Read-only local listener identity. No process-name/Python blanket trust."""
import os
from pathlib import Path

COMFY_ROOT = Path('/mnt/data-ssd/ComfyUI/app')


def listener_identity(port, proc=Path('/proc'), uid=None):
    uid = os.getuid() if uid is None else uid
    try:
        # Accept only the exact IPv4 loopback listener used by our transport.
        rows = [line.split() for line in (proc/'net/tcp').read_text().splitlines()[1:]]
        sockets = [r for r in rows if r[1] == f'0100007F:{port:04X}' and r[3] == '0A']
        if len(sockets) != 1 or int(sockets[0][7]) != uid: return None
        inode = sockets[0][9]
        matches = []
        for process in proc.iterdir():
            if not process.name.isdigit(): continue
            try:
                if process.stat().st_uid != uid: continue
                if not any(os.readlink(fd) == 'socket:['+inode+']' for fd in (process/'fd').iterdir()): continue
                args = (process/'cmdline').read_bytes().split(b'\0')
                args = [os.fsdecode(a) for a in args if a]
                cwd = (process/'cwd').resolve(strict=True)
                # A direct interpreter+main.py invocation only. Reject -c, -m,
                # wrappers and any other Python workload, even on the same UID.
                if len(args) < 2 or args[1].startswith('-'): return None
                script = Path(args[1]); script = script if script.is_absolute() else cwd/script
                if script.resolve() != COMFY_ROOT/'main.py': return None
                executable = (process/'exe').resolve(strict=True)
                if not executable.name.startswith('python'): return None
                fields = (process/'stat').read_text().rsplit(')',1)[1].split()
                matches.append((int(process.name), uid, int(fields[19])))
            except (OSError,ValueError):
                continue
        return matches[0] if len(matches) == 1 else None
    except (OSError,ValueError,IndexError): return None
