import importlib.util
import unittest


class FakeTransport:
    def __init__(self, status='running'):
        self.calls=[]; self.status=status
    def queue(self, workflow): self.calls.append(('queue', workflow)); return 'owned-123'
    def inspect(self, job): self.calls.append(('inspect',job)); return self.status
    def cancel_pending(self, job): self.calls.append(('cancel_pending',job))


class JobSafetyTests(unittest.TestCase):
    def test_force_never_bypasses_guard_and_midrender_never_interrupts_other_jobs(self):
        self.assertIsNotNone(importlib.util.find_spec('jobs'), 'guarded job lifecycle missing')
        from jobs import GuardedJob
        backend=FakeTransport()
        decision=['vr_active']
        job=GuardedJob(backend, lambda: decision[0])
        self.assertEqual(job.start({'reviewed':'workflow'}, force=True), 'deferred')
        self.assertEqual(backend.calls, [])
        decision[0]='safe'
        self.assertEqual(job.start({'reviewed':'workflow'}, force=True), 'queued')
        decision[0]='game_active'
        self.assertEqual(job.poll(), 'rendering_guard_blocked')
        self.assertEqual(backend.calls[-1], ('inspect','owned-123'))
        backend.status='complete'
        self.assertEqual(job.poll(), 'waiting_to_apply')
        self.assertFalse(any(c[0]=='interrupt' for c in backend.calls))
        backend2=FakeTransport('pending')
        decision[0]='safe'
        job2=GuardedJob(backend2, lambda: decision[0])
        job2.start({})
        decision[0]='unknown'
        self.assertEqual(job2.poll(),'deferred')
        self.assertEqual(backend2.calls[-1],('cancel_pending','owned-123'))
        backend3=FakeTransport('complete')
        decision[0]='safe'
        job3=GuardedJob(backend3, lambda: decision[0])
        job3.start({})
        self.assertEqual(job3.poll(),'preview_ready')

if __name__ == '__main__': unittest.main()
