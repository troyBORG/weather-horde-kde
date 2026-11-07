#!/usr/bin/env python3
"""Standalone, maintained owner bundle bootstrap. Generated wrapper pins archive hash.
Stopped-only deployment remains supported; --guided delegates explicit owner maintenance.
No imports from candidate until full archive verification.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tarfile
sys.dont_write_bytecode = True


def trusted(path):
    for p in (path, *path.parents):
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid not in (0, os.getuid()) or st.st_mode & 0o022:
            raise RuntimeError('Unsafe path '+repr(str(p))+f' mode={stat.S_IMODE(st.st_mode):04o} uid={st.st_uid}; '
                               'permissions unchanged. Review only this path; if unintended writable permissions, chmod go-w (never recursively).')


def prepare(archive, destination, digest, version):
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise RuntimeError('Archive SHA256 mismatch; use a new verified delivery, never overwrite existing extraction')
    files, directories = {}, set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar:
        for member in tar.getmembers():
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or str(path) != member.name.rstrip('/') or not path.parts:
                raise RuntimeError('Unsafe archive member')
            if member.isdir(): directories.add(str(path)); continue
            if not member.isfile() or str(path) in files:
                raise RuntimeError('Unsupported/duplicate archive member')
            files[str(path)] = tar.extractfile(member).read()
            directories.update(str(p) for p in path.parents if str(p) != '.')
    if set(files) & directories: raise RuntimeError('Conflicting archive objects')
    metadata = json.loads(files['plasma-widget/org.troyborg.weatherhorde/metadata.json'])
    if metadata['KPlugin']['Version'] != version: raise RuntimeError('Candidate version mismatch')
    trusted(destination.parent)
    if destination.exists() or destination.is_symlink():
        trusted(destination)
        if destination.stat().st_uid != os.getuid() or not destination.is_dir():
            raise RuntimeError('Existing extraction must be owner-owned directory')
        actual, actual_dirs = {}, set()
        for p in destination.rglob('*'):
            trusted(p)
            st = p.lstat()
            if st.st_uid != os.getuid(): raise RuntimeError('Extraction ownership mismatch')
            name = str(p.relative_to(destination))
            if p.is_dir(): actual_dirs.add(name)
            elif stat.S_ISREG(st.st_mode) and st.st_nlink == 1: actual[name] = p.read_bytes()
            else: raise RuntimeError('Unsupported extraction object')
        if actual != files or actual_dirs != directories:
            raise RuntimeError('Stale/corrupt extraction; untouched. Choose a new candidate path, do not overwrite it')
        return destination
    destination.mkdir(mode=0o700)  # exclusive creation; no existing directory overwritten
    for name in sorted(directories, key=lambda n: (len(Path(n).parts), n)):
        (destination/name).mkdir(mode=0o700)
    for name, data in files.items():
        with (destination/name).open('xb') as stream: stream.write(data)
        (destination/name).chmod(0o600)
    return prepare(archive, destination, digest, version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--candidate-name', required=True)
    parser.add_argument('--deploy', action='store_true', help='Existing stopped-only deployment')
    parser.add_argument('--guided', action='store_true', help='Interactive owner backup/stop/install/start/verify; entry Auto OFF required')
    parser.add_argument('--preflight', action='store_true', help='Checks only; with --guided authenticates runtime without mutation')
    args = parser.parse_args()
    if args.deploy and (args.guided or args.preflight): parser.error('--deploy cannot be combined with --guided/--preflight')
    owner = pwd.getpwuid(os.getuid())
    if os.getuid() == 0 or os.environ.get('WEATHER_HORDE_OWNER') != owner.pw_name:
        raise RuntimeError('Set WEATHER_HORDE_OWNER to your KDE account in its terminal; never use sudo')
    home = Path.home()
    if home != Path(owner.pw_dir): raise RuntimeError('HOME must match the kernel owner account home')
    data = os.environ.get('XDG_DATA_HOME', str(home/'.local/share'))
    if not Path(data).is_absolute() or '..' in Path(data).parts or data != data.strip() or any(ord(c)<32 for c in data):
        raise RuntimeError('XDG_DATA_HOME malformed; expected absolute path without traversal or control characters')
    if Path(args.candidate_name).name != args.candidate_name or args.candidate_name in ('.','..'):
        raise RuntimeError('Candidate must be a new basename under owner HOME')
    # Read-only ancestry admission before extraction, before any stopped request.
    for path in (home, Path(data), home/'.local/state/weather-horde-kde', home/'.config/systemd/user'):
        trusted(path)
    result = subprocess.run(['systemctl','--user','show','weather-horde-kde.service','--property=WorkingDirectory','--value'], check=True, capture_output=True, text=True, timeout=30)
    old = result.stdout.strip()
    if not Path(old).is_absolute() or any(ord(c)<32 for c in old): raise RuntimeError('Cannot discover persistent source directory')
    candidate = prepare(args.archive, home/args.candidate_name, args.sha256, args.version)
    if args.guided:
        command = [sys.executable,'-B',str(candidate/'scripts/guided-update-owner.py'),'--old-root',old]
        subprocess.run(command+(['--preflight'] if args.preflight else []), check=True)
        return
    command = [sys.executable,'-B',str(candidate/'scripts/deploy-preserving-owner.py'),'--old-root',old]
    subprocess.run(command+['--preflight'], check=True)
    if args.deploy:
        subprocess.run(command+['--deploy'], check=True)
    else:
        print('Candidate verified; preflight only. When safely idle, owner may stop controller then rerun this wrapper with --deploy. No service was stopped or started.')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        import errno
        # Only our own RuntimeErrors contain public diagnostics; never stringify subprocess/OS exceptions.
        detail = str(error) if type(error) is RuntimeError else type(error).__name__
        if isinstance(error, OSError): detail += ' errno='+str(error.errno)+' '+errno.errorcode.get(error.errno,'UNKNOWN')
        print('Owner bootstrap failed: '+detail, file=sys.stderr)
        sys.exit(1)
