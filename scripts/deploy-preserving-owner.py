#!/usr/bin/env python3
"""Owner-only STOPPED persistent-unit migration; leaves controller stopped.
Preserves all settings bytes and configured flags/environment/enablement.
No token/API, service start/stop, Auto writes, Plasma reload or GPU requests.
Arrange an idle owner-stopped maintenance window before --deploy.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from portable_paths import OwnerPreflightError


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def diagnostic(status):
    quarantine = status.get('quarantine') or {}
    return {'service_version':status.get('service_version'), 'source_revision':status.get('source_revision'),
            'state':status.get('state'), 'current_decision':status.get('guard',{}).get('decision'),
            'quarantine':{k:quarantine.get(k) for k in ('decision','reason','at')},
            'refresh':{k:status.get('refresh',{}).get(k) for k in ('pending','targets','waiting_reason','retry_seconds','action_required')}}


def stage(operation, function, *args):
    try:
        return function(*args)
    except BaseException as error:
        error.owner_operation = operation
        raise


def failure_report(error):
    """Never stringify OS/subprocess errors: argv, output and filenames may be secrets."""
    import errno
    from portable_paths import OwnerPreflightError
    lines, seen, pending = [], set(), [error]
    while pending:
        error = pending.pop(0)
        if error is None or id(error) in seen: continue
        seen.add(id(error))
        line = 'operation='+getattr(error, 'owner_operation', 'owner-preflight')+' type='+type(error).__name__
        if isinstance(error, OSError):
            line += ' errno='+str(error.errno)+' ('+errno.errorcode.get(error.errno, 'UNKNOWN')+')'
        elif isinstance(error, subprocess.CalledProcessError):
            line += ' exit='+str(error.returncode)
        elif isinstance(error, OwnerPreflightError):
            line += ' '+str(error)
        lines.append(line)
        pending.extend([error.__cause__, error.__context__, getattr(error, 'owner_rollback_error', None)])
    return '; caused/rollback by: '.join(lines)


def preflight(io):
    """Read-only static admission, allowed before arranging a stopped window."""
    return stage('capture-preflight', io.capture)


def deploy(io):
    stage('stopped-check', io.require_stopped)
    saved = stage('capture-preflight', io.capture)
    stage('backup', io.backup, saved)
    try:
        stage('stopped-recheck', io.require_stopped)
        stage('install', io.install, saved)
        stage('verify', io.verify, saved)
    except BaseException as failure:
        try:
            stage('rollback-stopped-check', io.require_stopped)
            stage('rollback', io.rollback, saved)
        except BaseException as rollback_error:
            failure.owner_rollback_error = rollback_error
            raise failure
        raise


def retarget_unit(raw, old, new):
    """Change only the two source-bearing directives; retain all other bytes."""
    helper = load('install-controller-service.py')
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip().startswith('ExecStart=')]
    directories = [i for i, line in enumerate(lines) if line.strip().startswith('WorkingDirectory=')]
    if len(starts) != 1 or len(directories) != 1 or '\\\n' in text:
        raise OwnerPreflightError('Unsupported persistent unit syntax')
    i, j = starts[0], directories[0]
    prefix = 'ExecStart='+helper.quote('/usr/bin/python3')+' '+helper.quote(old/'weather_controller.py')
    if not lines[i].startswith(prefix+' ') or lines[j] != 'WorkingDirectory='+str(old).replace('%','%%')+'\n':
        raise OwnerPreflightError('Persistent unit source does not match --old-root')
    helper.quote(new)  # reject controls before constructing a scalar path
    lines[i] = lines[i].replace(prefix, 'ExecStart='+helper.quote('/usr/bin/python3')+' '+helper.quote(new/'weather_controller.py'), 1)
    lines[j] = 'WorkingDirectory='+str(new).replace('%','%%')+'\n'
    return ''.join(lines).encode('utf-8')


class OwnerDeployment:
    """Stopped-only persistent migration. No token, API, start or Auto writes.

    Caller holds the exclusive controller lifetime lock throughout deploy().
    We intentionally do not offer an automatic rollback after a controller start:
    restored Auto could already have submitted work before readback failed.
    """
    def __init__(self, old_root):
        from portable_paths import require_owner
        require_owner()
        self.helper = load('install-controller-service.py')
        self.installer = load('install-auto-pairing.py')
        self.old_root = Path(old_root).absolute()
        self.state = Path.home()/'.local/state/weather-horde-kde'
        self.destination = Path.home()/'.config/systemd/user'/self.helper.UNIT
        from portable_paths import data_home
        data = data_home()
        self.package = data/'plasma/plasmoids/org.troyborg.weatherhorde'

    def require_stopped(self):
        p = self.helper.require_stopped()
        if p.get('LoadState') != 'loaded' or p.get('Transient') != 'no' or p.get('FragmentPath') != str(self.destination):
            raise OwnerPreflightError('Expected existing persistent unit; transient migration requires separate review')
        return p

    def tree(self, root):
        self.helper.safe_path(root, (0, os.getuid()), True)
        result = {}
        for path in root.rglob('*'):
            self.helper.safe_path(path, (0, os.getuid()))
            if path.is_file(): result[str(path.relative_to(root))] = path.read_bytes()
            elif not path.is_dir(): raise OwnerPreflightError('Unsupported package object')
        return result

    def enablement(self):
        result = self.helper.ctl('is-enabled', self.helper.UNIT, check=False)
        value = result.stdout.strip()
        if (value, result.returncode) not in (('enabled',0), ('disabled',1)):
            raise OwnerPreflightError('Unsupported persistent unit enablement')
        link = self.destination.parent/'graphical-session.target.wants'/self.helper.UNIT
        if value == 'enabled':
            self.helper.safe_path(link.parent, (0,os.getuid()), True)
            if not link.is_symlink() or link.resolve() != self.destination:
                raise OwnerPreflightError('Graphical enablement link mismatch')
        elif link.exists() or link.is_symlink():
            raise OwnerPreflightError('Unexpected graphical enablement link')
        return value

    def capture(self):
        import stat
        for root in (ROOT, self.old_root):
            self.helper.safe_path(root, (0, os.getuid()), True)
        # Validate all candidate code, not only source-directory ancestry.
        for path in ROOT.rglob('*'):
            if '.git' not in path.relative_to(ROOT).parts:
                self.helper.safe_path(path, (0, os.getuid()))
        self.helper.safe_path(self.state, (0, os.getuid()), True)
        if self.state.stat().st_uid != os.getuid() or stat.S_IMODE(self.state.stat().st_mode) != 0o700:
            raise OwnerPreflightError('State root must be private and owner-owned')
        self.helper.safe_path(self.destination, (0, os.getuid()))
        if self.destination.stat().st_uid != os.getuid() or not self.destination.is_file():
            raise OwnerPreflightError('Unit must be owner-owned regular file')
        self.helper.safe_path(self.package.parent, (0, os.getuid()), True)
        raw = self.destination.read_bytes()
        settings = self.helper.private_read(self.state/'settings.json')
        self.archive = self.installer.verify_release()
        self.saved = {'unit':raw, 'new_unit':retarget_unit(raw, self.old_root, ROOT),
                      'settings':settings, 'enabled':self.enablement(),
                      'package':self.tree(self.package) if self.package.exists() else None}
        return self.saved

    def backup(self, saved):
        self.backup_dir = Path(tempfile.mkdtemp(prefix='preserving-deploy-', dir=self.state))
        self.helper.atomic(self.backup_dir/'settings.json', saved['settings'])
        self.helper.atomic(self.backup_dir/'old-unit.service', saved['unit'])
        self.helper.atomic(self.backup_dir/self.helper.UNIT, saved['new_unit'])
        self.helper.atomic(self.backup_dir/'manifest.json', json.dumps({'enabled':saved['enabled'], 'had_package':saved['package'] is not None}).encode())
        if saved['package'] is not None:
            shutil.copytree(self.package, self.backup_dir/'package')
            if self.tree(self.backup_dir/'package') != saved['package']:
                raise OwnerPreflightError('Package backup mismatch')
        self.helper.run('systemd-analyze','--user','verify',str(self.backup_dir/self.helper.UNIT))
        print('Private rollback backup:', self.backup_dir, flush=True)

    def check_unchanged(self, saved):
        if self.helper.private_read(self.state/'settings.json') != saved['settings']:
            raise OwnerPreflightError('Settings changed concurrently; never overwrite concurrent edits')
        if self.enablement() != saved['enabled']:
            raise OwnerPreflightError('Enablement changed concurrently; refusing to guess')

    def replace_package(self, source):
        # Entire-tree replacement, never merge rollback files into a new package.
        # Displaced trees are retained privately rather than recursively deleted.
        self.helper.safe_path(self.package.parent, (0, os.getuid()), True)
        if self.package.is_symlink(): raise OwnerPreflightError('Unsafe package symlink')
        if self.package.exists(): self.tree(self.package)
        stage = Path(tempfile.mkdtemp(prefix='.weather-horde-deploy-', dir=self.package.parent))
        if source is not None:
            shutil.copytree(source, stage/'incoming')
            self.tree(stage/'incoming')
        displaced = False
        try:
            if self.package.exists():
                os.replace(self.package, stage/'displaced')
                displaced = True
            if source is not None: os.replace(stage/'incoming', self.package)
        except BaseException:
            if displaced: os.replace(stage/'displaced', self.package)
            raise

    def install(self, saved):
        import zipfile
        self.check_unchanged(saved)
        if self.destination.read_bytes() != saved['unit']:
            raise OwnerPreflightError('Unit changed concurrently')
        actual = self.tree(self.package) if self.package.exists() else None
        if actual != saved['package']:
            raise OwnerPreflightError('Package changed concurrently; inspect private backup')
        with zipfile.ZipFile(self.archive) as archive:
            target = self.backup_dir/'new-package'
            target.mkdir(mode=0o700)
            for entry in archive.infolist():
                name = Path(entry.filename)
                if name.is_absolute() or '..' in name.parts or entry.is_dir():
                    raise OwnerPreflightError('Unsupported archive member')
                dest = target/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.helper.atomic(dest, archive.read(entry))
        self.expected_package = self.tree(target)
        self.replace_package(target)
        self.helper.atomic(self.destination, saved['new_unit'])
        self.helper.ctl('daemon-reload')

    def verify(self, saved):
        self.require_stopped()
        self.check_unchanged(saved)
        if self.destination.read_bytes() != saved['new_unit'] or self.tree(self.package) != self.expected_package:
            raise OwnerPreflightError('Deployment readback mismatch')
        print('Persistent source/package verified; settings bytes and enablement unchanged. Controller remains STOPPED. Runtime/UI pairing NOT verified.')

    def rollback(self, saved):
        self.require_stopped()
        self.check_unchanged(saved)
        # Refuse to overwrite a unit concurrently replaced by another installer.
        if self.destination.read_bytes() not in (saved['unit'], saved['new_unit']):
            raise OwnerPreflightError('Concurrent unit edit; inspect private backup')
        actual = self.tree(self.package) if self.package.exists() else None
        if actual != saved['package'] and actual != getattr(self, 'expected_package', saved['package']):
            raise OwnerPreflightError('Package changed concurrently; inspect private backup')
        self.replace_package(self.backup_dir/'package' if saved['package'] is not None else None)
        self.helper.atomic(self.destination, saved['unit'])
        self.helper.ctl('daemon-reload')
        self.require_stopped()
        self.check_unchanged(saved)
        actual = self.tree(self.package) if self.package.exists() else None
        if self.destination.read_bytes() != saved['unit'] or actual != saved['package']:
            raise OwnerPreflightError('Rollback readback mismatch')
        print('Rollback verified; controller remains STOPPED. No automation or settings were changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy', action='store_true', help='Migrate an already STOPPED persistent unit/package; never starts services or changes Auto')
    parser.add_argument('--old-root', type=Path)
    parser.add_argument('--preflight', action='store_true', help='Read-only static checks; safe before owner stops service; does not certify runtime exclusion')
    args = parser.parse_args()
    if args.deploy or args.preflight:
        if not args.old_root: parser.error('--deploy requires --old-root')
        if args.deploy and args.preflight: parser.error('choose --deploy or --preflight')
        from receipt_lock import state_lock
        io = OwnerDeployment(args.old_root)
        preflight(io)
        if args.preflight:
            print('Read-only preflight passed. No files or services changed. Runtime exclusion will be checked again during stopped deployment.')
            return
        with state_lock(io.state, exclusive=True):
            deploy(io)
    else:
        from portable_paths import require_owner
        require_owner()
        properties = load('install-controller-service.py').props()
        print(json.dumps({k:properties.get(k) for k in ('LoadState','ActiveState','SubState','Transient')}, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Owner operation failed: '+failure_report(error)+'. No render/apply test requested; inspect private deployment backup if present.', file=sys.stderr)
        sys.exit(1)
