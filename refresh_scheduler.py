"""Pure coalescing automatic refresh intent. Caller serializes access.

UTC measures successful output age; monotonic repeated observations measure
settling/backoff. Never treat a telemetry gap (including suspend) as safety.
"""
import math
import uuid

REASONS = frozenset(('interval', 'unlock', 'startup', 'activity_recovered', 'retry', 'calendar_change'))


class RefreshScheduler:
    def __init__(self, grace=60, observation_ttl=15):
        self.grace, self.observation_ttl = grace, observation_ttl
        self.enabled = False
        self.mode = None
        self.targets = set()
        self.interval = 3600
        self.pending = {}
        self.success = {}
        self.active = None
        self.safe_since = self.last_observed = None
        self.retry_at = 0
        self.failures = 0
        self.blocker = 'activity_unknown'
        self.permanent_error = ''

    def configure(self, enabled, mode, targets, interval):
        changed = self.mode != mode or self.targets != set(targets)
        if not enabled or changed:
            self.pending.clear()
            self.active = None
            self.retry_at = 0
            self.failures = 0
        self.enabled, self.mode = enabled, mode
        self.targets, self.interval = set(targets), interval

    def request(self, reason, targets):
        if reason not in REASONS:
            raise ValueError('Unbounded refresh reason')
        if self.enabled:
            for target in set(targets) & self.targets:
                self.pending.setdefault(target, set()).add(reason)

    def reconcile(self, now_utc, reason='interval'):
        due = [t for t in self.targets if
               (stamp := self.success.get(self.mode, {}).get(t)) is None or
               now_utc < stamp or now_utc - stamp >= self.interval]
        self.request(reason, due)

    def observe_activity(self, safe, unlocked, monotonic_now):
        gap = (self.last_observed is None or monotonic_now < self.last_observed or
               monotonic_now - self.last_observed > self.observation_ttl)
        if gap or safe is not True or unlocked is not True:
            self.safe_since = None
        self.last_observed = monotonic_now
        self.blocker = ('session_locked' if unlocked is False else
                        'session_unknown' if unlocked is None else
                        'activity_unsafe_or_unknown' if safe is not True else '')
        if not self.blocker and self.safe_since is None:
            self.safe_since = monotonic_now

    def next_action(self, now_utc, monotonic_now):
        if (not self.enabled or not self.pending or self.active or
                self.permanent_error or monotonic_now < self.retry_at or self.safe_since is None or
                self.last_observed is None or not 0 <= monotonic_now-self.last_observed <= self.observation_ttl or
                monotonic_now-self.safe_since < self.grace):
            return None
        self.active = {'generation_id': uuid.uuid4().hex, 'targets': sorted(self.pending), 'mode': self.mode}
        return dict(self.active)

    def complete(self, target, generation_id, applied_at):
        if not self.active or self.active['generation_id'] != generation_id or target not in self.active['targets']:
            return False
        self.success.setdefault(self.mode, {})[target] = applied_at
        self.pending.pop(target, None)
        self.active['targets'].remove(target)
        if not self.active['targets']:
            self.active = None
            self.failures = 0
        return True

    def fail(self, reason, retryable=True, monotonic_now=0):
        self.active = None
        self.failures += 1
        self.retry_at = monotonic_now + (60, 300, 900)[min(self.failures-1, 2)] if retryable else math.inf
        if retryable: self.blocker = reason
        else: self.permanent_error = reason
        self.request('retry', self.pending)

    def status(self, monotonic_now):
        stale = self.last_observed is None or not 0 <= monotonic_now-self.last_observed <= self.observation_ttl
        return {'pending': sorted(self.pending),
                'reasons': sorted(set().union(*self.pending.values())) if self.pending else [],
                'waiting_reason': self.permanent_error or ('activity_unknown' if stale else self.blocker or ('settling' if self.safe_since is not None and monotonic_now-self.safe_since < self.grace else 'ready')),
                'activity_reason': 'activity_unknown' if stale else self.blocker,
                'settling_seconds': math.ceil(max(0, self.grace - (monotonic_now-self.safe_since))) if self.safe_since is not None else self.grace,
                'retry_seconds': math.ceil(max(0, self.retry_at-monotonic_now)) if math.isfinite(self.retry_at) else None,
                'action_required': bool(self.permanent_error),
                'last_success': self.success, 'active': self.active}
