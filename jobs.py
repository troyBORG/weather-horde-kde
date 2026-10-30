"""Transport-independent job policy, tested with fakes, NOT enabled by HTTP controller.

No global interrupt operation exists in the transport contract. A running job may
finish while its output is quarantined. Pending cancellation targets only our ID.
An actual Comfy transport and validated image store require a later approved step.
"""
import threading


class GuardedJob:
    def __init__(self, transport, guard):
        self.transport = transport
        self.guard = guard
        self.job_id = None
        self.blocked_during_render = False
        self.state = 'idle'
        self.lock = threading.Lock()

    def decision(self):
        try: return self.guard()
        except Exception: return 'unknown'

    def start(self, workflow, force=False):
        with self.lock:
            if self.job_id is not None: raise ValueError('Job already in flight')
            if self.decision() != 'safe':
                self.state = 'deferred'
                return self.state
            # Force is only a future dedup override; it cannot change policy.
            self.job_id = self.transport.queue(workflow)
            self.state = 'queued'
            return self.state

    def poll(self):
        with self.lock:
            if self.job_id is None: return self.state
            safe = self.decision() == 'safe'
            status = self.transport.inspect(self.job_id)
            if not safe: self.blocked_during_render = True
            if status == 'pending' and not safe:
                self.transport.cancel_pending(self.job_id)
                self.state = 'deferred'
                self.job_id = None
            elif status == 'complete':
                # Recheck after history fetch. Never call an apply command here.
                self.state = ('preview_ready' if self.decision() == 'safe' and not self.blocked_during_render
                              else 'waiting_to_apply')
                self.job_id = None
            elif status == 'failed':
                self.state = 'failed'
                self.job_id = None
            elif status in ('pending','running'):
                self.state = 'rendering' if safe else 'rendering_guard_blocked'
            else:
                self.state = 'unknown'
            return self.state
