"""On-demand owner user service. Never control an external Comfy listener."""
import subprocess
import threading
import time
from urllib.error import HTTPError

UNIT = 'weather-horde-comfy.service'

def port_occupied():
    from pathlib import Path
    return any(row.split()[1].split(':')[-1] == '1FFC' and row.split()[3] == '0A'
               for file in ('/proc/net/tcp', '/proc/net/tcp6')
               for row in Path(file).read_text().splitlines()[1:])


class ComfyService:
    def __init__(self, transport, idle_seconds=300, startup_seconds=90, systemctl='systemctl'):
        if not 30 <= idle_seconds <= 86400: raise ValueError('Idle timeout must be 30..86400 seconds')
        self.transport = transport
        self.idle_seconds, self.startup_seconds = idle_seconds, startup_seconds
        self.systemctl = systemctl
        self.state, self.reason = 'stopped', 'Not started'
        self.owned_identity = None
        self.last_used = time.monotonic()
        self.lock = threading.RLock()

    def command(self, *args):
        return subprocess.run([self.systemctl, '--user', *args], check=True,
                              capture_output=True, text=True, timeout=10).stdout

    def unit(self):
        return dict(line.split('=', 1) for line in self.command('show', UNIT,
            '--property=LoadState,ActiveState,MainPID').splitlines() if '=' in line)

    def status(self):
        return {'state':self.state, 'reason':self.reason, 'managed':True,
                'owned':self.owned_identity is not None, 'idle_timeout_seconds':self.idle_seconds}

    def fail(self, reason):
        self.state, self.reason = 'failed', reason
        raise ValueError(reason)

    def ensure_ready(self, guard, existing_guard=None):
        with self.lock:
            if existing_guard is not None and self.transport.owned_gpu_pid() is not None:
                decision = existing_guard()
                if decision != 'safe': raise ValueError('Existing Comfy preview deferred: '+decision)
                self.state, self.reason = 'ready', 'Verified existing listener; no start requested'
                self.last_used = time.monotonic()
                return
            decision = guard()
            if decision != 'safe': raise ValueError('Comfy startup deferred: '+decision)
            info = self.unit()
            # An already listening external/manual server may be used through
            # the transport's existing hard ownership gates, but never adopted.
            pid = self.transport.owned_gpu_pid()
            if pid is not None:
                self.state, self.reason = 'ready', 'Verified existing listener; no start requested'
                self.last_used = time.monotonic()
                return
            if info.get('LoadState') != 'loaded': self.fail('Comfy user unit not installed; run owner service installer')
            if info.get('ActiveState') not in ('inactive', 'failed'):
                self.fail('Comfy unit active but listener ownership/readiness unavailable')
            # No listener (including a foreign or wildcard listener) may be
            # overwritten. The owner launcher independently checks again.
            if port_occupied(): self.fail('Comfy port occupied by an unverified listener; not stopped')
            if guard() != 'safe': self.fail('Comfy startup eligibility changed; no start requested')
            self.state, self.reason = 'starting', 'Waiting for owner Comfy health'
            try:
                self.command('start', '--no-block', UNIT)
            except (OSError, subprocess.SubprocessError):
                self.fail('Comfy user service start failed; inspect owner user manager/log')
            deadline = time.monotonic() + self.startup_seconds
            # A previously stopped server identity must not poison restart.
            self.transport.listener = None
            while time.monotonic() < deadline:
                info = self.unit()
                if info.get('ActiveState') == 'failed': self.fail('Comfy user service failed; inspect private log')
                try:
                    stats = self.transport.request('/system_stats')
                    pid = self.transport.owned_gpu_pid()
                    if isinstance(stats, dict) and pid and str(pid) == info.get('MainPID'):
                        self.owned_identity = self.transport.listener
                        self.last_used = time.monotonic()
                        self.state, self.reason = 'ready', 'Owner service healthy'
                        # Never queue here; caller must recheck its frozen policy.
                        return
                except HTTPError as exc:
                    if exc.code in (401, 403): self.fail('Comfy authentication rejected; not an offline service')
                except (OSError, ValueError): pass
                time.sleep(.25)
            self.fail('Comfy startup health timeout; no job submitted, inspect private log')

    def maintain(self, inflight=False):
        with self.lock:
            if inflight:
                self.last_used = time.monotonic()
                self.state, self.reason = 'busy', 'Controller job active or unreconciled'
                return
            if self.owned_identity is None:
                if self.state == 'failed': return  # preserve startup diagnostics
                if self.transport.owned_gpu_pid() is not None:
                    self.state, self.reason = 'ready', 'Verified external listener; never stopped by this app'
                elif port_occupied():
                    self.state, self.reason = 'busy', 'External or unverified listener/queue; no lifecycle control'
                else:
                    self.state, self.reason = 'stopped', 'No Comfy listener; waiting for eligible request'
                return
            try:
                info = self.unit()
                if info.get('ActiveState') == 'inactive':
                    self.owned_identity = None
                    self.state, self.reason = 'stopped', 'Owner service stopped'
                    return
                pid = self.transport.owned_gpu_pid()
                if (pid is None or self.transport.listener != self.owned_identity
                        or str(pid) != info.get('MainPID')):
                    self.last_used = time.monotonic()
                    self.state, self.reason = 'busy', 'Foreign queue or changed listener; shutdown prohibited'
                    return
                queue = self.transport.request('/queue')
                if queue.get('queue_running') != [] or queue.get('queue_pending') != []:
                    self.last_used = time.monotonic()
                    self.state, self.reason = 'busy', 'Queue not empty; shutdown prohibited'
                    return
                self.state, self.reason = 'ready', 'Owner service idle'
                if time.monotonic()-self.last_used < self.idle_seconds: return
                # Recheck identity and queue immediately before scoped stop.
                if self.transport.owned_gpu_pid() != pid or self.transport.listener != self.owned_identity: return
                if self.transport.request('/queue') != queue: return
                if self.unit().get('MainPID') != str(pid): return
                self.state, self.reason = 'stopping', 'Idle timeout; releasing GPU by process exit'
                self.command('stop', '--no-block', UNIT)
            except (OSError, ValueError, subprocess.SubprocessError):
                self.state, self.reason = 'failed', 'Cannot verify service/queue; no shutdown authorized'
