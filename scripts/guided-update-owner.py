#!/usr/bin/env python3
"""Guided owner maintenance; no render, wallpaper or global shell restart."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def update(io):
    saved = io.capture()
    io.backup(saved)
    io.wait_idle()
    io.auto_off(saved)
    io.wait_idle()
    io.stop()
    io.wait_port()
    io.install()
    io.start()
    io.verify(saved)
    io.restore(saved)


class OwnerUpdate:
    def __init__(self, deployment, timeout=180, poll=1):
        self.deployment = deployment
        self.helper = deployment.helper
        self.state = deployment.state
        self.timeout, self.poll = timeout, poll
        self.base = 'http://127.0.0.1:8734'

    def api(self, body=None):
        from urllib.request import Request, build_opener, ProxyHandler
        token = self.helper.private_read(self.state/'token').decode().strip()
        request = Request(self.base+('/v1/status' if body is None else '/v1/settings'),
                          data=None if body is None else json.dumps(body).encode(),
                          method='GET' if body is None else 'PUT',
                          headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'})
        with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
            return json.load(response)

    def identity(self):
        p = self.helper.props()
        if (p.get('ActiveState') != 'active' or p.get('Transient') != 'no'
            or p.get('FragmentPath') != str(self.deployment.destination) or p.get('DropInPaths')):
            raise RuntimeError('Expected active persistent controller without drop-ins')
        pid = int(p['MainPID'])
        process = Path('/proc')/str(pid)
        if pid <= 0 or process.stat().st_uid != os.getuid():
            raise RuntimeError('Controller owner identity mismatch')
        argv = [os.fsdecode(v) for v in (process/'cmdline').read_bytes().split(b'\0') if v]
        if len(argv) < 2 or Path(argv[1]) != self.deployment.old_root/'weather_controller.py':
            raise RuntimeError('Controller source identity mismatch')
        if '--state-dir' not in argv or Path(argv[argv.index('--state-dir')+1]) != self.state:
            raise RuntimeError('Nonstandard controller state requires review')
        if '--port' in argv and argv[argv.index('--port')+1] != '8734':
            raise RuntimeError('Nonstandard controller port requires review')

    def preferences(self, expected, status):
        actual = json.loads(self.helper.private_read(self.state/'settings.json'))
        if actual != expected or any(status.get(k) != v for k, v in expected.items()):
            raise RuntimeError('Preferences changed concurrently or runtime mismatch; nothing restored')

    def capture(self):
        self.identity()
        saved = self.deployment.capture()
        self.raw = saved['settings']
        self.entry_unit, self.entry_enabled = saved['unit'], saved['enabled']
        expected = json.loads(self.raw)
        self.before = self.api()
        self.preferences(expected, self.before)
        if expected.get('automation_enabled') is not False:
            raise RuntimeError('Legacy controller has no atomic maintenance gate. Set Auto OFF while idle, then retry; no changes made')
        if self.before.get('testing_override', {}).get('active') is not False:
            raise RuntimeError('Disable testing override before maintenance')
        return expected

    def backup(self, saved):
        import tempfile
        self.backup_dir = Path(tempfile.mkdtemp(prefix='guided-update-', dir=self.state))
        print('Private recovery backup:', self.backup_dir, flush=True)
        self.helper.atomic(self.backup_dir/'settings-entry.json', self.raw)
        self.helper.atomic(self.backup_dir/'old-unit.service', self.deployment.saved['unit'])
        self.helper.atomic(self.backup_dir/'entry.json', json.dumps({
            'old_root':str(self.deployment.old_root), 'enabled':self.deployment.saved['enabled'],
            'automation_enabled':saved['automation_enabled'], 'phase':'captured'}).encode())
        self.helper.atomic(self.backup_dir/'RECOVERY.txt', b'Failure does not restore automation or restart old code. Keep Auto OFF. Old source remains untouched. The preserving-deploy backup contains the package and old unit. Do not copy historical settings over current preferences. Inspect service/source state and backups before owner-only recovery.\n')

    def pending(self):
        if (self.state/'inflight.json').exists(): return True
        journal = self.state/'wallpaper-restore.json'
        if journal.exists():
            data = json.loads(self.helper.private_read(journal))
            if any(item.get('state') == 'pending' for item in data.values()): return True
        return False

    def idle(self):
        status = self.api()
        if status.get('automation_enabled') is not False:
            raise RuntimeError('Auto changed during maintenance; refusing to interrupt work')
        return status.get('state') in {'idle','deferred','failed','quarantined','image_preview_ready',
            'wallpapers_applied','preview_ready','blocked_preview_only','applied','restored'} and not self.pending()

    def wait(self, predicate, label):
        deadline = time.monotonic()+self.timeout
        while not predicate():
            if time.monotonic() >= deadline: raise TimeoutError(label+' timed out; no job cancelled')
            time.sleep(self.poll)

    def wait_idle(self): self.wait(self.idle, 'Idle/pending apply wait')

    def auto_off(self, saved):
        self.preferences(saved, self.api())
        self.preferences(saved, self.api({'automation_enabled':False}))

    def stop(self):
        self.identity()
        self.preferences(json.loads(self.raw), self.api())
        if not self.idle(): raise RuntimeError('Work appeared before stop; controller left running')
        self.helper.ctl('stop', self.helper.UNIT)

    def port_state(self):
        # Any listener (including a foreign owner) is a hard failure, not TIME_WAIT.
        for name in ('tcp', 'tcp6'):
            for line in (Path('/proc/net')/name).read_text().splitlines()[1:]:
                fields = line.split()
                if int(fields[1].split(':')[-1],16) == 8734 and fields[3] == '0A':
                    raise RuntimeError('Listener on controller port after stop; never kill or retry foreign listeners')
        import errno
        import socket
        for family, address in ((socket.AF_INET,('127.0.0.1',8734)),(socket.AF_INET6,('::1',8734))):
            try:
                with socket.socket(family) as sock:
                    if family == socket.AF_INET6: sock.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
                    sock.bind(address)
            except OSError as error:
                if error.errno == errno.EADDRINUSE: return False
                raise
        return True

    def wait_port(self): self.wait(self.port_state, 'Port reuse wait')

    def install(self):
        from receipt_lock import state_lock
        module = load_preserving()
        with state_lock(self.state, exclusive=True):
            if (self.deployment.destination.read_bytes() != self.entry_unit
                or self.deployment.enablement() != self.entry_enabled
                or json.loads(self.helper.private_read(self.state/'settings.json')) != json.loads(self.raw)):
                raise RuntimeError('Unit, enablement or preferences changed before install; no installation attempted')
            module.deploy(self.deployment)

    def start(self):
        if json.loads(self.helper.private_read(self.state/'settings.json')).get('automation_enabled') is not False:
            raise RuntimeError('Refusing start without persisted Auto OFF')
        self.helper.ctl('start', self.helper.UNIT)

    def expected_revision(self):
        from weather_controller import SOURCE_REVISION
        return SOURCE_REVISION

    def verify(self, saved):
        from urllib.error import HTTPError, URLError
        def ready():
            try: status = self.api()
            except HTTPError: raise  # Auth errors are not readiness retries.
            except (URLError, ConnectionError): return False
            if status.get('source_revision') != self.expected_revision():
                raise RuntimeError('Authenticated loaded source revision mismatch')
            self.preferences(saved, status)
            before_caps = self.before.get('capabilities')
            after_caps = status.get('capabilities')
            if not isinstance(before_caps, dict) or not isinstance(after_caps, dict):
                raise RuntimeError('Runtime capability mismatch: capabilities schema')
            # These reviewed feature advertisements are not enabled runtime consent.
            # Preserve every existing value; admit only known True additions.
            additions = set(after_caps) - set(before_caps)
            if (not set(before_caps) <= set(after_caps)
                or any(after_caps.get(key) != value for key, value in before_caps.items())
                or not additions <= {'forced_automation', 'connected_panorama'}
                or any(after_caps[key] is not True for key in additions)):
                raise RuntimeError('Runtime capability mismatch: capabilities')
            if ('forced_automation' in additions
                and status.get('force_override', {}).get('active') is not False):
                raise RuntimeError('Runtime capability mismatch: force consent not inactive')
            for key in ('render_enabled', 'apply_enabled'):
                if status.get(key) != self.before.get(key):
                    raise RuntimeError('Runtime capability mismatch: '+key)
            if (status.get('testing_override',{}).get('active') is not False
                or status.get('comfy_service',{}).get('managed') != self.before.get('comfy_service',{}).get('managed')):
                raise RuntimeError('Runtime override/managed capability mismatch')
            if self.deployment.enablement() != self.entry_enabled:
                raise RuntimeError('Enablement changed')
            # HTTP serving can precede the monitor's first discovery result.
            # Keep all identity/preferences/safety checks hard failures above;
            # only display readiness gets the existing bounded startup retry.
            return bool(status.get('displays'))
        self.wait(ready, 'Authenticated startup')

    def restore(self, saved):
        # Legacy admission only accepts entry OFF. Preserve exact original bytes,
        # never import old backup consent. Semantic equality protects concurrent edits.
        self.preferences(saved, self.api())
        self.helper.atomic(self.state/'settings.json', self.raw)
        self.preferences(saved, self.api())
        if self.helper.private_read(self.state/'settings.json') != self.raw:
            raise RuntimeError('Settings byte readback mismatch')
        print('Authenticated candidate and preferences verified; entry Auto OFF and enablement preserved. Widget verification PENDING: no Plasma reload performed.')


def load_preserving():
    spec = importlib.util.spec_from_file_location('preserving', ROOT/'scripts/deploy-preserving-owner.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


from contextlib import contextmanager


@contextmanager
def update_lock(state):
    import fcntl
    import stat
    fd = os.open(state/'guided-update.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid() or meta.st_nlink != 1 or stat.S_IMODE(meta.st_mode) != 0o600:
            raise RuntimeError('Unsafe updater lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally: os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-root', type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--timeout', type=int, default=180, help='Bound per idle/port/start wait in seconds (1..1800)')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 1800: parser.error('timeout must be 1..1800')
    module = load_preserving()
    io = OwnerUpdate(module.OwnerDeployment(args.old_root), timeout=args.timeout)
    if args.preflight:
        io.capture()
        print('Authenticated read-only preflight passed. Auto OFF required. No service or settings changes.')
        return
    print('Exclusive owner maintenance window required: do not use the widget or other controller clients until completion. No renders are cancelled. Entry Auto must be OFF. No Plasma restart will occur.')
    if input('Type UPDATE to back up, stop, install, start and verify: ') != 'UPDATE':
        raise RuntimeError('Owner declined; no changes made')
    # Independent installer lock: controller lifetime lock is acquired only after stop.
    io.helper.safe_path(io.state, (0, os.getuid()), True)
    with update_lock(io.state):
        update(io)


if __name__ == '__main__':
    try: main()
    except (Exception, KeyboardInterrupt) as error:
        detail = str(error) if type(error) in (RuntimeError, TimeoutError) else type(error).__name__
        print('Guided update stopped: '+detail+'. No automatic restart, Auto restore or live rollback. Inspect the printed private backup; keep Auto OFF.', file=sys.stderr)
        sys.exit(1)
